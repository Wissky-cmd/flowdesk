import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_db
from .models import LoginSession, User

DB = Annotated[AsyncSession, Depends(get_db)]
COOKIE = 'flowdesk_session'


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def csrf_token(token: str) -> str:
    return hmac.new(token.encode(), b'flowdesk-csrf-v1', hashlib.sha256).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    key = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2**14, r=8, p=1)
    return f'scrypt${salt}${key.hex()}'


def verify_password(password: str, encoded: str) -> bool:
    _, salt, expected = encoded.split('$')
    actual = hashlib.scrypt(password.encode(), salt=salt.encode(), n=2**14, r=8, p=1).hex()
    return hmac.compare_digest(actual, expected)


async def current_user(request: Request, db: DB) -> User:
    token = request.cookies.get(COOKIE, '')
    result = await db.execute(select(User, LoginSession).join(LoginSession, LoginSession.user_id == User.id).where(
        LoginSession.token_hash == digest(token), LoginSession.revoked_at.is_(None),
        LoginSession.expires_at > datetime.now(timezone.utc), User.is_active.is_(True),
    ))
    row = result.first()
    if row is None:
        raise HTTPException(401, '请先登录，或重新登录已过期的会话')
    if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
        if not hmac.compare_digest(request.headers.get('x-csrf-token', ''), csrf_token(token)):
            raise HTTPException(403, 'CSRF 校验失败，请刷新页面')
    request.state.login_session = row[1]
    return row[0]


CurrentUser = Annotated[User, Depends(current_user)]
