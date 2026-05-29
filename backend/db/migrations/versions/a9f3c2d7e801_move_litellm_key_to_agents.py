"""move_litellm_key_to_agents

Move litellm_virtual_key from workflows → agents so each agent gets its own
LiteLLM virtual key (better cost isolation and rate-limit attribution).

Revision ID: a9f3c2d7e801
Revises: 1412090258b8
Create Date: 2026-05-26
"""

from __future__ import annotations

from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = 'a9f3c2d7e801'
down_revision: Union[str, None] = '1412090258b8'
branch_labels = None
depends_on = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    insp = sa.inspect(bind)
    return column in {c["name"] for c in insp.get_columns(table)}


def upgrade() -> None:
    # Add litellm_virtual_key to agents
    if not _column_exists("agents", "litellm_virtual_key"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.add_column(sa.Column("litellm_virtual_key", sa.String(), nullable=True))

    # Drop litellm_virtual_key from workflows
    if _column_exists("workflows", "litellm_virtual_key"):
        with op.batch_alter_table("workflows") as batch_op:
            batch_op.drop_column("litellm_virtual_key")


def downgrade() -> None:
    # Restore litellm_virtual_key on workflows
    if not _column_exists("workflows", "litellm_virtual_key"):
        with op.batch_alter_table("workflows") as batch_op:
            batch_op.add_column(sa.Column("litellm_virtual_key", sa.String(), nullable=True))

    # Drop litellm_virtual_key from agents
    if _column_exists("agents", "litellm_virtual_key"):
        with op.batch_alter_table("agents") as batch_op:
            batch_op.drop_column("litellm_virtual_key")
