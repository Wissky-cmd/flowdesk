"""Project-local PostgreSQL for Windows. Never installs a service or changes PATH."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
BIN = LOCAL / 'pgsql' / 'bin'
DATA = LOCAL / 'pgdata'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def run(*args, **kwargs):
    return subprocess.run([str(a) for a in args], check=True, creationflags=FLAGS, **kwargs)


def main():
    LOCAL.mkdir(exist_ok=True)
    if not BIN.exists():
        archive = LOCAL / 'postgresql.zip'
        expected = 'e2246ba91d22345bc3d017586c09ede52d9df180b1eeb480f050445f1cad84e2'
        if hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest() != expected:
            raise SystemExit('PostgreSQL archive does not match the verified download.')
        with zipfile.ZipFile(archive) as z:
            for entry in z.infolist():
                if entry.filename.startswith(('pgsql/bin/', 'pgsql/lib/', 'pgsql/share/')):
                    target = (LOCAL / entry.filename).resolve()
                    if not target.is_relative_to(LOCAL.resolve()):
                        raise SystemExit('Invalid archive path')
                    z.extract(entry, LOCAL)
    if len(sys.argv) > 1 and sys.argv[1] == 'stop':
        run(BIN / 'pg_ctl.exe', '-D', DATA, 'stop', '-m', 'fast')
        return
    credential_file = LOCAL / 'credentials.json'
    if not credential_file.exists():
        credential_file.write_text(json.dumps({key: secrets.token_urlsafe(24) for key in ['admin', 'database', 'seed']}, indent=2))
    credentials = json.loads(credential_file.read_text())
    if not (DATA / 'PG_VERSION').exists():
        pwfile = LOCAL / 'initdb-password'
        pwfile.write_text(credentials['admin'])
        try:
            run(BIN / 'initdb.exe', '-D', DATA, '-U', 'flowdesk_admin', '--pwfile', pwfile, '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C')
        finally:
            pwfile.unlink(missing_ok=True)
    import psycopg
    from psycopg import sql
    # A sandbox account cannot reliably inspect a server owned by the desktop user.
    # An authenticated connection is the authoritative readiness check.
    try:
        with psycopg.connect(host='127.0.0.1', port=55432, dbname='postgres', user='flowdesk_admin', password=credentials['admin'], connect_timeout=3):
            ready = True
    except psycopg.OperationalError:
        ready = False
    if not ready:
        run(BIN / 'pg_ctl.exe', '-D', DATA, '-l', LOCAL / 'postgresql.log', '-o', '-h 127.0.0.1 -p 55432', '-w', 'start')
    with psycopg.connect(host='127.0.0.1', port=55432, dbname='postgres', user='flowdesk_admin', password=credentials['admin'], autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='flowdesk'").fetchone():
            conn.execute(sql.SQL('CREATE ROLE flowdesk LOGIN PASSWORD {}').format(sql.Literal(credentials['database'])))
        for database in ['flowdesk', 'flowdesk_test']:
            if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s', (database,)).fetchone():
                conn.execute(sql.SQL('CREATE DATABASE {} OWNER flowdesk').format(sql.Identifier(database)))
    if not (ROOT / '.env').exists():
        base = f"postgresql+psycopg://flowdesk:{credentials['database']}@127.0.0.1:55432/"
        (ROOT / '.env').write_text(f'DATABASE_URL={base}flowdesk\nTEST_DATABASE_URL={base}flowdesk_test\nCOOKIE_SECURE=false\n', encoding='utf-8')
    print('PostgreSQL ready at 127.0.0.1:55432; separate flowdesk / flowdesk_test databases.')
    print('Local demo password is in .local/credentials.json (seed); never commit this file.')


if __name__ == '__main__':
    main()
