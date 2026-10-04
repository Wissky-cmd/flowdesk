"""Database-owned budgets and leases. Celery messages are only delivery hints."""
import csv
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from .config import settings
from .models import Job, JobEvent, Membership, OutboxEvent, Ticket, User

logger = logging.getLogger('flowdesk.jobs')
engine = create_engine(settings.database_url, pool_pre_ping=True)
Sessions = sessionmaker(engine, expire_on_commit=False)
MAX_EXECUTIONS = 3
MAX_DELIVERIES = 5
LEASE_SECONDS = 120


def now():
    return datetime.now(timezone.utc)


def event(db, job, kind, **detail):
    db.add(JobEvent(job_id=job.id, generation=job.generation, kind=kind, detail=detail))


def permitted(db, job):
    member = db.get(Membership, (job.workspace_id, job.owner_id))
    owner = db.get(User, job.owner_id)
    return bool(member and member.is_active and member.role == job.owner_role and owner and owner.is_active)


def fail(db, job, code):
    job.status, job.error_code, job.claim_token, job.lease_until = 'failed', code, None, None
    outbox = db.get(OutboxEvent, job.id)
    outbox.status = 'exhausted'
    event(db, job, 'failed', error_code=code)


def queue_again(db, job, code):
    if job.run_attempts >= MAX_EXECUTIONS:
        fail(db, job, code + '_EXHAUSTED')
        return
    job.status, job.error_code, job.claim_token, job.lease_until = 'queued', code, None, None
    outbox = db.get(OutboxEvent, job.id)
    outbox.status, outbox.claim_token = 'pending', None
    outbox.next_attempt_at = now() + timedelta(seconds=5 * 2 ** job.run_attempts)
    job.ready_at = outbox.next_attempt_at
    event(db, job, 'retry_scheduled', error_code=code, attempt=job.attempts)


def reconcile():
    """Recover abandoned work, expire results, preserve every automatic attempt count."""
    with Sessions.begin() as db:
        jobs = db.scalars(select(Job).where(
            (Job.expires_at <= now()) | ((Job.status == 'running') & (Job.lease_until <= now()))
        ).where(Job.status != 'expired').with_for_update(skip_locked=True).limit(100)).all()
        for job in jobs:
            if job.expires_at <= now():
                job.status, job.result_key, job.claim_token, job.lease_until = 'expired', None, None, None
                db.get(OutboxEvent, job.id).status = 'exhausted'
                event(db, job, 'expired')
            else:
                queue_again(db, job, 'LEASE_EXPIRED')
    # Recover file cleanup after a crash; only server-generated UUID names are touched.
    if settings.export_dir.exists():
        for path in settings.export_dir.iterdir():
            try:
                job_id = uuid.UUID(path.name.split('.')[0])
                if path.suffix not in ('.csv', '.tmp'):
                    continue
                with Sessions.begin() as db:
                    # Serialize deletion with retry and publication of the same UUID file.
                    job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
                    old = now().timestamp() - path.stat().st_mtime > LEASE_SECONDS * 2
                    if old and (path.suffix == '.tmp' or not job or job.status == 'expired'):
                        path.unlink(missing_ok=True)
            except (ValueError, OSError):
                logger.warning('Export cleanup deferred')


def dispatch_once(publish):
    """Reserve attempts before publishing; crash boundaries can duplicate delivery."""
    reconcile()
    for _ in range(25):
        with Sessions.begin() as db:
            pair = db.execute(select(Job, OutboxEvent).join(OutboxEvent).where(
                Job.status == 'queued', Job.expires_at > now(), OutboxEvent.status != 'exhausted', OutboxEvent.next_attempt_at <= now(),
            ).order_by(OutboxEvent.next_attempt_at).with_for_update(skip_locked=True).limit(1)).first()
            if not pair:
                break
            job, outbox = pair
            if not permitted(db, job):
                fail(db, job, 'PERMISSION_REVOKED')
                continue
            if outbox.run_attempts >= MAX_DELIVERIES:
                fail(db, job, 'DELIVERY_EXHAUSTED')
                continue
            claim = uuid.uuid4()
            outbox.claim_token, outbox.status = claim, 'dispatching'
            outbox.attempts += 1
            outbox.run_attempts += 1
            outbox.next_attempt_at = now() + timedelta(seconds=30 * 2 ** (outbox.run_attempts - 1))
            job_id, generation = job.id, job.generation
            event(db, job, 'delivery_started', attempt=outbox.attempts)
        try:
            publish(str(job_id))
            error = None
        except Exception as exc:
            error = type(exc).__name__
            logger.warning('Queue publish failed job_id=%s error=%s', job_id, error)
        with Sessions.begin() as db:
            job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            outbox = db.get(OutboxEvent, job_id)
            if job.generation != generation or outbox.claim_token != claim:
                continue
            if job.status != 'queued':
                continue
            outbox.status = 'pending' if error else 'sent'
            event(db, job, 'delivery_failed' if error else 'delivered', attempt=outbox.attempts, error_code=error)
            if error and outbox.run_attempts >= MAX_DELIVERIES:
                fail(db, job, 'DELIVERY_EXHAUSTED')


