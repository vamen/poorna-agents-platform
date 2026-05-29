"""add_sender_recipient_tables

Revision ID: 1412090258b8
Revises: 3e506607548c
Create Date: 2026-05-26 16:13:13.721221

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision: str = '1412090258b8'
down_revision: Union[str, None] = '3e506607548c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(name: str) -> bool:
    bind = op.get_bind()
    return inspect(bind).has_table(name)


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    cols = [c["name"] for c in inspect(bind).get_columns(table)]
    return column in cols


def upgrade() -> None:
    if not _table_exists('senders'):
        op.create_table(
            'senders',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('type', sa.String(), nullable=False),
            sa.Column('ref_id', sa.String(), nullable=False),
            sa.Column('display_name', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint('type', 'ref_id', name='uq_sender_type_ref'),
        )

    if not _table_exists('recipients'):
        op.create_table(
            'recipients',
            sa.Column('id', sa.String(36), primary_key=True),
            sa.Column('type', sa.String(), nullable=False),
            sa.Column('ref_id', sa.String(), nullable=False),
            sa.Column('display_name', sa.String(), nullable=True),
            sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
            sa.UniqueConstraint('type', 'ref_id', name='uq_recipient_type_ref'),
        )

    # Remodel agent_messages: add sender_id/recipient_id, drop old FK columns
    if not _column_exists('agent_messages', 'sender_id'):
        with op.batch_alter_table('agent_messages', schema=None) as batch_op:
            batch_op.add_column(sa.Column('sender_id', sa.String(36), nullable=True))
            batch_op.add_column(sa.Column('recipient_id', sa.String(36), nullable=True))
            batch_op.drop_column('from_agent_id')
            batch_op.drop_column('to_agent_id')


def downgrade() -> None:
    if _column_exists('agent_messages', 'sender_id'):
        with op.batch_alter_table('agent_messages', schema=None) as batch_op:
            batch_op.add_column(sa.Column('from_agent_id', sa.String(36), nullable=True))
            batch_op.add_column(sa.Column('to_agent_id', sa.String(36), nullable=True))
            batch_op.drop_column('sender_id')
            batch_op.drop_column('recipient_id')

    if _table_exists('recipients'):
        op.drop_table('recipients')
    if _table_exists('senders'):
        op.drop_table('senders')
