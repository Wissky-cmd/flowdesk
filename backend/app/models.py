import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(256))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LoginSession(Base):
    __tablename__ = 'sessions'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Workspace(Base):
    __tablename__ = 'workspaces'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100))
    created_by: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Membership(Base):
    __tablename__ = 'memberships'
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id'), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id'), primary_key=True)
    role: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    __table_args__ = (CheckConstraint("role IN ('admin', 'agent', 'requester')", name='ck_member_role'),)


class Ticket(Base):
    __tablename__ = 'tickets'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('workspaces.id'))
    creator_id: Mapped[uuid.UUID] = mapped_column()
    assignee_id: Mapped[uuid.UUID | None] = mapped_column()
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default='new', server_default='new')
    priority: Mapped[str] = mapped_column(String(20), default='normal', server_default='normal')
    version: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'creator_id'], ['memberships.workspace_id', 'memberships.user_id'], name='fk_ticket_creator_member'),
        ForeignKeyConstraint(['workspace_id', 'assignee_id'], ['memberships.workspace_id', 'memberships.user_id'], name='fk_ticket_assignee_member'),
        CheckConstraint("status IN ('new', 'accepted', 'in_progress', 'review', 'closed', 'cancelled')", name='ck_ticket_status'),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name='ck_ticket_priority'),
        CheckConstraint('version > 0', name='ck_ticket_version'),
        Index('ix_ticket_workspace_updated', 'workspace_id', 'updated_at', 'id'),
        Index('ix_ticket_workspace_creator', 'workspace_id', 'creator_id'),
    )
