"""new-queries detector: autocomplete prefixes and the terms they surfaced

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-20 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0011'
down_revision: Union[str, Sequence[str], None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'suggest_prefixes',
        sa.Column('prefix', sa.String(32), primary_key=True),
        sa.Column('lang', sa.String(8), primary_key=True),
        sa.Column('country', sa.String(8), primary_key=True),
        sa.Column('first_crawled', sa.Date()),
        sa.Column('crawled_at', sa.DateTime()),
    )
    op.create_table(
        'suggest_terms',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('term', sa.String(255), nullable=False),
        sa.Column('lang', sa.String(8), nullable=False),
        sa.Column('country', sa.String(8), nullable=False),
        sa.Column('first_seen', sa.Date(), nullable=False),
        sa.Column('last_seen', sa.Date(), nullable=False),
        sa.Column('days_seen', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('baseline', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('prefix', sa.String(32)),
        sa.Column('prefix_len', sa.Integer()),
        sa.Column('position', sa.Integer()),
        sa.Column('first_prefix_len', sa.Integer()),
        sa.Column('keyword_id', sa.Integer(), sa.ForeignKey('keywords.id', ondelete='SET NULL')),
        sa.Column('phrase', sa.String(255)),
        sa.Column('phrase_birth', sa.Date()),
        sa.Column('phrase_titles', sa.Integer()),
        sa.Column('phrase_titles_30d', sa.Integer()),
        sa.Column('leader_app_id', sa.String(255)),
        sa.Column('leader_paid', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('relevant_top', sa.Integer()),
        sa.Column('score', sa.Float()),
        sa.Column('checked_at', sa.DateTime()),
        sa.UniqueConstraint('term', 'lang', 'country'),
    )
    op.create_index('ix_suggest_terms_first_seen', 'suggest_terms', ['first_seen'])
    op.create_index('ix_suggest_terms_score', 'suggest_terms', ['score'])


def downgrade() -> None:
    op.drop_index('ix_suggest_terms_score', 'suggest_terms')
    op.drop_index('ix_suggest_terms_first_seen', 'suggest_terms')
    op.drop_table('suggest_terms')
    op.drop_table('suggest_prefixes')
