"""create_claude_daily_costs_table

Revision ID: 435a99988f2b
Revises: 0024_add_batch_number_to_manuals
Create Date: 2026-08-14 05:36:58.419416

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '435a99988f2b'
down_revision: Union[str, None] = '0024_add_batch_number_to_manuals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('claude_daily_costs',
    sa.Column('date', sa.Date(), nullable=False),
    sa.Column('input_tokens', sa.Integer(), nullable=False),
    sa.Column('output_tokens', sa.Integer(), nullable=False),
    sa.Column('cost', sa.Float(), nullable=False),
    sa.PrimaryKeyConstraint('date')
    )


def downgrade() -> None:
    op.drop_table('claude_daily_costs')
