"""new-queries detector: mark queries that are a big #1 game's own name

Revision ID: 0013
Revises: 0012
Create Date: 2026-10-22 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0013'
down_revision: Union[str, Sequence[str], None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('suggest_terms', schema=None) as batch_op:
        batch_op.add_column(sa.Column('name_taken', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('suggest_terms', schema=None) as batch_op:
        batch_op.drop_column('name_taken')
