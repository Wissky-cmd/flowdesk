from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from .models import Membership, Ticket, User
from .security import DB, CurrentUser
from .workspaces import require_member

router = APIRouter(prefix='/workspaces/{wid}/tickets')


class TicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    priority: Literal['low', 'normal', 'high', 'urgent'] = 'normal'
    assignee_id: UUID | None = None


class TicketOutput(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    workspace_id: UUID
    creator_id: UUID
    assignee_id: UUID | None
    title: str
    body: str
    priority: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


def visible(wid, user_id, role):
    conditions = [Ticket.workspace_id == wid]
    if role == 'requester':
        conditions.append(Ticket.creator_id == user_id)
    return conditions


@router.get('')
async def list_tickets(wid: UUID, db: DB, user: CurrentUser, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100)):
    member = await require_member(db, wid, user.id)
    conditions = visible(wid, user.id, member.role)
    total = await db.scalar(select(func.count()).select_from(Ticket).where(*conditions))
    rows = (await db.scalars(select(Ticket).where(*conditions).order_by(Ticket.updated_at.desc(), Ticket.id.desc()).offset((page - 1) * page_size).limit(page_size))).all()
    return {'items': [TicketOutput.model_validate(t) for t in rows], 'total': total, 'page': page, 'page_size': page_size}


@router.post('', response_model=TicketOutput, status_code=201)
async def create_ticket(wid: UUID, data: TicketInput, db: DB, user: CurrentUser):
    member = await require_member(db, wid, user.id)
    if data.assignee_id:
        if member.role == 'requester':
            raise HTTPException(403, '提交人不能指定负责人')
        assignee = await db.scalar(select(Membership).join(User).where(Membership.workspace_id == wid, Membership.user_id == data.assignee_id, Membership.is_active.is_(True), Membership.role.in_(['admin', 'agent']), User.is_active.is_(True)))
        if not assignee:
            raise HTTPException(422, '负责人必须是本空间可用的管理员或处理人员')
    ticket = Ticket(workspace_id=wid, creator_id=user.id, **data.model_dump())
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.get('/{ticket_id}', response_model=TicketOutput)
async def ticket_detail(wid: UUID, ticket_id: UUID, db: DB, user: CurrentUser):
    member = await require_member(db, wid, user.id)
    ticket = await db.scalar(select(Ticket).where(Ticket.id == ticket_id, *visible(wid, user.id, member.role)))
    if not ticket:
        raise HTTPException(404, '工单不存在或不可访问')
    return ticket
