"""add card revocation and access log seen flag

Revision ID: fd8d0fdbf486
Revises: a22cb7a2bddb
Create Date: 2026-08-26 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'fd8d0fdbf486'
down_revision: Union[str, Sequence[str], None] = 'a22cb7a2bddb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('patients', sa.Column('is_revoked', sa.Boolean(), nullable=True, server_default=sa.false()))
    op.add_column('patients', sa.Column('revoked_at', sa.DateTime(), nullable=True))
    op.add_column('access_logs', sa.Column('seen', sa.Boolean(), nullable=True, server_default=sa.false()))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('access_logs', 'seen')
    op.drop_column('patients', 'revoked_at')
    op.drop_column('patients', 'is_revoked')
