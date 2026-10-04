import asyncio
import os
from pathlib import Path
import secrets

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from dotenv import dotenv_values
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]
values = dotenv_values(ROOT / '.env')
url = os.environ.get('TEST_DATABASE_URL') or values.get('TEST_DATABASE_URL')
if not url or not make_url(url).database.endswith('_test'):
    raise RuntimeError('Tests require an explicit PostgreSQL TEST_DATABASE_URL ending in _test')
if url == (os.environ.get('DATABASE_URL') or values.get('DATABASE_URL')):
    raise RuntimeError('Never run destructive test fixtures against the development database')
os.environ['DATABASE_URL'] = url
os.environ['COOKIE_SECURE'] = 'false'
os.environ['RATE_LIMIT_ENABLED'] = 'false'
PASSWORD = secrets.token_urlsafe(20)
os.environ['SEED_PASSWORD'] = PASSWORD

from app.main import app
from app.db import get_db
from app.runtime import loop_factory
from app.seed import seed

DSN = url.replace('postgresql+psycopg://', 'postgresql://', 1)


@pytest.fixture(scope='session', autouse=True)
def migrate():
    command.upgrade(Config(str(ROOT / 'backend/alembic.ini')), 'head')
    command.check(Config(str(ROOT / 'backend/alembic.ini')))


@pytest.fixture(autouse=True)
def reset_database(migrate):
    with psycopg.connect(DSN, autocommit=True) as conn:
        conn.execute('TRUNCATE tickets, sessions, memberships, workspaces, users CASCADE')
    asyncio.run(seed(), loop_factory=loop_factory)


@pytest.fixture
def sql():
    with psycopg.connect(DSN, autocommit=True) as conn:
        yield conn


@pytest.fixture
def client():
    test_engine = create_async_engine(url, poolclass=NullPool)
    factory = async_sessionmaker(test_engine, expire_on_commit=False)
    async def test_db():
        async with factory() as db:
            yield db
    app.dependency_overrides[get_db] = test_db
    with TestClient(app, backend_options={'loop_factory': loop_factory}, headers={'origin': 'http://127.0.0.1:5173'}) as browser:
        yield browser
    app.dependency_overrides.clear()


@pytest.fixture
def login(client):
    def perform(person='admin'):
        client.cookies.clear()
        result = client.post('/api/v1/auth/login', json={'email': f'{person}@flowdesk.example', 'password': PASSWORD})
        assert result.status_code == 200, result.text
        client.headers['x-csrf-token'] = result.json()['csrf_token']
        return client
    return perform
