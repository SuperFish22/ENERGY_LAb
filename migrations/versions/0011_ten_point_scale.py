"""Десятибалльная шкала оценок и коэффициент вариации в прогнозе

Баллы экспертов, вероятность и последствия провала блоков, оценки гостей переводятся со шкалы 1–5 на 1–10
линейно: x' = 1 + (x − 1)·9/4 (целые — с округлением). В forecasts добавляется коэффициент вариации.

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UP_INT = "CAST(ROUND(1 + ({c} - 1) * 9.0 / 4) AS INTEGER)"
UP_FLOAT = "1 + ({c} - 1) * 9.0 / 4"
DOWN_INT = "CAST(ROUND(1 + ({c} - 1) * 4.0 / 9) AS INTEGER)"
DOWN_FLOAT = "1 + ({c} - 1) * 4.0 / 9"


def _convert(up: bool) -> None:
    i, f = (UP_INT, UP_FLOAT) if up else (DOWN_INT, DOWN_FLOAT)
    op.execute(f"UPDATE evaluations SET score = {i.format(c='score')}")
    op.execute(f"UPDATE risk_assessments SET probability = {i.format(c='probability')}, "
               f"impact = {i.format(c='impact')}")
    op.execute(f"UPDATE feedback SET rating = {i.format(c='rating')}")
    op.execute(f"UPDATE feedback_stations SET rating = {i.format(c='rating')}")
    op.execute(f"UPDATE event_results SET avg_rating = {f.format(c='avg_rating')} WHERE avg_rating IS NOT NULL")
    for col in ("avg_rating", "expert_score"):
        op.execute(f"UPDATE forecasts SET {col} = {f.format(c=col)} WHERE {col} IS NOT NULL")


def _constraints(top: int) -> None:
    with op.batch_alter_table('evaluations') as b:
        b.drop_constraint('ck_score', type_='check')
        b.create_check_constraint('ck_score', f'score BETWEEN 1 AND {top}')
    with op.batch_alter_table('risk_assessments') as b:
        b.drop_constraint('ck_risk', type_='check')
        b.create_check_constraint('ck_risk', f'probability BETWEEN 1 AND {top} AND impact BETWEEN 1 AND {top}')
    with op.batch_alter_table('feedback') as b:
        b.drop_constraint('ck_fb_rating', type_='check')
        b.create_check_constraint('ck_fb_rating', f'rating BETWEEN 1 AND {top}')


def upgrade() -> None:
    _constraints(10)
    _convert(up=True)
    op.add_column('forecasts', sa.Column('variation', sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column('forecasts', 'variation')
    _convert(up=False)
    _constraints(5)
