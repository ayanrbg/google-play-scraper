"""keys reports queued by the daily run for fast young games

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-18 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0010'
down_revision: Union[str, Sequence[str], None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('keys_reports', schema=None) as batch_op:
        batch_op.add_column(sa.Column('auto', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('keys_reports', schema=None) as batch_op:
        batch_op.drop_column('auto')
