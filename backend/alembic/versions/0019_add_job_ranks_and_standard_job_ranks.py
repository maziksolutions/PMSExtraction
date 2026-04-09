"""Add job rank library and rank fields on standard jobs.

Revision ID: 0019_job_ranks
Revises: 0018
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0019_job_ranks"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "job_ranks",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("tenant_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rank_name", sa.String(length=200), nullable=False),
        sa.Column("normalized_name", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_deleted", sa.Boolean(), nullable=False),
    )
    op.create_index(
        "ix_job_ranks_tenant_norm",
        "job_ranks",
        ["tenant_id", "normalized_name"],
        unique=True,
    )
    op.add_column("standard_jobs", sa.Column("performing_rank", sa.String(length=200), nullable=True))
    op.add_column("standard_jobs", sa.Column("verifying_rank", sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column("standard_jobs", "verifying_rank")
    op.drop_column("standard_jobs", "performing_rank")
    op.drop_index("ix_job_ranks_tenant_norm", table_name="job_ranks")
    op.drop_table("job_ranks")
