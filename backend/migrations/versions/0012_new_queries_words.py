"""new-queries detector: word queries from fresh titles, clone waves, explosive leaders marked not hidden

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-20 16:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0012'
down_revision: Union[str, Sequence[str], None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('suggest_prefixes', schema=None) as batch_op:
        batch_op.alter_column('prefix', type_=sa.String(64), existing_type=sa.String(32))
        batch_op.add_column(sa.Column('kind', sa.String(8), nullable=False, server_default='short'))
    with op.batch_alter_table('suggest_terms', schema=None) as batch_op:
        batch_op.alter_column('prefix', type_=sa.String(64), existing_type=sa.String(32))
        batch_op.add_column(sa.Column('phrase_devs_30d', sa.Integer()))
        batch_op.add_column(sa.Column('leader_explosive', sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table('suggest_terms', schema=None) as batch_op:
        batch_op.drop_column('leader_explosive')
        batch_op.drop_column('phrase_devs_30d')
        batch_op.alter_column('prefix', type_=sa.String(32), existing_type=sa.String(64))
    with op.batch_alter_table('suggest_prefixes', schema=None) as batch_op:
        batch_op.drop_column('kind')
        batch_op.alter_column('prefix', type_=sa.String(32), existing_type=sa.String(64))
