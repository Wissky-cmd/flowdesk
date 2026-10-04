"""Real HTTP + PostgreSQL benchmark. Requires an EMPTY, dedicated *_perf_test DB."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import logging
import math
import os
from pathlib import Path
import platform
import secrets
import subprocess
import sys
import time

import httpx
import psycopg
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))
url = os.environ.get('PERF_DATABASE_URL', '')
if not url or not (make_url(url).database or '').endswith('_perf_test'):
    raise SystemExit('PERF_DATABASE_URL must name an EMPTY dedicated *_perf_test PostgreSQL database')
if url in (os.environ.get('DATABASE_URL'), os.environ.get('TEST_DATABASE_URL')):
    raise SystemExit('Performance database must be separate from development and regression databases')
dsn = url.replace('postgresql+psycopg://', 'postgresql://', 1)
with psycopg.connect(dsn) as db:
    if db.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public'").fetchone()[0]:
        raise SystemExit('Refusing to modify a nonempty performance database; create a new one')
password = secrets.token_urlsafe(24)
os.environ.update(DATABASE_URL=url, RATE_LIMIT_ENABLED='false', COOKIE_SECURE='false', SEED_PASSWORD=password,
                  PYTHONPATH=str(ROOT / 'backend'), EXPORT_DIR=str(ROOT / '.local/perf-exports'))
ROOT.joinpath('.local').mkdir(exist_ok=True)
with (ROOT / '.local/performance-setup.log').open('w') as log:
    subprocess.run([sys.executable, '-m', 'alembic', '-c', 'backend/alembic.ini', 'upgrade', 'head'], cwd=ROOT, check=True, stdout=log, stderr=log)
from app.seed import seed, seed_id
from app.runtime import loop_factory
asyncio.run(seed(), loop_factory=loop_factory)
product, support = seed_id('product'), seed_id('support')
with psycopg.connect(dsn) as db:
    # 80k product / 20k support; requester Alice owns 8k generated product tickets.
    db.execute("""INSERT INTO tickets (id,workspace_id,creator_id,assignee_id,title,body,status,priority,created_at,updated_at)
      SELECT gen_random_uuid(), CASE WHEN n<=80000 THEN %(product)s::uuid ELSE %(support)s::uuid END,
      CASE WHEN n>80000 THEN %(other)s::uuid WHEN n%%10=0 THEN %(alice)s::uuid ELSE %(bob)s::uuid END,
      CASE WHEN n<=80000 AND n%%3=0 THEN %(agent)s::uuid ELSE NULL END,
      'Performance request ' || n || CASE WHEN n%%100=0 THEN ' needle' ELSE '' END,
      repeat(md5(n::text),32),
      (ARRAY['new','accepted','in_progress','review','closed','cancelled'])[1+n%%6],
      (ARRAY['low','normal','high','urgent'])[1+n%%4],
      now() - n * interval '1 minute', now() - n * interval '1 minute'
      FROM generate_series(1,100000) n""", {name:seed_id(name) for name in ['product','support','other','alice','bob','agent']})
    db.execute('ANALYZE tickets')
    report = {'timestamp':datetime.now(timezone.utc).isoformat(), 'platform':platform.platform(), 'python':platform.python_version(),
              'postgresql':db.execute('SHOW server_version').fetchone()[0], 'tickets':db.execute('SELECT count(*) FROM tickets').fetchone()[0],
              'body_bytes_per_generated_ticket':1024, 'method':'Real loopback HTTP, warm samples, 1 and 8 concurrent clients; no production capacity claim.',
              'plans':{}, 'http':{}}
    queries = {
        'list_first':'SELECT t.*, p.total FROM tickets t JOIN (SELECT id, count(*) OVER() total FROM tickets WHERE workspace_id=%s ORDER BY updated_at DESC,id DESC LIMIT 20) p ON t.id=p.id ORDER BY t.updated_at DESC,t.id DESC',
        'list_deep':'SELECT t.*, p.total FROM tickets t JOIN (SELECT id, count(*) OVER() total FROM tickets WHERE workspace_id=%s ORDER BY updated_at DESC,id DESC OFFSET 60000 LIMIT 20) p ON t.id=p.id ORDER BY t.updated_at DESC,t.id DESC',
        'search':"SELECT t.*, p.total FROM tickets t JOIN (SELECT id, count(*) OVER() total FROM tickets WHERE workspace_id=%s AND (title ILIKE '%%needle%%' OR id::text ILIKE '%%needle%%') ORDER BY updated_at DESC,id DESC LIMIT 20) p ON t.id=p.id ORDER BY t.updated_at DESC,t.id DESC",
        'summary':'SELECT status,priority,count(*) FROM tickets WHERE workspace_id=%s GROUP BY status,priority',
    }
    for name, query in queries.items():
        report['plans'][name] = db.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query,(product,)).fetchone()[0]

port = int(os.environ.get('PERF_PORT','18001'))
origin = f'http://127.0.0.1:{port}'
server_code = f"import asyncio,uvicorn; from app.runtime import loop_factory; asyncio.run(uvicorn.Server(uvicorn.Config('app.main:app',host='127.0.0.1',port={port},loop='none')).serve(),loop_factory=loop_factory)"
flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
def summary(values, elapsed):
    ordered = sorted(values)
    return {'samples':len(values), 'p50_ms':round(ordered[math.ceil(len(values)*.5)-1],2),
            'p95_ms':round(ordered[math.ceil(len(values)*.95)-1],2), 'max_ms':round(max(values),2),
            'requests_per_second':round(len(values)/elapsed,2)}

with (ROOT / '.local/performance-api.log').open('w',encoding='utf-8') as log:
    server = subprocess.Popen([sys.executable,'-c',server_code],cwd=ROOT,stdout=log,stderr=log,creationflags=flags)
    try:
        with httpx.Client(base_url=origin,timeout=60,headers={'origin':'http://127.0.0.1:5173'}) as client:
            for _ in range(60):
                if server.poll() is not None:
                    raise RuntimeError('Benchmark API failed to start; see private local log')
                try:
                    if client.get('/api/v1/health').status_code == 200: break
                except httpx.ConnectError: pass
                time.sleep(.5)
            else: raise RuntimeError('Benchmark API readiness timed out')
            auth = client.post('/api/v1/auth/login',json={'email':'admin@flowdesk.example','password':password})
            auth.raise_for_status()
            client.headers['x-csrf-token'] = auth.json()['csrf_token']
            base = f'/api/v1/workspaces/{product}'
            cases = {'first_page':'/tickets','deep_page':'/tickets?page=3001', 'search':'/tickets?q=needle',
                     'status_filter':'/tickets?status=in_progress', 'assignee_filter':f'/tickets?assignee_id={seed_id("agent")}', 'summary':'/tickets/summary'}
            for name, suffix in cases.items():
                def request(_):
                    started = time.perf_counter()
                    response = client.get(base+suffix)
                    response.raise_for_status()
                    payload = response.json()
                    assert payload['total'] > 0
                    if 'items' in payload:
                        assert all(t['workspace_id']==str(product) for t in payload['items'])
                    return (time.perf_counter()-started)*1000
                cold = request(0)
                report['http'][name] = {'first_request_ms':round(cold,2)}
                for concurrency in [1,8]:
                    started = time.perf_counter()
                    with ThreadPoolExecutor(concurrency) as pool:
                        values = list(pool.map(request,range(40)))
                    report['http'][name][str(concurrency)] = summary(values,time.perf_counter()-started)
            # Exercise the real export function and HTTP download at both sides of its cap.
            from app.job_runtime import execute_job
            job = client.post(base+'/exports').json()
            execute_job(job['id'])
            assert client.get(base+'/jobs/'+job['id']).json()['error_code']=='EXPORT_ROW_LIMIT'
            client.cookies.clear()
            auth = client.post('/api/v1/auth/login',json={'email':'alice@flowdesk.example','password':password})
            auth.raise_for_status()
            client.headers['x-csrf-token'] = auth.json()['csrf_token']
            job = client.post(base+'/exports').json()
            started = time.perf_counter()
            execute_job(job['id'])
            response = client.get(base+'/jobs/'+job['id']+'/download')
            response.raise_for_status()
            import csv, io
            rows = list(csv.reader(io.StringIO(response.content.decode('utf-8-sig'))))
            assert len(rows)==8002 and all(row[4]==str(seed_id('alice')) for row in rows[1:])
            report['export']={'rows':len(rows)-1,'build_and_http_download_ms':round((time.perf_counter()-started)*1000,2),
                              'bytes':len(response.content),'over_limit_rejected':True,'requester_isolation':True}
    finally:
        server.terminate()
        try: server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill(); server.wait()

report['budget']={'p95_ms':1000,'concurrency':8,'passed':all(v['8']['p95_ms']<=1000 for v in report['http'].values())}
target=ROOT/'docs/evidence/performance.json'
target.parent.mkdir(parents=True,exist_ok=True)
target.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps({'tickets':report['tickets'],'p95_ms_at_8':{k:v['8']['p95_ms'] for k,v in report['http'].items()},'export':report['export'],'budget':report['budget']}))
if not report['budget']['passed']: raise SystemExit('Performance budget exceeded; inspect performance.json')
