"""Сценарий вместо станций: виды блоков, карусель, оцениваемые блоки, фактическое время, слот площадки

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-13

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # прежние станции становятся блоками программы, которые оцениваются, — экспертизы и анкеты сохраняются
    with op.batch_alter_table('stations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('kind', sa.String(length=10), nullable=False, server_default='block'))
        batch_op.add_column(sa.Column('parent_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('rated', sa.Boolean(), nullable=False, server_default=sa.true()))
        batch_op.add_column(sa.Column('fact_min', sa.SmallInteger(), nullable=True))
        batch_op.add_column(sa.Column('groups', sa.SmallInteger(), nullable=True))
        batch_op.add_column(sa.Column('transition_min', sa.SmallInteger(), nullable=True))
        batch_op.create_foreign_key('fk_stations_parent', 'stations', ['parent_id'], ['id'], ondelete='CASCADE')
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('slot_min', sa.SmallInteger(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('slot_min')
    # станции каруселей поднимаются на верхний уровень, сами карусели удаляются
    op.execute("UPDATE stations SET parent_id = NULL")
    op.execute("DELETE FROM stations WHERE kind = 'carousel'")
    with op.batch_alter_table('stations', schema=None) as batch_op:
        batch_op.drop_constraint('fk_stations_parent', type_='foreignkey')
        batch_op.drop_column('transition_min')
        batch_op.drop_column('groups')
        batch_op.drop_column('fact_min')
        batch_op.drop_column('rated')
        batch_op.drop_column('parent_id')
        batch_op.drop_column('kind')
