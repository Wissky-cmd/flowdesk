from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from app import job_runtime as runtime
from app.config import settings
from app.models import Job, JobEvent, OutboxEvent
from app.seed import seed_id
from test_phase_one import BASE, PAYLOAD, TICKET


@pytest.fixture(autouse=True)
def export_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'export_dir', tmp_path / 'exports')


def create(client):
    response = client.post(BASE + '/exports')
    assert response.status_code == 202, response.text
    return response.json()['id']


def detail(client, job_id):
    return client.get(BASE + '/jobs/' + job_id).json()


def due(job_id):
    with runtime.Sessions.begin() as db:
        db.get(OutboxEvent, UUID(job_id)).next_attempt_at = runtime.now() - timedelta(seconds=1)
        db.get(Job, UUID(job_id)).ready_at = runtime.now() - timedelta(seconds=1)


def test_job_creation_and_outbox_atomicity(login, sql, monkeypatch):
    client = login()
    from app import jobs
    real = jobs.OutboxEvent
    monkeypatch.setattr(jobs, 'OutboxEvent', lambda **kw: real(**kw, status='invalid'))
    assert client.post(BASE + '/exports').status_code == 409
    assert sql.execute('SELECT count(*) FROM jobs').fetchone()[0] == 0
    assert sql.execute('SELECT count(*) FROM job_events').fetchone()[0] == 0


def test_export_permission_csv_and_duplicate_execution(login, sql):
    client = login('alice')
    private = client.post(BASE + '/tickets', json={**PAYLOAD, 'title': '=SUM(1,2)'}).json()
    job_id = create(client)
    runtime.execute_job(job_id)
    runtime.execute_job(job_id)
    result = detail(client, job_id)
    assert result['status'] == 'succeeded' and result['attempts'] == 1
    response = client.get(BASE + '/jobs/' + job_id + '/download')
    assert response.status_code == 200
    assert "'=SUM(1,2)" in response.content.decode('utf-8-sig')
    assert private['id'] in response.text and str(seed_id('ticket-2')) not in response.text
    assert len(list(settings.export_dir.glob('*.csv'))) == 1
    assert len(list(settings.export_dir.glob('*.tmp'))) == 0
    for person in ['bob', 'other', 'admin']:
        client = login(person)
        for suffix in ['', '/download']:
            assert client.get(BASE + '/jobs/' + job_id + suffix).status_code == 404
        assert client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason': 'forged'}).status_code == 404


def test_temporary_failure_recovers_with_persisted_attempts(login, monkeypatch):
    client = login()
    job_id = create(client)
    real = runtime.build_export
    monkeypatch.setattr(runtime, 'build_export', lambda *_: (_ for _ in ()).throw(OSError('temporary')))
    runtime.execute_job(job_id)
    assert detail(client, job_id)['status'] == 'queued'
    runtime.execute_job(job_id)
    assert detail(client, job_id)['attempts'] == 1  # A duplicate message cannot skip backoff.
    due(job_id)
    monkeypatch.setattr(runtime, 'build_export', real)
    runtime.execute_job(job_id)
    result = detail(client, job_id)
    assert result['status'] == 'succeeded' and result['attempts'] == 2


def test_execution_exhaustion_and_audited_manual_retry(login, monkeypatch):
    client = login()
    job_id = create(client)
    real = runtime.build_export
    monkeypatch.setattr(runtime, 'build_export', lambda *_: (_ for _ in ()).throw(OSError('persistent')))
    for _ in range(5):
        due(job_id)
        runtime.execute_job(job_id)
    result = detail(client, job_id)
    assert result['status'] == 'failed' and result['attempts'] == result['run_attempts'] == 3
    runtime.reconcile()
    assert detail(client, job_id)['attempts'] == 3
    assert client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason': ''}).status_code == 422
    assert client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason': '已恢复磁盘写入'}).status_code == 200
    monkeypatch.setattr(runtime, 'build_export', real)
    runtime.execute_job(job_id)
    result = detail(client, job_id)
    assert result['generation'] == 2 and result['attempts'] == 4 and result['run_attempts'] == 1 and result['status'] == 'succeeded'
    assert any(e['kind'] == 'manual_retry' and e['detail']['reason'] == '已恢复磁盘写入' for e in result['events'])


