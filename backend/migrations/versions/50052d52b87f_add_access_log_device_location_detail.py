"""add access log device and location detail

Revision ID: 50052d52b87f
Revises: fd8d0fdbf486
Create Date: 2026-08-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '50052d52b87f'
down_revision: Union[str, Sequence[str], None] = 'fd8d0fdbf486'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('access_logs', sa.Column('device_info', sa.String(), nullable=True, server_default=''))
    op.add_column('access_logs', sa.Column('approx_location', sa.String(), nullable=True, server_default=''))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('access_logs', 'approx_location')
    op.drop_column('access_logs', 'device_info')
