"""Доска задач и календарь: позиция, приоритет, история задач, подписка на календарь

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0005'
down_revision: Union[str, Sequence[str], None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('position', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('priority', sa.String(length=10), nullable=False, server_default='normal'))
        batch_op.add_column(sa.Column('done_at', sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_tasks_status_position', ['status', 'position'])
    # существующие задачи: порядок по id, выполненным — дата закрытия
    op.execute("UPDATE tasks SET position = id * 1000")
    op.execute("UPDATE tasks SET done_at = created_at WHERE status = 'done'")

    op.create_table(
        'task_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('task_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('field', sa.String(length=20), nullable=False),
        sa.Column('old_value', sa.String(length=50), nullable=True),
        sa.Column('new_value', sa.String(length=50), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=10), nullable=False, server_default='cabinet'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_task_events_task_id', 'task_events', ['task_id'])

    op.create_table(
        'calendar_feeds',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('token', sa.String(length=64), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('consent_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
        sa.UniqueConstraint('token'),
    )


def downgrade() -> None:
    op.drop_table('calendar_feeds')
    op.drop_index('ix_task_events_task_id', table_name='task_events')
    op.drop_table('task_events')
    # статуса «На проверке» в старой схеме нет — возвращаем такие задачи «В работу»
    op.execute("UPDATE tasks SET status = 'in_progress' WHERE status = 'review'")
    with op.batch_alter_table('tasks', schema=None) as batch_op:
        batch_op.drop_index('ix_tasks_status_position')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('done_at')
        batch_op.drop_column('priority')
        batch_op.drop_column('position')
