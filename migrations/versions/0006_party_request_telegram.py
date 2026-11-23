"""Заявка на мероприятие: ник в Telegram

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('party_requests', schema=None) as batch_op:
        batch_op.add_column(sa.Column('telegram', sa.String(length=32), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('party_requests', schema=None) as batch_op:
        batch_op.drop_column('telegram')
