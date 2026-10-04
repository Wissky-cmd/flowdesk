"""Idempotent demo seed; password is supplied by environment, never hardcoded."""
import asyncio
import os
import uuid

from sqlalchemy import select

from .db import SessionFactory, engine
from .models import Membership, Ticket, User, Workspace
from .security import hash_password
from .runtime import loop_factory


def seed_id(name: str):
    return uuid.uuid5(uuid.NAMESPACE_URL, 'https://flowdesk.example/seed/' + name)


async def seed():
    password = os.environ.get('SEED_PASSWORD', '')
    if len(password) < 12:
        raise SystemExit('请通过 SEED_PASSWORD 提供至少 12 位的演示密码')
    people = [('admin', '林管理员'), ('agent', '陈处理员'), ('alice', '许提交人'), ('bob', '周提交人'), ('other', '另一空间用户')]
    async with SessionFactory() as db:
        for name, label in people:
            if not await db.get(User, seed_id(name)):
                db.add(User(id=seed_id(name), email=f'{name}@flowdesk.example', name=label, password_hash=hash_password(password)))
        await db.flush()
        for name, label, owner in [('product', '产品与研发', 'admin'), ('support', '客户支持', 'other')]:
            if not await db.get(Workspace, seed_id(name)):
                db.add(Workspace(id=seed_id(name), name=label, created_by=seed_id(owner)))
        await db.flush()
        for person, space, role in [('admin', 'product', 'admin'), ('agent', 'product', 'agent'), ('alice', 'product', 'requester'), ('bob', 'product', 'requester'), ('other', 'support', 'admin')]:
            if not await db.get(Membership, (seed_id(space), seed_id(person))):
                db.add(Membership(workspace_id=seed_id(space), user_id=seed_id(person), role=role))
        await db.flush()
        for name, title, person, space, priority in [
            ('ticket-1', '新同事入职：开通项目访问权限', 'alice', 'product', 'high'),
            ('ticket-2', '优化工单提交表单的错误提示', 'bob', 'product', 'normal'),
            ('ticket-3', '整理客户支持知识文档', 'other', 'support', 'low'),
        ]:
            if not await db.get(Ticket, seed_id(name)):
                db.add(Ticket(id=seed_id(name), workspace_id=seed_id(space), creator_id=seed_id(person), title=title, body='请协助确认需求并安排处理。这是一条用于学习和验收的演示工单。', priority=priority))
        await db.commit()
    await engine.dispose()
    print('种子数据已就绪；重复执行不会重置密码或覆盖现有数据。')


if __name__ == '__main__':
    asyncio.run(seed(), loop_factory=loop_factory)
