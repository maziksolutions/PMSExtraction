"""Add no_extraction_reason column to manual_page_extractions

Revision ID: 0028_add_no_extraction_reason
Revises: 0027_add_manual_page_ref_history
Create Date: 2026-11-11
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '0028_add_no_extraction_reason'
down_revision = '0027_add_manual_page_ref_history'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"

    if is_postgres:
        op.execute("""
            ALTER TABLE manual_page_extractions 
            ADD COLUMN IF NOT EXISTS no_extraction_reason TEXT;
        """)
    else:
        # SQLite idempotent column add
        try:
            op.add_column('manual_page_extractions', sa.Column('no_extraction_reason', sa.Text(), nullable=True))
        except Exception:
            pass


def downgrade() -> None:
    conn = op.get_bind()
    is_postgres = conn.dialect.name == "postgresql"
    if is_postgres:
        op.execute("ALTER TABLE manual_page_extractions DROP COLUMN IF EXISTS no_extraction_reason;")
    else:
        try:
            op.drop_column('manual_page_extractions', 'no_extraction_reason')
        except Exception:
            pass
