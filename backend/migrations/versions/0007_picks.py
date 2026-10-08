"""picks: games picked by hand to build on

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-08 12:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0007'
down_revision: Union[str, Sequence[str], None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'picks',
        sa.Column('workspace_id', sa.Integer(), nullable=False),
        sa.Column('app_id', sa.String(length=255), nullable=False),
        sa.Column('position', sa.Integer(), nullable=False),
        sa.Column('tier', sa.String(length=16), nullable=False),
        sa.Column('niche', sa.String(length=255), nullable=True),
        sa.Column('why', sa.Text(), nullable=True),
        sa.Column('entry', sa.Text(), nullable=True),
        sa.Column('risks', sa.Text(), nullable=True),
        sa.Column('keys', sa.JSON(), nullable=False),
        sa.Column('rivals', sa.JSON(), nullable=False),
        sa.Column('added_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['app_id'], ['apps.app_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('workspace_id', 'app_id'),
    )


def downgrade() -> None:
    op.drop_table('picks')
