"""rebuild_agent_definitions

Drops and recreates agent_definitions with the new blob-based schema.
Old columns (category, model_provider, model_name, etc.) are replaced by
a single JSON ``definition`` column that conforms to _generic_agent.yaml.

Revision ID: 5688c429ddf0
Revises: 3fc028576a36
Create Date: 2026-05-26 01:06:37.136425
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '5688c429ddf0'
down_revision: Union[str, None] = '3fc028576a36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('agent_definitions')
    op.create_table(
        'agent_definitions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), nullable=False, index=True),
        sa.Column('name', sa.String(), nullable=False, index=True),
        sa.Column('definition', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('updated_by', sa.String(36), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.UniqueConstraint('name', 'org_id', name='uq_agent_def_name_org'),
    )


def downgrade() -> None:
    op.drop_table('agent_definitions')
    op.create_table(
        'agent_definitions',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), nullable=False, index=True),
        sa.Column('type', sa.String(), nullable=False, index=True),
        sa.Column('display_name', sa.String(), nullable=False),
        sa.Column('description', sa.String(), nullable=True),
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('model_provider', sa.String(), nullable=False),
        sa.Column('model_name', sa.String(), nullable=False),
        sa.Column('api_key', sa.String(), nullable=True),
        sa.Column('reasoning_strategy', sa.String(), nullable=False),
        sa.Column('max_iterations', sa.Integer(), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('user_prompt', sa.Text(), nullable=False),
        sa.Column('tools', sa.JSON(), nullable=False),
        sa.Column('events', sa.JSON(), nullable=False),
        sa.Column('created_by', sa.String(36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
