"""Real Redis + Linux Celery smoke, against an isolated test database only."""
import os
import json
import subprocess
import sys
import time
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
from sqlalchemy.engine import make_url

test_url = os.environ['TEST_DATABASE_URL']
if not make_url(test_url).database.endswith('_test') or test_url == os.environ.get('DATABASE_URL'):
    raise SystemExit('Requires an isolated *_test database')
if sys.platform == 'win32':
    raise SystemExit('Run this smoke in Linux; Windows execution is not a Linux Worker acceptance')
os.environ['DATABASE_URL'] = test_url
os.environ['EXPORT_DIR'] = str(root / '.local/queue-smoke-exports')
from datetime import timedelta
from app.job_runtime import Sessions, now, dispatch_once
from app.models import Job, OutboxEvent
from app.seed import seed_id
from app.worker import export_csv

with Sessions.begin() as db:
    job = Job(workspace_id=seed_id('product'), owner_id=seed_id('admin'), owner_role='admin', expires_at=now() + timedelta(hours=1))
    db.add(job)
    db.flush()
    db.add(OutboxEvent(job_id=job.id))
job_id = job.id
dispatch_once(lambda value: export_csv.apply_async(args=[value]))
with Sessions() as db:
    assert db.get(Job, job_id).status == 'queued', 'Task should survive worker absence'
env = {**os.environ, 'PYTHONPATH': str(root / 'backend')}
root.joinpath('.local').mkdir(exist_ok=True)
with (root / '.local/queue-smoke.log').open('w') as log:
    worker = subprocess.Popen([sys.executable, '-m', 'celery', '-A', 'app.worker:celery', 'worker', '--loglevel=INFO', '--concurrency=1'], cwd=root, env=env, stdout=log, stderr=log)
    try:
        for _ in range(60):
            with Sessions() as db:
                result = db.get(Job, job_id)
                if result.status == 'succeeded':
                    break
                assert result.status != 'failed', result.error_code
            time.sleep(1)
        else:
            raise AssertionError('Real worker did not complete within 60 seconds')
        export_csv.apply_async(args=[str(job_id)])
        time.sleep(2)
        with Sessions() as db:
            result = db.get(Job, job_id)
            assert result.status == 'succeeded' and result.attempts == 1
        assert len(list(Path(os.environ['EXPORT_DIR']).glob(f'{job_id}.csv'))) == 1
        evidence = root / 'docs/evidence/queue-smoke.json'
        evidence.parent.mkdir(parents=True, exist_ok=True)
        evidence.write_text(json.dumps({'platform': sys.platform, 'passed': True, 'transport': 'redis',
                                       'worker': 'celery prefork', 'checks': ['absent_worker_recovery', 'duplicate_delivery', 'single_artifact'],
                                       'execution_attempts': result.attempts}, indent=2), encoding='utf-8')
        print('PASS: Redis delivery, absent worker recovery, Linux Celery execution, duplicate delivery, one artifact')
    finally:
        worker.terminate()
        try:
            worker.wait(timeout=15)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
