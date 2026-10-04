from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from .config import settings
from .models import Job, JobEvent, Membership, OutboxEvent
from .security import DB, CurrentUser
from .workspaces import require_member

router = APIRouter(prefix='/workspaces/{wid}')


def output(job):
    result = {key: getattr(job, key) for key in ('id', 'status', 'generation', 'attempts', 'run_attempts', 'error_code', 'expires_at', 'created_at')}
    if job.expires_at <= datetime.now(timezone.utc):
        result['status'] = 'expired'
    return result


async def lock_export_owner(db, wid, user):
    # Creation and retry share this lock before taking any job lock.
    member = await db.scalar(select(Membership).where(Membership.workspace_id == wid, Membership.user_id == user.id)
                             .with_for_update().execution_options(populate_existing=True))
    if not member or not member.is_active:
        raise HTTPException(404, '工作空间或资源不存在')
    return member


async def check_pending_quota(db, wid, user):
    count = await db.scalar(select(func.count()).select_from(Job).where(
        Job.workspace_id == wid, Job.owner_id == user.id, Job.status.in_(['queued', 'running']),
        Job.expires_at > datetime.now(timezone.utc)))
    if count >= 5:
        raise HTTPException(429, '最多同时保留 5 个待处理导出任务')


async def accessible_job(db, wid, job_id, user, lock=False):
    member = await require_member(db, wid, user.id)
    query = select(Job).where(Job.id == job_id, Job.workspace_id == wid, Job.owner_id == user.id)
    job = await db.scalar(query.with_for_update() if lock else query)
    if not job:
        raise HTTPException(404, '任务不存在或不可访问')
    return job, member


@router.post('/exports', status_code=202)
async def create_export(wid: UUID, db: DB, user: CurrentUser):
    member = await lock_export_owner(db, wid, user)
    await check_pending_quota(db, wid, user)
    job = Job(workspace_id=wid, owner_id=user.id, owner_role=member.role, expires_at=datetime.now(timezone.utc) + timedelta(hours=24))
    db.add(job)
    await db.flush()
    db.add(OutboxEvent(job_id=job.id))
    db.add(JobEvent(job_id=job.id, generation=1, kind='created', detail={'actor_id': str(user.id)}))
    await db.commit()
    return output(job)


@router.get('/jobs')
async def list_jobs(wid: UUID, db: DB, user: CurrentUser, page: int = Query(1, ge=1)):
    await require_member(db, wid, user.id)
    rows = (await db.execute(select(Job, func.count().over()).where(Job.workspace_id == wid, Job.owner_id == user.id).order_by(Job.created_at.desc(), Job.id.desc()).offset((page - 1) * 20).limit(20))).all()
    total = rows[0][1] if rows else await db.scalar(select(func.count()).select_from(Job).where(Job.workspace_id == wid, Job.owner_id == user.id))
    return {'items': [output(job) for job, _ in rows], 'total': total}


@router.get('/jobs/{job_id}')
async def job_detail(wid: UUID, job_id: UUID, db: DB, user: CurrentUser):
    job, _ = await accessible_job(db, wid, job_id, user)
    outbox = await db.get(OutboxEvent, job.id)
    events = (await db.scalars(select(JobEvent).where(JobEvent.job_id == job.id).order_by(JobEvent.created_at.desc(), JobEvent.id.desc()).limit(100))).all()
    return {**output(job), 'delivery_attempts': outbox.attempts, 'delivery_run_attempts': outbox.run_attempts,
            'events': [{'kind': e.kind, 'generation': e.generation, 'detail': e.detail, 'created_at': e.created_at} for e in events]}


class RetryInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    reason: str = Field(min_length=1, max_length=500)


@router.post('/jobs/{job_id}/retry')
async def retry_job(wid: UUID, job_id: UUID, data: RetryInput, db: DB, user: CurrentUser):
    await lock_export_owner(db, wid, user)
    job, member = await accessible_job(db, wid, job_id, user, lock=True)
    if job.status not in ('failed', 'expired') and job.expires_at > datetime.now(timezone.utc):
        raise HTTPException(409, '仅失败或过期的任务可以人工重试')
    await check_pending_quota(db, wid, user)
    job.generation += 1
    job.run_attempts = 0
    job.status, job.error_code, job.result_key = 'queued', None, None
    job.claim_token, job.lease_until = None, None
    job.owner_role = member.role
    job.ready_at = datetime.now(timezone.utc)
    job.expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
    outbox = await db.get(OutboxEvent, job.id)
    outbox.status, outbox.run_attempts, outbox.claim_token = 'pending', 0, None
    outbox.next_attempt_at = datetime.now(timezone.utc)
    db.add(JobEvent(job_id=job.id, generation=job.generation, kind='manual_retry', detail={'actor_id': str(user.id), 'reason': data.reason}))
    await db.commit()
    return output(job)


@router.get('/jobs/{job_id}/download')
async def download_export(wid: UUID, job_id: UUID, db: DB, user: CurrentUser):
    job, member = await accessible_job(db, wid, job_id, user)
    if member.role != job.owner_role:
        raise HTTPException(403, '权限已变化，请重新创建导出任务')
    if job.expires_at <= datetime.now(timezone.utc):
        raise HTTPException(410, '导出文件已过期，请重新导出')
    if job.status != 'succeeded' or job.result_key != f'{job.id}.csv':
        raise HTTPException(409, '导出尚未完成')
    path = settings.export_dir / job.result_key
    if not path.is_file():
        raise HTTPException(410, '导出文件不存在，请重新导出')
    return FileResponse(path, media_type='text/csv; charset=utf-8', filename=f'FlowDesk-{str(job.id)[:8]}.csv')
