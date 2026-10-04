"""Runs only against an explicitly configured disposable Redis database (CI uses DB 15)."""
import os
import uuid

import pytest
from redis import Redis
from concurrent.futures import ThreadPoolExecutor

from app.config import settings
from app.rate_limit import COUNTER

URL = os.environ.get('TEST_REDIS_URL')
pytestmark = pytest.mark.skipif(not URL, reason='TEST_REDIS_URL not configured; real Redis unavailable on this host')


def test_real_redis_atomic_counter_window_and_api_429(client, monkeypatch):
    redis = Redis.from_url(URL)
    key = 'flowdesk:test:' + uuid.uuid4().hex
    try:
        with ThreadPoolExecutor(12) as pool:
            results = list(pool.map(lambda _: redis.eval(COUNTER, 1, key, 1), range(24)))
        assert sorted(r[0] for r in results) == list(range(1, 25))
        assert sum(count <= 10 for count, _ in results) == 10
        import time
        time.sleep(1.1)
        assert redis.eval(COUNTER, 1, key, 1)[0] == 1
        monkeypatch.setattr(settings, 'rate_limit_enabled', True)
        monkeypatch.setattr(settings, 'redis_url', URL)
        monkeypatch.setattr(settings, 'login_limit', 1)
        from app.security import digest
        ip_key = 'flowdesk:login:' + digest('ip:testclient')
        account_key = 'flowdesk:login:' + digest('account:rate-' + key + '@example.test')
        redis.delete(ip_key, account_key)
        try:
            data = {'email': 'rate-' + key + '@example.test', 'password': 'wrong'}
            assert client.post('/api/v1/auth/login', json=data).status_code == 401
            response = client.post('/api/v1/auth/login', json=data)
            assert response.status_code == 429 and int(response.headers['retry-after']) >= 1
        finally:
            redis.delete(ip_key, account_key)
    finally:
        redis.delete(key)
        redis.close()
