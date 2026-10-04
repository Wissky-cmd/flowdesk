import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, LargeBinary, JSON, func
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
        UniqueConstraint('workspace_id', 'id', name='uq_ticket_workspace_id'),
        ForeignKeyConstraint(['workspace_id', 'creator_id'], ['memberships.workspace_id', 'memberships.user_id'], name='fk_ticket_creator_member'),
        ForeignKeyConstraint(['workspace_id', 'assignee_id'], ['memberships.workspace_id', 'memberships.user_id'], name='fk_ticket_assignee_member'),
        CheckConstraint("status IN ('new', 'accepted', 'in_progress', 'review', 'closed', 'cancelled')", name='ck_ticket_status'),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name='ck_ticket_priority'),
        CheckConstraint('version > 0', name='ck_ticket_version'),
        Index('ix_ticket_workspace_updated', 'workspace_id', 'updated_at', 'id'),
        Index('ix_ticket_workspace_creator', 'workspace_id', 'creator_id'),
    )


class TicketEvent(Base):
    __tablename__ = 'ticket_events'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    ticket_id: Mapped[uuid.UUID] = mapped_column()
    actor_id: Mapped[uuid.UUID] = mapped_column()
    kind: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'ticket_id'], ['tickets.workspace_id', 'tickets.id']),
        ForeignKeyConstraint(['workspace_id', 'actor_id'], ['memberships.workspace_id', 'memberships.user_id']),
        CheckConstraint("kind IN ('created', 'updated', 'transition', 'comment', 'attachment')", name='ck_event_kind'),
        Index('ix_event_ticket_created', 'ticket_id', 'created_at', 'id'),
    )


class Attachment(Base):
    __tablename__ = 'attachments'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    ticket_id: Mapped[uuid.UUID] = mapped_column()
    actor_id: Mapped[uuid.UUID] = mapped_column()
    filename: Mapped[str] = mapped_column(String(180))
    content_type: Mapped[str] = mapped_column(String(80))
    content: Mapped[bytes] = mapped_column(LargeBinary, deferred=True)
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'ticket_id'], ['tickets.workspace_id', 'tickets.id']),
        ForeignKeyConstraint(['workspace_id', 'actor_id'], ['memberships.workspace_id', 'memberships.user_id']),
        CheckConstraint('size > 0 AND size <= 5242880 AND octet_length(content) = size', name='ck_attachment_size'),
        Index('ix_attachment_ticket', 'ticket_id'),
    )


class IdempotencyRequest(Base):
    __tablename__ = 'idempotency_requests'
    workspace_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    payload_hash: Mapped[str] = mapped_column(String(64))
    response: Mapped[dict | None] = mapped_column(JSON)
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'actor_id'], ['memberships.workspace_id', 'memberships.user_id']),
    )


class IntegrationToken(Base):
    __tablename__ = 'integration_tokens'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    user_id: Mapped[uuid.UUID] = mapped_column()
    name: Mapped[str] = mapped_column(String(80))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    scopes: Mapped[list] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(['workspace_id', 'user_id'], ['memberships.workspace_id', 'memberships.user_id']),)


class Job(Base):
    __tablename__ = 'jobs'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column()
    owner_id: Mapped[uuid.UUID] = mapped_column()
    owner_role: Mapped[str] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(20), default='queued', server_default='queued')
    generation: Mapped[int] = mapped_column(Integer, default=1, server_default='1')
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    run_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    ready_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    claim_token: Mapped[uuid.UUID | None] = mapped_column()
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error_code: Mapped[str | None] = mapped_column(String(80))
    result_key: Mapped[str | None] = mapped_column(String(80))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (
        ForeignKeyConstraint(['workspace_id', 'owner_id'], ['memberships.workspace_id', 'memberships.user_id']),
        CheckConstraint("status IN ('queued','running','succeeded','failed','expired')", name='ck_job_status'),
        CheckConstraint('attempts >= 0 AND run_attempts BETWEEN 0 AND 3 AND generation > 0', name='ck_job_budget'),
        Index('ix_job_workspace_owner_created', 'workspace_id', 'owner_id', 'created_at'),
        Index('ix_job_status_lease', 'status', 'lease_until'),
    )


class OutboxEvent(Base):
    __tablename__ = 'outbox_events'
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('jobs.id'), primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default='pending', server_default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    run_attempts: Mapped[int] = mapped_column(Integer, default=0, server_default='0')
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    claim_token: Mapped[uuid.UUID | None] = mapped_column()
    __table_args__ = (
        CheckConstraint("status IN ('pending','dispatching','sent','exhausted')", name='ck_outbox_status'),
        CheckConstraint('attempts >= 0 AND run_attempts BETWEEN 0 AND 5', name='ck_outbox_budget'),
        Index('ix_outbox_due', 'status', 'next_attempt_at'),
    )


class JobEvent(Base):
    __tablename__ = 'job_events'
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('jobs.id'))
    generation: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    detail: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (Index('ix_job_event_created', 'job_id', 'created_at'),)
