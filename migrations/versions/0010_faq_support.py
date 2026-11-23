"""Вопросы и ответы (FAQ) вместо SOS, переписка поддержки, роль «Поддержка»

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'faq',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('question', sa.String(length=300), nullable=False),
        sa.Column('answer', sa.Text(), nullable=False),
        sa.Column('topic', sa.String(length=40), nullable=False, server_default='Общие вопросы'),
        sa.Column('order_no', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_published', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('question_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['question_id'], ['questions.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'support_chats',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('channel', sa.String(length=10), nullable=False),
        sa.Column('chat_id', sa.String(length=40), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=True),
        sa.Column('status', sa.String(length=10), nullable=False, server_default='open'),
        sa.Column('operator_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['operator_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_support_chats_peer', 'support_chats', ['channel', 'chat_id'])
    op.create_table(
        'support_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('chat_id', sa.Integer(), nullable=False),
        sa.Column('direction', sa.String(length=3), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=True),
        sa.Column('source', sa.String(length=10), nullable=False, server_default='web'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chat_id'], ['support_chats.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_support_messages_chat_id', 'support_messages', ['chat_id'])

    # роль «Поддержка» — одним SQL, чтобы миграция работала и в offline-режиме (alembic upgrade --sql)
    op.execute("INSERT INTO roles (code, name) SELECT 'support', 'Поддержка' "
               "WHERE NOT EXISTS (SELECT 1 FROM roles WHERE code = 'support')")
    # SOS больше нет: прежние SOS-обращения уходят в архив как отклонённые (на доске их не было и не будет)
    op.execute("UPDATE questions SET status = 'rejected' WHERE status = 'sos'")


def downgrade() -> None:
    op.execute("DELETE FROM user_roles WHERE role_id IN (SELECT id FROM roles WHERE code = 'support')")
    op.execute("DELETE FROM roles WHERE code = 'support'")
    op.drop_index('ix_support_messages_chat_id', table_name='support_messages')
    op.drop_table('support_messages')
    op.drop_index('ix_support_chats_peer', table_name='support_chats')
    op.drop_table('support_chats')
    op.drop_table('faq')
