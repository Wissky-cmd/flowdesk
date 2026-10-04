import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import String, cast, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from .models import Attachment, IdempotencyRequest, Membership, Ticket, TicketEvent, User
from .security import DB
from .integrations import TicketUser as CurrentUser
from .workspaces import require_member

router = APIRouter(prefix='/workspaces/{wid}/tickets')
Status = Literal['new', 'accepted', 'in_progress', 'review', 'closed', 'cancelled']
Priority = Literal['low', 'normal', 'high', 'urgent']


class TicketInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    title: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=20000)
    priority: Priority = 'normal'
    assignee_id: UUID | None = None


class TicketEdit(TicketInput):
    version: int = Field(ge=1)


class TransitionInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    version: int = Field(ge=1)
    status: Status
    reason: str = Field(default='', max_length=2000)


class CommentInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    body: str = Field(min_length=1, max_length=5000)


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


async def accessible(db, wid, ticket_id, user, lock=False):
    member = await require_member(db, wid, user.id)
    stmt = select(Ticket).where(Ticket.id == ticket_id, *visible(wid, user.id, member.role))
    ticket = await db.scalar(stmt.with_for_update() if lock else stmt)
    if not ticket:
        raise HTTPException(404, '工单不存在或不可访问')
    return ticket, member


async def validate_assignee(db, wid, assignee_id):
    if assignee_id and not await db.scalar(select(Membership).join(User).where(
        Membership.workspace_id == wid, Membership.user_id == assignee_id,
        Membership.is_active.is_(True), Membership.role.in_(['admin', 'agent']), User.is_active.is_(True),
    )):
        raise HTTPException(422, '负责人必须是本空间可用的管理员或处理人员')


def audit(db, ticket, user, kind, detail):
    db.add(TicketEvent(workspace_id=ticket.workspace_id, ticket_id=ticket.id, actor_id=user.id, kind=kind, detail=detail))


def snapshot(ticket):
    return TicketOutput.model_validate(ticket).model_dump(mode='json')


def transitions(ticket, member, user):
    staff = member.role in ('admin', 'agent')
    owner = ticket.creator_id == user.id
    admin = member.role == 'admin'
    result = []
    if staff:
        result += {'new': ['accepted'], 'accepted': ['in_progress'], 'in_progress': ['review']}.get(ticket.status, [])
    if ticket.status == 'review' and (admin or owner):
        result += ['closed', 'in_progress']
    if ticket.status == 'closed' and (admin or owner):
        result += ['in_progress']
    if ticket.status in ('new', 'accepted', 'in_progress', 'review') and (admin or (owner and ticket.status == 'new')):
        result += ['cancelled']
    return result


@router.get('')
async def list_tickets(
    wid: UUID, db: DB, user: CurrentUser, page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
    q: str = Query('', max_length=200), status: Status | None = None, priority: Priority | None = None,
    assignee_id: UUID | None = None, unassigned: bool = False,
    created_from: datetime | None = None, created_to: datetime | None = None,
    sort: Literal['newest', 'oldest'] = 'newest',
):
    member = await require_member(db, wid, user.id)
    conditions = visible(wid, user.id, member.role)
    if q.strip():
        escaped = q.strip().replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        conditions.append(or_(Ticket.title.ilike(f'%{escaped}%', escape='\\'), cast(Ticket.id, String).ilike(f'%{escaped}%', escape='\\')))
    for column, value in ((Ticket.status, status), (Ticket.priority, priority), (Ticket.assignee_id, assignee_id)):
        if value is not None:
            conditions.append(column == value)
    if unassigned:
        conditions.append(Ticket.assignee_id.is_(None))
    if any(value and value.tzinfo is None for value in (created_from, created_to)):
        raise HTTPException(422, '日期必须包含时区')
    if created_from and created_to and created_from >= created_to:
        raise HTTPException(422, '结束日期必须晚于开始日期')
    if created_from:
        conditions.append(Ticket.created_at >= created_from)
    if created_to:
        conditions.append(Ticket.created_at < created_to)
    # Window count keeps the page and count in the same PostgreSQL statement snapshot.
    order = (Ticket.updated_at.desc(), Ticket.id.desc()) if sort == 'newest' else (Ticket.updated_at, Ticket.id)
    rows = (await db.execute(select(Ticket, func.count().over()).where(*conditions).order_by(*order).offset((page - 1) * page_size).limit(page_size))).all()
    total = rows[0][1] if rows else await db.scalar(select(func.count()).select_from(Ticket).where(*conditions))
    return {'items': [TicketOutput.model_validate(t) for t, _ in rows], 'total': total, 'page': page, 'page_size': page_size}


