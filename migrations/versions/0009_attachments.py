"""Документы проектов, вложения задач, ссылка на фотоальбом на Яндекс/Google Диске

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_id', sa.Integer(), nullable=True),
        sa.Column('task_id', sa.Integer(), nullable=True),
        sa.Column('kind', sa.String(length=5), nullable=False),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('category', sa.String(length=15), nullable=False, server_default='other'),
        sa.Column('file', sa.String(length=255), nullable=True),
        sa.Column('original_name', sa.String(length=200), nullable=True),
        sa.Column('size', sa.Integer(), nullable=True),
        sa.Column('url', sa.String(length=500), nullable=True),
        sa.Column('provider', sa.String(length=10), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['event_id'], ['events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_attachments_event_id', 'attachments', ['event_id'])
    op.create_index('ix_attachments_task_id', 'attachments', ['task_id'])
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('album_url', sa.String(length=500), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('album_url')
    op.drop_index('ix_attachments_task_id', table_name='attachments')
    op.drop_index('ix_attachments_event_id', table_name='attachments')
    op.drop_table('attachments')
