"""Run migration roundtrip only on the explicitly configured disposable test DB."""
import asyncio
import json
import os
from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
import psycopg
from sqlalchemy.engine import make_url

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'backend'))
values = dotenv_values(root / '.env')
test_url = os.environ.get('TEST_DATABASE_URL') or values['TEST_DATABASE_URL']
dev_url = os.environ.get('DATABASE_URL') or values['DATABASE_URL']
if test_url == dev_url or not make_url(test_url).database.endswith('_test'):
    raise SystemExit('Refusing to modify a database not explicitly isolated for testing')
os.environ['DATABASE_URL'] = test_url
config = Config(str(root / 'backend/alembic.ini'))
command.downgrade(config, 'base')
command.upgrade(config, 'head')
command.check(config)

from app.seed import seed
from app.runtime import loop_factory

os.environ['SEED_PASSWORD'] = 'temporary-' + os.urandom(16).hex()
asyncio.run(seed(), loop_factory=loop_factory)
dsn = test_url.replace('postgresql+psycopg://', 'postgresql://', 1)


def counts():
    with psycopg.connect(dsn) as conn:
        return {table: conn.execute(psycopg.sql.SQL('SELECT count(*) FROM {}').format(psycopg.sql.Identifier(table))).fetchone()[0] for table in ['users', 'workspaces', 'memberships', 'tickets']}


before = counts()
asyncio.run(seed(), loop_factory=loop_factory)
after = counts()
assert before == after == {'users': 5, 'workspaces': 2, 'memberships': 5, 'tickets': 3}
print(json.dumps({'migration_roundtrip': 'passed', 'seed_idempotence': 'passed', 'before': before, 'after': after}, indent=2))