def test_delivery_failure_exhaustion_and_manual_recovery(login):
    client = login()
    job_id = create(client)
    def broken(_):
        raise ConnectionError('queue down')
    for _ in range(7):
        due(job_id)
        runtime.dispatch_once(broken)
    result = detail(client, job_id)
    assert result['status'] == 'failed' and result['error_code'] == 'DELIVERY_EXHAUSTED'
    assert result['delivery_attempts'] == result['delivery_run_attempts'] == 5
    assert result['attempts'] == 0
    assert client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason':'队列恢复'}).status_code == 200
    delivered = []
    runtime.dispatch_once(delivered.append)
    assert delivered == [job_id]
    runtime.execute_job(delivered[0])
    assert detail(client, job_id)['status'] == 'succeeded'
    assert detail(client, job_id)['delivery_attempts'] == 6


def test_missing_worker_redelivery_and_lease_recovery(login):
    client = login()
    job_id = create(client)
    messages = []
    runtime.dispatch_once(messages.append)
    due(job_id)
    runtime.dispatch_once(messages.append)
    assert messages == [job_id, job_id]
    with runtime.Sessions.begin() as db:
        job = db.get(Job, UUID(job_id))
        job.status, job.attempts, job.run_attempts = 'running', 1, 1
        job.lease_until = runtime.now() - timedelta(seconds=1)
    runtime.reconcile()
    assert detail(client, job_id)['status'] == 'queued'
    assert detail(client, job_id)['attempts'] == 1
    due(job_id)
    runtime.execute_job(job_id)
    runtime.execute_job(job_id)
    assert detail(client, job_id)['status'] == 'succeeded'
    assert detail(client, job_id)['attempts'] == 2


def test_stale_worker_cannot_publish_over_new_claim(login, monkeypatch):
    client = login()
    job_id = create(client)
    started, resume = Event(), Event()
    real = runtime.build_export
    def paused(job, path):
        real(job, path)
        started.set()
        assert resume.wait(8)
    monkeypatch.setattr(runtime, 'build_export', paused)
    with ThreadPoolExecutor(1) as pool:
        first = pool.submit(runtime.execute_job, job_id)
        assert started.wait(8)
        with runtime.Sessions.begin() as db:
            db.get(Job, UUID(job_id)).lease_until = runtime.now() - timedelta(seconds=1)
        runtime.reconcile()
        due(job_id)
        monkeypatch.setattr(runtime, 'build_export', real)
        runtime.execute_job(job_id)
        content = (settings.export_dir / f'{job_id}.csv').read_bytes()
        resume.set()
        first.result(timeout=8)
    assert (settings.export_dir / f'{job_id}.csv').read_bytes() == content
    result = detail(client, job_id)
    assert result['attempts'] == 2
    assert sum(e['kind'] == 'succeeded' for e in result['events']) == 1


@pytest.mark.parametrize('point', ['before', 'during', 'download'])
def test_export_rechecks_current_permissions(login, sql, monkeypatch, point):
    client = login('agent')
    job_id = create(client)
    real = runtime.build_export
    def revoke():
        sql.execute("UPDATE memberships SET role='requester' WHERE user_id=%s", (seed_id('agent'),))
    if point == 'before':
        revoke()
    elif point == 'during':
        def changed(job, path):
            real(job, path)
            revoke()
        monkeypatch.setattr(runtime, 'build_export', changed)
    runtime.execute_job(job_id)
    if point == 'download':
        revoke()
        assert client.get(BASE + '/jobs/' + job_id + '/download').status_code == 403
    else:
        result = detail(client, job_id)
        assert result['status'] == 'failed' and result['error_code'] == 'PERMISSION_REVOKED'


def test_expiry_and_quota(login):
    client = login()
    job_id = create(client)
    runtime.execute_job(job_id)
    with runtime.Sessions.begin() as db:
        db.get(Job, UUID(job_id)).expires_at = runtime.now() - timedelta(seconds=1)
    assert client.get(BASE + '/jobs/' + job_id + '/download').status_code == 410
    runtime.reconcile()
    assert detail(client, job_id)['status'] == 'expired'
    for _ in range(5):
        create(client)
    assert client.post(BASE + '/exports').status_code == 429


