"""discovery events, similar links, keys reports, snapshot version

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-29 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0006'
down_revision: Union[str, Sequence[str], None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'discovery_events',
        sa.Column('app_id', sa.String(length=255), nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('detail', sa.JSON(), nullable=False),
        sa.Column('first', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['apps.app_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('app_id', 'source'),
    )
    op.create_table(
        'similar_links',
        sa.Column('app_id', sa.String(length=255), nullable=False),
        sa.Column('similar_id', sa.String(length=255), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.ForeignKeyConstraint(['app_id'], ['apps.app_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('app_id', 'similar_id'),
    )
    op.create_index('ix_similar_links_similar_id', 'similar_links', ['similar_id'])
    op.create_table(
        'keys_reports',
        sa.Column('app_id', sa.String(length=255), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False),
        sa.Column('requested_by', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('finished_at', sa.DateTime(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('progress', sa.JSON(), nullable=False),
        sa.Column('result', sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(['app_id'], ['apps.app_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('app_id'),
    )
    op.create_index('ix_keys_reports_status', 'keys_reports', ['status'])
    with op.batch_alter_table('snapshots', schema=None) as batch_op:
        batch_op.add_column(sa.Column('version', sa.String(length=100), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('snapshots', schema=None) as batch_op:
        batch_op.drop_column('version')
    op.drop_index('ix_keys_reports_status', table_name='keys_reports')
    op.drop_table('keys_reports')
    op.drop_index('ix_similar_links_similar_id', table_name='similar_links')
    op.drop_table('similar_links')
    op.drop_table('discovery_events')
