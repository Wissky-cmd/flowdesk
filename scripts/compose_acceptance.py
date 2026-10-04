"""Boot and destroy a uniquely named disposable Compose stack; never production volumes."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import time
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[1]
project = 'flowdesk-acceptance-' + uuid.uuid4().hex[:10]
local = ROOT / '.local' / project
local.mkdir(parents=True)
env_file = local / '.env'
password = secrets.token_urlsafe(24)
env = {**os.environ, 'POSTGRES_PASSWORD':secrets.token_urlsafe(24), 'POSTGRES_ADMIN_PASSWORD':secrets.token_urlsafe(24),
       'COOKIE_SECURE':'false', 'ALLOWED_ORIGINS':'["http://127.0.0.1:8080"]', 'SEED_PASSWORD':password}
env_file.write_text('\n'.join(f'{k}={env[k]}' for k in ['POSTGRES_PASSWORD','POSTGRES_ADMIN_PASSWORD','COOKIE_SECURE','ALLOWED_ORIGINS']),encoding='utf-8')
os.chmod(env_file,0o600)
command = ['docker','compose','--project-name',project,'--env-file',str(env_file)]
report = {'timestamp':datetime.now(timezone.utc).isoformat(),'project':project,'checks':[],'passed':False}
def compose(*args, capture=False):
    return subprocess.run(command+list(args),cwd=ROOT,env=env,check=True,text=True,
                          stdout=subprocess.PIPE if capture else None,stderr=subprocess.PIPE if capture else None)
def checked(name):
    report['checks'].append(name)
    print('PASS:',name,flush=True)
def ready(client):
    for _ in range(90):
        try:
            if client.get('/api/v1/health').status_code==200: return
        except httpx.TransportError: pass
        time.sleep(1)
    raise AssertionError('Container API readiness timeout')
try:
    compose('config','--quiet')
    compose('up','-d','--build','--wait','--wait-timeout','180')
    compose('exec','-T','-e','SEED_PASSWORD','api','python','-m','app.seed')
    with httpx.Client(base_url='http://127.0.0.1:8080',timeout=15,headers={'origin':'http://127.0.0.1:8080'}) as client:
        ready(client)
        page = client.get('/w/f441fe89-3299-51c1-ab7b-1a23105e255f/board')
        assert page.status_code==200 and '<div id="app">' in page.text
        assert "frame-ancestors 'none'" in page.headers['content-security-policy']
        assert page.headers['x-content-type-options']=='nosniff'
        checked('Nginx SPA fallback and security headers')
        response = client.post('/api/v1/auth/login',json={'email':'admin@flowdesk.example','password':password})
        assert response.status_code==200
        assert 'httponly' in response.headers['set-cookie'].lower()
        client.headers['x-csrf-token']=response.json()['csrf_token']
        base='/api/v1/workspaces/f441fe89-3299-51c1-ab7b-1a23105e255f'
        created=client.post(base+'/tickets',json={'title':'Container acceptance','body':'Disposable stack only','priority':'normal'})
        assert created.status_code==201
        ticket=created.json()['id']
        upload=client.post(base+f'/tickets/{ticket}/attachments?filename=container.txt',content=b'container-persistence',headers={'content-type':'application/octet-stream'})
        assert upload.status_code==201
        attachment=upload.json()['id']
        checked('PostgreSQL migration, authenticated create and attachment upload')
        compose('stop','worker')
        created=client.post(base+'/exports')
        assert created.status_code==202
        job=created.json()['id']
        # Wait for a real dispatcher publication while no consumer exists.
        for _ in range(30):
            detail=client.get(base+'/jobs/'+job).json()
            if any(e['kind']=='delivered' for e in detail['events']): break
            time.sleep(1)
        else: raise AssertionError('Dispatcher never delivered through Redis')
        assert detail['status']=='queued'
        compose('restart','redis')
        compose('up','-d','--wait','--wait-timeout','90','redis')
        compose('start','worker')
        for _ in range(60):
            detail=client.get(base+'/jobs/'+job).json()
            if detail['status']=='succeeded': break
            assert detail['status']!='failed',detail.get('error_code')
            time.sleep(1)
        else: raise AssertionError('Worker recovery timeout')
        download=client.get(base+'/jobs/'+job+'/download')
        assert download.status_code==200 and 'Container acceptance' in download.text
        checked('Real dispatcher/Redis/Celery, absent consumer and Redis restart recovery, shared CSV download')
        compose('restart','api','web','worker','dispatcher')
        ready(client)
        assert client.get(base+'/tickets/'+ticket).status_code==200
        assert client.get(base+f'/tickets/{ticket}/attachments/{attachment}').content==b'container-persistence'
        assert client.get(base+'/jobs/'+job+'/download').content==download.content
        checked('Service restart preserves session, ticket, binary attachment and CSV')
        compose('stop','redis')
        response=client.post('/api/v1/auth/login',json={'email':'outage@example.test','password':'invalid'})
        assert response.status_code==503
        assert client.get(base+'/tickets/'+ticket).status_code==200
        checked('Real Redis outage fails login closed while existing sessions still work')
        compose('up','-d','--wait','--wait-timeout','90','redis')
        for _ in range(12):
            response=client.post('/api/v1/auth/login',json={'email':'limit@example.test','password':'invalid'})
            if response.status_code==429: break
            assert response.status_code==401
        else: raise AssertionError('Real Redis login limit did not activate')
        assert int(response.headers['retry-after'])>=1
        checked('Real Redis HTTP 429 with Retry-After')
        report['job']={'attempts':detail['attempts'],'delivery_attempts':detail['delivery_attempts']}
    report['passed']=True
finally:
    evidence=ROOT/'docs/evidence'
    evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'compose-acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    # Logs can contain deployment connection details: retain locally, do not upload raw logs.
    with (local/'compose.log').open('w',encoding='utf-8') as log:
        subprocess.run(command+['logs','--no-color','--tail','100'],cwd=ROOT,env=env,stdout=log,stderr=log)
    try:
        compose('down','--volumes','--remove-orphans')
    finally:
        env_file.unlink(missing_ok=True)