def csv_cell(value):
    value = '' if value is None else str(value)
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


class ExportRejected(Exception):
    pass


def build_export(job, path):
    with Sessions() as db:
        if not permitted(db, job):
            raise ExportRejected('PERMISSION_REVOKED')
        conditions = [Ticket.workspace_id == job.workspace_id]
        if job.owner_role == 'requester':
            conditions.append(Ticket.creator_id == job.owner_id)
        rows = db.execute(select(Ticket.id, Ticket.title, Ticket.status, Ticket.priority, Ticket.creator_id,
                                 Ticket.assignee_id, Ticket.created_at)
                          .where(*conditions).order_by(Ticket.created_at, Ticket.id).limit(10001)).all()
        if len(rows) > 10000:
            raise ExportRejected('EXPORT_ROW_LIMIT')
        with path.open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['编号', '标题', '状态', '优先级', '创建人', '负责人', '创建时间'])
            for ticket in rows:
                writer.writerow([csv_cell(value) for value in (ticket.id, ticket.title, ticket.status, ticket.priority, ticket.creator_id, ticket.assignee_id, ticket.created_at.isoformat())])
            stream.flush()
            os.fsync(stream.fileno())


def execute_job(job_id):
    job_id = uuid.UUID(job_id)
    with Sessions.begin() as db:
        job = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
        if not job or job.status != 'queued' or job.expires_at <= now() or job.ready_at > now():
            return
        if not permitted(db, job):
            fail(db, job, 'PERMISSION_REVOKED')
            return
        if job.run_attempts >= MAX_EXECUTIONS:
            fail(db, job, 'EXECUTION_EXHAUSTED')
            return
        job.attempts += 1
        job.run_attempts += 1
        claim = uuid.uuid4()
        job.claim_token, job.status = claim, 'running'
        job.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
        event(db, job, 'execution_started', attempt=job.attempts, claim=str(claim))
    temporary = settings.export_dir / f'{job.id}.{claim}.tmp'
    try:
        settings.export_dir.mkdir(parents=True, exist_ok=True)
        build_export(job, temporary)
        with Sessions.begin() as db:
            current = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if current.status != 'running' or current.claim_token != claim or current.lease_until <= now() or current.expires_at <= now():
                return
            if not permitted(db, current):
                fail(db, current, 'PERMISSION_REVOKED')
                return
            # Row lock + claim token fence stale workers before atomic publication.
            key = f'{job.id}.csv'
            os.replace(temporary, settings.export_dir / key)
            current.status, current.result_key, current.error_code = 'succeeded', key, None
            current.claim_token, current.lease_until = None, None
            event(db, current, 'succeeded', attempt=current.attempts)
    except Exception as exc:
        logger.warning('Export attempt failed job_id=%s error=%s', job_id, type(exc).__name__)
        with Sessions.begin() as db:
            current = db.scalar(select(Job).where(Job.id == job_id).with_for_update())
            if current.status == 'running' and current.claim_token == claim:
                if isinstance(exc, (OSError, OperationalError)):
                    queue_again(db, current, 'TEMPORARY_FAILURE')
                else:
                    fail(db, current, str(exc) if isinstance(exc, ExportRejected) else 'EXPORT_ERROR')
    finally:
        temporary.unlink(missing_ok=True)
