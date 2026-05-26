"""add_agent_state

Revision ID: f4e3d2c1b0a9
Revises: d3a1f892b045
Create Date: 2026-05-26 06:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f4e3d2c1b0a9'
down_revision: Union[str, None] = 'd3a1f892b045'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'agent_state',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('agent_id', sa.String(36), nullable=False),
        sa.Column('workflow_id', sa.String(36), nullable=False),
        sa.Column('key', sa.String, nullable=False),
        sa.Column('value', sa.JSON, nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('agent_id', 'workflow_id', 'key', name='uq_agent_state'),
    )
    op.create_index('ix_agent_state_agent_id', 'agent_state', ['agent_id'])
    op.create_index('ix_agent_state_workflow_id', 'agent_state', ['workflow_id'])


def downgrade() -> None:
    op.drop_index('ix_agent_state_workflow_id', table_name='agent_state')
    op.drop_index('ix_agent_state_agent_id', table_name='agent_state')
    op.drop_table('agent_state')
