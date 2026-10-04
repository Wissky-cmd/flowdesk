"""Local PostgreSQL snapshot + export volume recovery drill; never overwrites a DB.

Uses project-local credentials on Windows. Backups contain secrets and stay in .local.
For production stop writers, pg_dump -Fc, copy export volume, restore into an empty DB.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import psycopg
from psycopg import sql
from dotenv import dotenv_values
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))


def inventory(conn):
    tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
    counts = {name: conn.execute(sql.SQL('SELECT count(*) FROM {}').format(sql.Identifier(name))).fetchone()[0] for name in tables}
    files = {str(row[0]): hashlib.sha256(bytes(row[1])).hexdigest() for row in conn.execute('SELECT id,content FROM attachments ORDER BY id')}
    return {'counts': counts, 'attachment_sha256': files, 'revision': conn.execute('SELECT version_num FROM alembic_version').fetchone()[0]}


def verify_api():
    from fastapi.testclient import TestClient
    from app.main import app
    from app.runtime import loop_factory
    with TestClient(app, backend_options={'loop_factory': loop_factory}, headers={'origin':'http://127.0.0.1:5173'}) as client:
        response = client.post('/api/v1/auth/login', json={'email':'admin@flowdesk.example', 'password':os.environ['SEED_PASSWORD']})
        assert response.status_code == 200
        client.headers['x-csrf-token'] = response.json()['csrf_token']
        me = client.get('/api/v1/me').json()
        wid = next(w['id'] for w in me['workspaces'] if w['name'] == '产品与研发')
        tickets = client.get(f'/api/v1/workspaces/{wid}/tickets').json()
        assert tickets['total'] > 0
        dsn = os.environ['DATABASE_URL'].replace('postgresql+psycopg://','postgresql://',1)
        with psycopg.connect(dsn) as db:
            attachments = db.execute('SELECT id,ticket_id,content FROM attachments WHERE workspace_id=%s', (wid,)).fetchall()
            exports = db.execute("SELECT id FROM jobs WHERE workspace_id=%s AND owner_id=%s AND status='succeeded' AND expires_at>now()", (wid,me['id'])).fetchall()
        assert attachments, 'Drill requires at least one attachment'
        for attachment_id, ticket_id, content in attachments:
            response = client.get(f'/api/v1/workspaces/{wid}/tickets/{ticket_id}/attachments/{attachment_id}')
            assert response.status_code == 200 and response.content == bytes(content)
        for job_id, in exports:
            assert client.get(f'/api/v1/workspaces/{wid}/jobs/{job_id}/download').status_code == 200
        print(json.dumps({'login': 'passed', 'ticket_read': 'passed', 'attachments_downloaded': len(attachments), 'exports_downloaded': len(exports)}))


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    target_name = 'flowdesk_restore_' + stamp + '_test'
    folder = ROOT / '.local/backups' / stamp
    folder.mkdir(parents=True, exist_ok=False)
    credentials = json.loads((ROOT / '.local/credentials.json').read_text())
    source_url = make_url(dotenv_values(ROOT / '.env')['DATABASE_URL'])
    if source_url.host != '127.0.0.1' or source_url.database != 'flowdesk':
        raise SystemExit('This local drill only supports the project flowdesk database on loopback')
    env = {**os.environ, 'PGHOST': source_url.host, 'PGPORT': str(source_url.port), 'PGUSER': source_url.username, 'PGPASSWORD': source_url.password}
    source_dsn = source_url.set(drivername='postgresql').render_as_string(hide_password=False)
    flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
    binary = ROOT / '.local/pgsql/bin'
    with psycopg.connect(source_dsn) as conn:
        conn.execute("SET LOCAL lock_timeout='10s'")
        tables = [r[0] for r in conn.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")]
        conn.execute(sql.SQL('LOCK TABLE {} IN SHARE MODE').format(sql.SQL(',').join(map(sql.Identifier, tables))))
        if conn.execute("SELECT count(*) FROM jobs WHERE status='running'").fetchone()[0]:
            raise SystemExit('Wait for running jobs before taking a consistent DB + volume snapshot')
        snapshot = conn.execute('SELECT pg_export_snapshot()').fetchone()[0]
        before = inventory(conn)
        subprocess.run([str(binary / 'pg_dump.exe'), '-Fc', '--no-owner', '--no-acl', '--snapshot', snapshot, '--file', str(folder / 'database.dump'), source_url.database], env=env, check=True, creationflags=flags)
        export_files = conn.execute("SELECT result_key FROM jobs WHERE status='succeeded' AND result_key IS NOT NULL").fetchall()
        restored_exports = folder / 'exports'
        restored_exports.mkdir()
        hashes = {}
        for key, in export_files:
            if '/' in key or '\\' in key:
                raise RuntimeError('Invalid stored result key')
            source = ROOT / '.local/exports' / key
            shutil.copy2(source, restored_exports / key)
            hashes[key] = hashlib.sha256(source.read_bytes()).hexdigest()
    with psycopg.connect(host=source_url.host, port=source_url.port, dbname='postgres', user='flowdesk_admin', password=credentials['admin'], autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {} OWNER {}').format(sql.Identifier(target_name), sql.Identifier(source_url.username)))
    subprocess.run([str(binary / 'pg_restore.exe'), '--exit-on-error', '--no-owner', '--no-acl', '--dbname', target_name, str(folder / 'database.dump')], env=env, check=True, creationflags=flags)
    restored_url = source_url.set(database=target_name)
    with psycopg.connect(restored_url.set(drivername='postgresql').render_as_string(hide_password=False)) as conn:
        after = inventory(conn)
    assert before == after
    assert all(hashlib.sha256((restored_exports / key).read_bytes()).hexdigest() == value for key, value in hashes.items())
    verify_env = {**os.environ, 'DATABASE_URL': restored_url.render_as_string(hide_password=False), 'COOKIE_SECURE':'false', 'RATE_LIMIT_ENABLED':'false', 'SEED_PASSWORD': credentials['seed'], 'EXPORT_DIR': str(restored_exports)}
    result = subprocess.run([sys.executable, __file__, '--verify'], env=verify_env, check=True, capture_output=True, text=True, encoding='utf-8', creationflags=flags)
    report = {'executed_at': datetime.now(timezone.utc).isoformat(), 'source':'flowdesk', 'restored_database':target_name, 'snapshot_and_write_lock':True, 'inventory_matches':True, **before, 'export_sha256':hashes, 'api':json.loads(result.stdout.strip().splitlines()[-1]), 'backup_sha256':hashlib.sha256((folder / 'database.dump').read_bytes()).hexdigest()}
    (ROOT / 'docs/evidence/backup-restore.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('restored_database','inventory_matches','api')}, ensure_ascii=False))


if __name__ == '__main__':
    verify_api() if '--verify' in sys.argv else main()
