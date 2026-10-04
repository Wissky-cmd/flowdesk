from fastapi import HTTPException, Request
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .config import settings
from .security import digest

# Increment and expiry are indivisible, including the first request in a window.
COUNTER = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return {count, redis.call('TTL', KEYS[1])}
"""


async def check_login_limit(request: Request, email: str):
    if not settings.rate_limit_enabled:
        return
    client = Redis.from_url(settings.redis_url, socket_connect_timeout=1, socket_timeout=1)
    try:
        # Do not trust arbitrary forwarded headers. Uvicorn trusts only the configured proxy.
        for subject in ('ip:' + (request.client.host if request.client else 'unknown'), 'account:' + email.strip().lower()):
            count, ttl = await client.eval(COUNTER, 1, 'flowdesk:login:' + digest(subject), settings.login_window_seconds)
            if count > settings.login_limit:
                raise HTTPException(429, '登录尝试过于频繁，请稍后重试', headers={'Retry-After': str(max(ttl, 1))})
    except RedisError:
        # Fail closed for login. Existing sessions remain usable during Redis outages.
        raise HTTPException(503, '登录保护服务暂时不可用，请稍后重试')
    finally:
        await client.aclose()
