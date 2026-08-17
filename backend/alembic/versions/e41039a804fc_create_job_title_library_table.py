"""create job title library table

Revision ID: e41039a804fc
Revises: 435a99988f2b
Create Date: 2026-08-18 04:46:14.720998

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e41039a804fc'
down_revision: Union[str, None] = '435a99988f2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('job_title_library',
    sa.Column('ship_component_job_link_id', sa.Integer(), nullable=False),
    sa.Column('vessel_name', sa.String(length=200), nullable=False),
    sa.Column('component_name', sa.String(length=300), nullable=False),
    sa.Column('component_code', sa.String(length=100), nullable=True),
    sa.Column('job_code', sa.String(length=100), nullable=True),
    sa.Column('job_name', sa.String(length=500), nullable=False),
    sa.Column('frequency_type', sa.String(length=100), nullable=True),
    sa.Column('frequency', sa.Integer(), nullable=True),
    sa.Column('alternate_frequency_type', sa.String(length=100), nullable=True),
    sa.Column('alternate_frequency', sa.Integer(), nullable=True),
    sa.Column('responsibility', sa.String(length=200), nullable=True),
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('tenant_id', sa.UUID(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('is_deleted', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_job_title_library_component_name'), 'job_title_library', ['component_name'], unique=False)
    op.create_index(op.f('ix_job_title_library_is_deleted'), 'job_title_library', ['is_deleted'], unique=False)
    op.create_index(op.f('ix_job_title_library_job_name'), 'job_title_library', ['job_name'], unique=False)
    op.create_index(op.f('ix_job_title_library_ship_component_job_link_id'), 'job_title_library', ['ship_component_job_link_id'], unique=False)
    op.create_index(op.f('ix_job_title_library_tenant_id'), 'job_title_library', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_job_title_library_tenant_id'), table_name='job_title_library')
    op.drop_index(op.f('ix_job_title_library_ship_component_job_link_id'), table_name='job_title_library')
    op.drop_index(op.f('ix_job_title_library_job_name'), table_name='job_title_library')
    op.drop_index(op.f('ix_job_title_library_is_deleted'), table_name='job_title_library')
    op.drop_index(op.f('ix_job_title_library_component_name'), table_name='job_title_library')
    sa.drop_table('job_title_library')
