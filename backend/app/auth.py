import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from .config import settings
from .models import LoginSession, Membership, User, Workspace
from .security import COOKIE, DB, CurrentUser, csrf_token, digest, hash_password, verify_password

router = APIRouter()
DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


class LoginInput(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(min_length=1, max_length=256)


@router.post('/auth/login')
async def login(data: LoginInput, request: Request, response: Response, db: DB):
    user = await db.scalar(select(User).where(User.email == data.email.strip().lower()))
    valid = await run_in_threadpool(verify_password, data.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.is_active:
        raise HTTPException(401, '邮箱或密码错误')
    old_token = request.cookies.get(COOKIE)
    if old_token:
        old = await db.scalar(select(LoginSession).where(LoginSession.token_hash == digest(old_token)))
        if old:
            old.revoked_at = datetime.now(timezone.utc)
    token = secrets.token_urlsafe(32)
    db.add(LoginSession(user_id=user.id, token_hash=digest(token), expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_hours)))
    await db.commit()
    response.set_cookie(COOKIE, token, httponly=True, secure=settings.cookie_secure, samesite='lax', max_age=settings.session_hours * 3600, path='/api')
    return {'csrf_token': csrf_token(token)}


@router.post('/auth/logout', status_code=204)
async def logout(request: Request, response: Response, db: DB, user: CurrentUser):
    request.state.login_session.revoked_at = datetime.now(timezone.utc)
    await db.commit()
    response.delete_cookie(COOKIE, path='/api', secure=settings.cookie_secure, httponly=True, samesite='lax')


@router.get('/me')
async def me(request: Request, db: DB, user: CurrentUser):
    rows = (await db.execute(select(Workspace, Membership.role).join(Membership).where(
        Membership.user_id == user.id, Membership.is_active.is_(True),
    ).order_by(Workspace.name))).all()
    return {'id': user.id, 'name': user.name, 'email': user.email,
            'csrf_token': csrf_token(request.cookies[COOKIE]),
            'workspaces': [{'id': w.id, 'name': w.name, 'role': role} for w, role in rows]}
