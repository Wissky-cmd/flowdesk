import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from .models import IntegrationToken, User
from .security import DB, CurrentUser, current_user, digest
from .workspaces import require_member

router = APIRouter(prefix='/workspaces/{wid}/integration-tokens')
Scope = Literal['tickets:read', 'tickets:create', 'tickets:comment']


class TokenInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=80)
    scopes: list[Scope] = Field(min_length=1, max_length=3)
    days: int = Field(default=30, ge=1, le=90)


@router.get('')
async def list_tokens(wid: UUID, db: DB, user: CurrentUser):
    await require_member(db, wid, user.id)
    rows = (await db.scalars(select(IntegrationToken).where(IntegrationToken.workspace_id == wid, IntegrationToken.user_id == user.id).order_by(IntegrationToken.created_at.desc()))).all()
    return [{'id': t.id, 'name': t.name, 'scopes': t.scopes, 'expires_at': t.expires_at, 'revoked_at': t.revoked_at} for t in rows]


@router.post('', status_code=201)
async def create_token(wid: UUID, data: TokenInput, db: DB, user: CurrentUser):
    await require_member(db, wid, user.id)
    token = 'fd_' + secrets.token_urlsafe(32)
    row = IntegrationToken(workspace_id=wid, user_id=user.id, name=data.name, token_hash=digest(token), scopes=sorted(set(data.scopes)), expires_at=datetime.now(timezone.utc) + timedelta(days=data.days))
    db.add(row)
    await db.commit()
    return {'id': row.id, 'token': token, 'expires_at': row.expires_at}


@router.delete('/{token_id}', status_code=204)
async def revoke_token(wid: UUID, token_id: UUID, db: DB, user: CurrentUser):
    await require_member(db, wid, user.id)
    row = await db.scalar(select(IntegrationToken).where(IntegrationToken.id == token_id, IntegrationToken.workspace_id == wid, IntegrationToken.user_id == user.id))
    if not row:
        raise HTTPException(404, '令牌不存在')
    row.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def ticket_user(request: Request, db: DB) -> User:
    authorization = request.headers.get('authorization')
    if not authorization:
        return await current_user(request, db)
    if not authorization.startswith('Bearer '):
        raise HTTPException(401, '令牌无效')
    row = (await db.execute(select(IntegrationToken, User).join(User, User.id == IntegrationToken.user_id).where(
        IntegrationToken.token_hash == digest(authorization[7:]), IntegrationToken.revoked_at.is_(None),
        IntegrationToken.expires_at > datetime.now(timezone.utc), User.is_active.is_(True),
    ))).first()
    if not row:
        raise HTTPException(401, '令牌无效或已失效')
    token, user = row
    if str(token.workspace_id) != request.path_params['wid']:
        raise HTTPException(404, '工作空间或资源不存在')
    await require_member(db, token.workspace_id, user.id)
    scope = 'tickets:read' if request.method == 'GET' else 'tickets:create' if request.method == 'POST' and 'ticket_id' not in request.path_params else 'tickets:comment' if request.method == 'POST' and request.url.path.endswith('/comments') else None
    if scope not in token.scopes:
        raise HTTPException(403, '令牌未授权此操作')
    request.state.integration_token_id = token.id
    return user


TicketUser = Annotated[User, Depends(ticket_user)]
