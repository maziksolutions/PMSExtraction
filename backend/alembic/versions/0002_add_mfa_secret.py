"""add mfa_secret to users

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('mfa_secret', sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'mfa_secret')
