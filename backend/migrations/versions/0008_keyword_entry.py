"""keyword entry metrics (room for a new game) and search results history

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0008'
down_revision: Union[str, Sequence[str], None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ("room", "room_best", "fresh_count", "entrants_growing", "entrants_v7", "churn7")


def upgrade() -> None:
    with op.batch_alter_table('keywords', schema=None) as batch_op:
        for c in COLUMNS:
            batch_op.add_column(sa.Column(c, sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('entry_score', sa.Float(), nullable=True))
        batch_op.create_index('ix_keywords_entry_score', ['entry_score'])
    op.create_table(
        'keyword_serps',
        sa.Column('keyword_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('apps', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['keyword_id'], ['keywords.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('keyword_id', 'date'),
    )


def downgrade() -> None:
    op.drop_table('keyword_serps')
    with op.batch_alter_table('keywords', schema=None) as batch_op:
        batch_op.drop_index('ix_keywords_entry_score')
        batch_op.drop_column('entry_score')
        for c in COLUMNS:
            batch_op.drop_column(c)
