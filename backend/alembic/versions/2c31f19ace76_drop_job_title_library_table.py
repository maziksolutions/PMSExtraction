"""drop job title library table

Revision ID: 2c31f19ace76
Revises: e41039a804fc
Create Date: 2026-08-19 15:08:07.795434

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c31f19ace76'
down_revision: Union[str, None] = 'e41039a804fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('job_title_library')


def downgrade() -> None:
    pass
