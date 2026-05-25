"""add_workflow_id_to_agents

Revision ID: d3a1f892b045
Revises: c65b814769a4
Create Date: 2026-05-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd3a1f892b045'
down_revision: Union[str, None] = 'c65b814769a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'agents',
        sa.Column('workflow_id', sa.String(36), nullable=True)
    )
    # SQLite doesn't support ADD CONSTRAINT in ALTER TABLE, so we create the
    # index separately (works on Postgres too).
    op.create_index('ix_agents_workflow_id', 'agents', ['workflow_id'])


def downgrade() -> None:
    op.drop_index('ix_agents_workflow_id', table_name='agents')
    op.drop_column('agents', 'workflow_id')
