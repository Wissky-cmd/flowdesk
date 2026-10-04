from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from .models import Membership, User, Workspace
from .security import DB, CurrentUser

router = APIRouter(prefix='/workspaces/{wid}')


async def require_member(db, wid: UUID, user_id: UUID) -> Membership:
    member = await db.get(Membership, (wid, user_id))
    if not member or not member.is_active:
        raise HTTPException(404, '工作空间或资源不存在')
    return member


def require_admin(member: Membership):
    if member.role != 'admin':
        raise HTTPException(403, '此操作需要空间管理员权限')


class MemberInput(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    role: str = Field(pattern='^(admin|agent|requester)$')
    is_active: bool = True


@router.get('/members')
async def members(wid: UUID, db: DB, user: CurrentUser):
    member = await require_member(db, wid, user.id)
    require_admin(member)
    rows = (await db.execute(select(User, Membership).join(Membership).where(Membership.workspace_id == wid).order_by(User.name))).all()
    return [{'user_id': u.id, 'email': u.email, 'name': u.name, 'role': m.role, 'is_active': m.is_active} for u, m in rows]


@router.get('/assignees')
async def assignees(wid: UUID, db: DB, user: CurrentUser):
    await require_member(db, wid, user.id)
    rows = (await db.execute(select(User).join(Membership).where(Membership.workspace_id == wid, Membership.is_active.is_(True), Membership.role.in_(['admin', 'agent']), User.is_active.is_(True)).order_by(User.name))).scalars()
    return [{'id': u.id, 'name': u.name} for u in rows]


@router.put('/members')
async def set_member(wid: UUID, data: MemberInput, db: DB, user: CurrentUser):
    # Serialize membership changes, so two admins cannot concurrently remove the last admins.
    await db.scalar(select(Workspace).where(Workspace.id == wid).with_for_update())
    member = await require_member(db, wid, user.id)
    require_admin(member)
    target = await db.scalar(select(User).where(User.email == data.email.strip().lower(), User.is_active.is_(True)))
    if not target:
        raise HTTPException(404, '未找到可用账户')
    existing = await db.get(Membership, (wid, target.id))
    if existing and existing.role == 'admin' and existing.is_active and (data.role != 'admin' or not data.is_active):
        count = await db.scalar(select(func.count()).select_from(Membership).where(Membership.workspace_id == wid, Membership.role == 'admin', Membership.is_active.is_(True)))
        if count <= 1:
            raise HTTPException(409, '至少保留一位管理员')
    if existing:
        existing.role, existing.is_active = data.role, data.is_active
    else:
        db.add(Membership(workspace_id=wid, user_id=target.id, role=data.role, is_active=data.is_active))
    await db.commit()
    return {'user_id': target.id, 'role': data.role, 'is_active': data.is_active}
