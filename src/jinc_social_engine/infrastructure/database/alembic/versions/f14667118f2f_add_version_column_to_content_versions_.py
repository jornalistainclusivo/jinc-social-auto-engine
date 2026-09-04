"""Add version column to content_versions for CAS

Revision ID: f14667118f2f
Revises: f7b1efe054a0
Create Date: 2026-09-03 21:26:19.369719

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f14667118f2f"
down_revision: str | Sequence[str] | None = "f7b1efe054a0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "content_versions",
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("content_versions", "version")