def test_retry_quota_serializes_concurrent_requests(login):
    client = login()
    failed = [create(client), create(client)]
    with runtime.Sessions.begin() as db:
        for job_id in failed:
            runtime.fail(db, db.get(Job, UUID(job_id)), 'EXPORT_ERROR')
    for _ in range(4):
        create(client)
    barrier = Barrier(2)
    def retry(job_id):
        barrier.wait(timeout=8)
        return client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason': '故障已恢复'})
    with ThreadPoolExecutor(2) as pool:
        responses = list(pool.map(retry, failed))
    assert sorted(r.status_code for r in responses) == [200, 429]
    rejected = failed[next(i for i, r in enumerate(responses) if r.status_code == 429)]
    assert detail(client, rejected)['generation'] == 1
    assert client.post(BASE + '/exports').status_code == 429


@pytest.mark.parametrize('status', ['queued', 'succeeded'])
def test_expiry_without_scanner_allows_recovery_and_releases_quota(login, status):
    client = login()
    job_id = create(client)
    if status == 'succeeded':
        runtime.execute_job(job_id)
    with runtime.Sessions.begin() as db:
        db.get(Job, UUID(job_id)).expires_at = runtime.now() - timedelta(seconds=1)
    assert detail(client, job_id)['status'] == 'expired'
    assert client.get(BASE + '/jobs').json()['items'][0]['status'] == 'expired'
    assert client.get(BASE + '/jobs/' + job_id + '/download').status_code == 410
    for _ in range(5):
        create(client)
    assert client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason': '重新生成'}).status_code == 429
    with runtime.Sessions.begin() as db:
        queued = db.scalar(select(Job).where(Job.id != UUID(job_id), Job.status == 'queued').limit(1))
        runtime.fail(db, queued, 'EXPORT_ERROR')
    assert client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason': '重新生成'}).status_code == 200
    assert detail(client, job_id)['generation'] == 2


def test_empty_pages_keep_scoped_total(login):
    client = login('alice')
    create(client)
    assert client.get(BASE + '/jobs?page=99').json() == {'items': [], 'total': 1}
    assert client.post(BASE + '/tickets/' + TICKET + '/comments', json={'body': '分页记录'}).status_code == 201
    first = client.get(BASE + '/tickets/' + TICKET + '/activity').json()
    assert first['total'] > 0
    assert client.get(BASE + '/tickets/' + TICKET + '/activity?page=99').json() == {'items': [], 'total': first['total']}
    login('bob')
    assert client.get(BASE + '/jobs?page=99').json() == {'items': [], 'total': 0}
    assert client.get(BASE + '/tickets/' + TICKET + '/activity?page=99').status_code == 404


def test_cleanup_holds_publication_lock_until_file_removed(login, monkeypatch):
    import os
    client = login()
    job_id = create(client)
    runtime.execute_job(job_id)
    path = settings.export_dir / f'{job_id}.csv'
    old = runtime.now().timestamp() - runtime.LEASE_SECONDS * 3
    os.utime(path, (old, old))
    with runtime.Sessions.begin() as db:
        db.get(Job, UUID(job_id)).expires_at = runtime.now() - timedelta(seconds=1)
    deleting, resume = Event(), Event()
    real_unlink = Path.unlink
    def paused_unlink(self, *args, **kwargs):
        if self == path:
            deleting.set()
            assert resume.wait(8)
        return real_unlink(self, *args, **kwargs)
    monkeypatch.setattr(Path, 'unlink', paused_unlink)
    with ThreadPoolExecutor(1) as pool:
        cleanup = pool.submit(runtime.reconcile)
        try:
            assert deleting.wait(8)
            # A separate real PostgreSQL connection cannot retry/publish during deletion.
            with pytest.raises(OperationalError) as locked:
                with runtime.Sessions.begin() as db:
                    db.scalar(select(Job).where(Job.id == UUID(job_id)).with_for_update(nowait=True))
            assert locked.value.orig.sqlstate == '55P03'
        finally:
            resume.set()
        cleanup.result(timeout=8)
    assert not path.exists()
    assert client.post(BASE + '/jobs/' + job_id + '/retry', json={'reason': '更新导出'}).status_code == 200
    runtime.execute_job(job_id)
    runtime.reconcile()
    assert client.get(BASE + '/jobs/' + job_id + '/download').status_code == 200


