"""add_litellm_virtual_key_to_workflows

Revision ID: 3e506607548c
Revises: f4e3d2c1b0a9
Create Date: 2026-05-26 13:00:07.400969

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e506607548c'
down_revision: Union[str, None] = 'f4e3d2c1b0a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('workflows', schema=None) as batch_op:
        batch_op.add_column(sa.Column('litellm_virtual_key', sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('workflows', schema=None) as batch_op:
        batch_op.drop_column('litellm_virtual_key')