@router.get('/summary')
async def summary(wid: UUID, db: DB, user: CurrentUser):
    member = await require_member(db, wid, user.id)
    rows = (await db.execute(select(Ticket.status, Ticket.priority, func.count()).where(*visible(wid, user.id, member.role)).group_by(Ticket.status, Ticket.priority))).all()
    statuses, priorities = {}, {}
    for status, priority, count in rows:
        statuses[status] = statuses.get(status, 0) + count
        priorities[priority] = priorities.get(priority, 0) + count
    assigned = (await db.execute(select(Ticket.assignee_id, User.name, func.count()).outerjoin(User, User.id == Ticket.assignee_id)
                                .where(*visible(wid, user.id, member.role), Ticket.status.not_in(['closed', 'cancelled']))
                                .group_by(Ticket.assignee_id, User.name).order_by(func.count().desc()))).all()
    return {'total': sum(statuses.values()), 'statuses': statuses, 'priorities': priorities,
            'assignees': [{'id': uid, 'name': name or '未分派', 'count': count} for uid, name, count in assigned]}


@router.post('', response_model=TicketOutput, status_code=201)
async def create_ticket(wid: UUID, data: TicketInput, db: DB, user: CurrentUser, idempotency_key: str | None = Header(None, min_length=8, max_length=80, pattern=r'^[A-Za-z0-9_-]+$')):
    member = await require_member(db, wid, user.id)
    if data.assignee_id and member.role == 'requester':
        raise HTTPException(403, '提交人不能指定负责人')
    request_row = None
    if idempotency_key:
        payload_hash = hashlib.sha256(json.dumps(data.model_dump(mode='json'), sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        # ON CONFLICT waits for the competing transaction; failed requests leave no reservation.
        await db.execute(insert(IdempotencyRequest).values(workspace_id=wid, actor_id=user.id, key=idempotency_key, payload_hash=payload_hash).on_conflict_do_nothing())
        request_row = await db.get(IdempotencyRequest, (wid, user.id, idempotency_key))
        if request_row.payload_hash != payload_hash:
            raise HTTPException(409, '同一请求编号已用于不同内容，请重新提交')
        if request_row.response:
            await db.commit()
            return request_row.response
    await validate_assignee(db, wid, data.assignee_id)
    ticket = Ticket(workspace_id=wid, creator_id=user.id, **data.model_dump())
    db.add(ticket)
    await db.flush()
    audit(db, ticket, user, 'created', {'after': snapshot(ticket)})
    if request_row:
        request_row.response = snapshot(ticket)
    await db.commit()
    return ticket


@router.get('/{ticket_id}', response_model=TicketOutput)
async def ticket_detail(wid: UUID, ticket_id: UUID, db: DB, user: CurrentUser):
    ticket, _ = await accessible(db, wid, ticket_id, user)
    return ticket


@router.get('/{ticket_id}/actions')
async def ticket_actions(wid: UUID, ticket_id: UUID, db: DB, user: CurrentUser):
    ticket, member = await accessible(db, wid, ticket_id, user)
    return {'transitions': transitions(ticket, member, user), 'can_edit': member.role in ('admin', 'agent') or ticket.status == 'new'}


async def save_change(db, ticket, user, version, values, kind, reason=''):
    if version != ticket.version:
        raise HTTPException(409, '工单已被其他人更新。请加载最新版本，再确认你的修改')
    before = snapshot(ticket)
    changed = await db.scalar(update(Ticket).where(Ticket.id == ticket.id, Ticket.workspace_id == ticket.workspace_id, Ticket.version == version)
                              .values(**values, version=Ticket.version + 1, updated_at=datetime.now(timezone.utc)).returning(Ticket).execution_options(populate_existing=True))
    if not changed:
        raise HTTPException(409, '工单已被其他人更新。请加载最新版本，再确认你的修改')
    audit(db, changed, user, kind, {'before': before, 'after': snapshot(changed), 'reason': reason})
    await db.commit()
    return changed


@router.put('/{ticket_id}', response_model=TicketOutput)
async def edit_ticket(wid: UUID, ticket_id: UUID, data: TicketEdit, db: DB, user: CurrentUser):
    ticket, member = await accessible(db, wid, ticket_id, user)
    if member.role == 'requester':
        if ticket.status != 'new' or data.assignee_id != ticket.assignee_id or data.priority != ticket.priority:
            raise HTTPException(403, '提交人仅可编辑新建工单的标题和描述')
    await validate_assignee(db, wid, data.assignee_id)
    return await save_change(db, ticket, user, data.version, data.model_dump(exclude={'version'}), 'updated')


@router.post('/{ticket_id}/transitions', response_model=TicketOutput)
async def transition_ticket(wid: UUID, ticket_id: UUID, data: TransitionInput, db: DB, user: CurrentUser):
    ticket, member = await accessible(db, wid, ticket_id, user)
    if data.version != ticket.version:
        raise HTTPException(409, '工单已被其他人更新。请加载最新版本，再确认你的修改')
    if data.status not in transitions(ticket, member, user):
        raise HTTPException(403, '当前状态或角色不允许此流转')
    if (data.status == 'cancelled' or (data.status == 'in_progress' and ticket.status in ('review', 'closed'))) and not data.reason:
        raise HTTPException(422, '取消、退回或重新打开工单需要填写原因')
    if data.status in ('accepted', 'in_progress', 'review'):
        if not ticket.assignee_id:
            raise HTTPException(422, '请先分派负责人')
        await validate_assignee(db, wid, ticket.assignee_id)
    return await save_change(db, ticket, user, data.version, {'status': data.status}, 'transition', data.reason)


@router.get('/{ticket_id}/activity')
async def activity(wid: UUID, ticket_id: UUID, db: DB, user: CurrentUser, page: int = Query(1, ge=1)):
    await accessible(db, wid, ticket_id, user)
    rows = (await db.execute(select(TicketEvent, User.name, func.count().over()).join(User, User.id == TicketEvent.actor_id)
                            .where(TicketEvent.workspace_id == wid, TicketEvent.ticket_id == ticket_id)
                            .order_by(TicketEvent.created_at.desc(), TicketEvent.id.desc()).offset((page - 1) * 30).limit(30))).all()
    return {'items': [{'id': e.id, 'kind': e.kind, 'detail': e.detail, 'actor': name, 'created_at': e.created_at} for e, name, _ in rows], 'total': rows[0][2] if rows else 0}


@router.post('/{ticket_id}/comments', status_code=201)
async def comment(wid: UUID, ticket_id: UUID, data: CommentInput, db: DB, user: CurrentUser):
    ticket, _ = await accessible(db, wid, ticket_id, user)
    # Comments are immutable activity entries; one source of truth, no duplicate comment table.
    audit(db, ticket, user, 'comment', {'body': data.body})
    await db.commit()
    return {'ok': True}


@router.get('/{ticket_id}/attachments')
async def attachments(wid: UUID, ticket_id: UUID, db: DB, user: CurrentUser):
    await accessible(db, wid, ticket_id, user)
    rows = (await db.scalars(select(Attachment).where(Attachment.workspace_id == wid, Attachment.ticket_id == ticket_id).order_by(Attachment.created_at))).all()
    return [{'id': a.id, 'filename': a.filename, 'size': a.size, 'created_at': a.created_at} for a in rows]


@router.post('/{ticket_id}/attachments', status_code=201)
async def upload(wid: UUID, ticket_id: UUID, request: Request, db: DB, user: CurrentUser, filename: str = Query(min_length=1, max_length=180)):
    await accessible(db, wid, ticket_id, user)
    if any(ord(c) < 32 or c in '/\\\x7f' for c in filename) or filename.strip() in ('.', '..', ''):
        raise HTTPException(422, '文件名无效')
    ext = filename.rsplit('.', 1)[-1].lower()
    types = {'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'pdf': 'application/pdf', 'txt': 'text/plain'}
    if ext not in types:
        raise HTTPException(422, '仅支持 PNG、JPEG、PDF、UTF-8 TXT')
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 5 * 1024 * 1024:
            raise HTTPException(413, '单个附件不能超过 5 MB')
    if not content:
        raise HTTPException(422, '不能上传空文件')
    signatures = {'png': b'\x89PNG\r\n\x1a\n', 'jpg': b'\xff\xd8\xff', 'jpeg': b'\xff\xd8\xff', 'pdf': b'%PDF-'}
    if ext in signatures and not content.startswith(signatures[ext]):
        raise HTTPException(422, '文件内容与扩展名不符')
    if ext == 'txt':
        try:
            decoded = content.decode('utf-8')
            if '\x00' in decoded:
                raise ValueError()
        except (UnicodeDecodeError, ValueError):
            raise HTTPException(422, '文本附件必须是 UTF-8 格式')
    # Lock only after receiving the bounded body. Serializes the per-ticket attachment quota.
    ticket, _ = await accessible(db, wid, ticket_id, user, lock=True)
    count = await db.scalar(select(func.count()).select_from(Attachment).where(Attachment.ticket_id == ticket_id))
    if count >= 10:
        raise HTTPException(422, '每张工单最多 10 个附件')
    # ponytail: bounded 5 MB / 10 files in PostgreSQL; use object storage when volume warrants it.
    attachment = Attachment(workspace_id=wid, ticket_id=ticket_id, actor_id=user.id, filename=filename, content_type=types[ext], content=bytes(content), size=len(content))
    db.add(attachment)
    await db.flush()
    audit(db, ticket, user, 'attachment', {'filename': filename, 'attachment_id': str(attachment.id)})
    await db.commit()
    return {'id': attachment.id, 'filename': filename, 'size': attachment.size}


@router.get('/{ticket_id}/attachments/{attachment_id}')
async def download(wid: UUID, ticket_id: UUID, attachment_id: UUID, db: DB, user: CurrentUser):
    await accessible(db, wid, ticket_id, user)
    row = (await db.execute(select(Attachment.filename, Attachment.content).where(Attachment.id == attachment_id, Attachment.workspace_id == wid, Attachment.ticket_id == ticket_id))).first()
    if not row:
        raise HTTPException(404, '附件不存在')
    return Response(row.content, media_type='application/octet-stream', headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(row.filename, safe='')}", 'Content-Security-Policy': "sandbox; default-src 'none'"})