def test_export_expiring_during_build_is_not_published(login, monkeypatch):
    client = login()
    job_id = create(client)
    real_build = runtime.build_export
    def expire(job, path):
        real_build(job, path)
        with runtime.Sessions.begin() as db:
            db.get(Job, job.id).expires_at = runtime.now() - timedelta(seconds=1)
    monkeypatch.setattr(runtime, 'build_export', expire)
    runtime.execute_job(job_id)
    assert detail(client, job_id)['status'] == 'expired'
    assert not list(settings.export_dir.iterdir())


def test_integration_scopes_hash_revoke_and_role_intersection(login, client, sql):
    login('alice')
    response = client.post(BASE + '/integration-tokens', json={'name':'DocPilot','scopes':['tickets:read','tickets:create','tickets:comment'],'days':7})
    assert response.status_code == 201
    token = response.json()
    listing = client.get(BASE + '/integration-tokens').json()
    assert 'token' not in listing[0] and 'token_hash' not in listing[0]
    assert sql.execute('SELECT token_hash FROM integration_tokens').fetchone()[0] != token['token']
    client.cookies.clear()
    headers = {'Authorization':'Bearer ' + token['token']}
    client.headers.pop('origin')
    client.headers.pop('x-csrf-token')
    assert client.get(BASE + '/tickets', headers=headers).json()['total'] == 1
    assert client.get(BASE + '/tickets/' + str(seed_id('ticket-2')), headers=headers).status_code == 404
    assert client.post(BASE + '/tickets', json=PAYLOAD, headers=headers).status_code == 201
    assert client.post(BASE + '/tickets', json={**PAYLOAD,'assignee_id':str(seed_id('agent'))}, headers=headers).status_code == 403
    assert client.post(BASE + '/tickets/' + TICKET + '/comments', json={'body':'API comment'}, headers=headers).status_code == 201
    assert client.post(BASE + '/tickets/' + TICKET + '/transitions', json={'version':1,'status':'cancelled','reason':'forged'}, headers=headers).status_code == 403
    assert client.post(BASE + '/integration-tokens', json={'name':'forged','scopes':['tickets:read']}, headers=headers).status_code == 403
    sql.execute('UPDATE memberships SET is_active=false WHERE user_id=%s', (seed_id('alice'),))
    assert client.get(BASE + '/tickets', headers=headers).status_code == 404
    sql.execute('UPDATE memberships SET is_active=true WHERE user_id=%s', (seed_id('alice'),))
    client.headers['origin'] = 'http://127.0.0.1:5173'
    login('alice')
    assert client.delete(BASE + '/integration-tokens/' + token['id']).status_code == 204
    assert client.get(BASE + '/tickets', headers=headers).status_code == 401


def test_read_only_token_expiry_workspace_and_cookie_csrf(login, sql):
    client = login()
    token = client.post(BASE + '/integration-tokens', json={'name':'readonly','scopes':['tickets:read']}).json()
    headers = {'Authorization':'Bearer ' + token['token']}
    assert client.post(BASE + '/tickets', json=PAYLOAD, headers=headers).status_code == 403
    assert client.get('/api/v1/workspaces/' + str(seed_id('support')) + '/tickets', headers=headers).status_code == 404
    client.headers['x-csrf-token'] = 'bad'
    assert client.post(BASE + '/tickets', json=PAYLOAD).status_code == 403
    sql.execute('UPDATE integration_tokens SET expires_at=now() - interval \'1 day\'')
    assert client.get(BASE + '/tickets', headers=headers).status_code == 401


def test_login_redis_outage_fails_closed(client, monkeypatch):
    from app import rate_limit
    from redis.exceptions import ConnectionError
    class Unavailable:
        async def eval(self, *args):
            raise ConnectionError('unavailable')
        async def aclose(self):
            pass
    monkeypatch.setattr(settings, 'rate_limit_enabled', True)
    monkeypatch.setattr(rate_limit.Redis, 'from_url', lambda *a, **kw: Unavailable())
    response = client.post('/api/v1/auth/login', json={'email':'admin@flowdesk.example','password':'anything'})
    assert response.status_code == 503 and response.json()['code'] == 'UNAVAILABLE'
