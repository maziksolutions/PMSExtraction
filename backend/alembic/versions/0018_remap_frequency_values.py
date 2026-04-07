"""No-op: frequency remapping was folded into migration 0017

Revision ID: 0018
Revises: 0017
Create Date: 2026-04-07

All work originally planned here was moved into 0017 to avoid the PostgreSQL
ALTER TYPE ADD VALUE transaction restriction. This migration exists only to
preserve the revision chain.
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
