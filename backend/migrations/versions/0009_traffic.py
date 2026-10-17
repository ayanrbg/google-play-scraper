"""traffic source estimate per game (organic / mixed / paid / external / unclear)

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-17 10:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0009'
down_revision: Union[str, Sequence[str], None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('game_metrics', schema=None) as batch_op:
        batch_op.add_column(sa.Column('traffic', sa.String(length=16), nullable=True))
        batch_op.add_column(sa.Column('paid_level', sa.Integer(), nullable=True))
        batch_op.create_index('ix_game_metrics_traffic', ['traffic'])


def downgrade() -> None:
    with op.batch_alter_table('game_metrics', schema=None) as batch_op:
        batch_op.drop_index('ix_game_metrics_traffic')
        batch_op.drop_column('paid_level')
        batch_op.drop_column('traffic')
