"""phase two workflow activity attachments idempotency"""
from alembic import op
import sqlalchemy as sa


revision = 'bddda9993306'
down_revision = 'd766290986c1'
branch_labels = None
depends_on = None

def upgrade():
    # Referenced composite key must exist before the child foreign keys.
    op.create_unique_constraint('uq_ticket_workspace_id', 'tickets', ['workspace_id', 'id'])
    op.create_table('idempotency_requests',
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('key', sa.String(length=80), nullable=False),
    sa.Column('payload_hash', sa.String(length=64), nullable=False),
    sa.Column('response', sa.JSON(), nullable=True),
    sa.ForeignKeyConstraint(['workspace_id', 'actor_id'], ['memberships.workspace_id', 'memberships.user_id'], ),
    sa.PrimaryKeyConstraint('workspace_id', 'actor_id', 'key')
    )
    op.create_table('attachments',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('ticket_id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('filename', sa.String(length=180), nullable=False),
    sa.Column('content_type', sa.String(length=80), nullable=False),
    sa.Column('content', sa.LargeBinary(), nullable=False),
    sa.Column('size', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint('size > 0 AND size <= 5242880 AND octet_length(content) = size', name='ck_attachment_size'),
    sa.ForeignKeyConstraint(['workspace_id', 'actor_id'], ['memberships.workspace_id', 'memberships.user_id'], ),
    sa.ForeignKeyConstraint(['workspace_id', 'ticket_id'], ['tickets.workspace_id', 'tickets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_attachment_ticket', 'attachments', ['ticket_id'], unique=False)
    op.create_table('ticket_events',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('workspace_id', sa.Uuid(), nullable=False),
    sa.Column('ticket_id', sa.Uuid(), nullable=False),
    sa.Column('actor_id', sa.Uuid(), nullable=False),
    sa.Column('kind', sa.String(length=30), nullable=False),
    sa.Column('detail', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.CheckConstraint("kind IN ('created', 'updated', 'transition', 'comment', 'attachment')", name='ck_event_kind'),
    sa.ForeignKeyConstraint(['workspace_id', 'actor_id'], ['memberships.workspace_id', 'memberships.user_id'], ),
    sa.ForeignKeyConstraint(['workspace_id', 'ticket_id'], ['tickets.workspace_id', 'tickets.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_event_ticket_created', 'ticket_events', ['ticket_id', 'created_at', 'id'], unique=False)

def downgrade():
    op.drop_index('ix_event_ticket_created', table_name='ticket_events')
    op.drop_table('ticket_events')
    op.drop_index('ix_attachment_ticket', table_name='attachments')
    op.drop_table('attachments')
    op.drop_table('idempotency_requests')
    op.drop_constraint('uq_ticket_workspace_id', 'tickets', type_='unique')
