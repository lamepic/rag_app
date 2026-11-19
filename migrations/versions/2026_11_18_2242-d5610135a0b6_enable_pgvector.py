"""enable pgvector

Revision ID: d5610135a0b6
Revises:
Create Date: 2026-11-18 22:42:31.048475

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d5610135a0b6"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Turn on pgvector. Supabase keeps extensions in the `extensions` schema."""
    op.execute("CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA extensions")


def downgrade() -> None:
    """Turn off pgvector.

    No CASCADE on purpose: once vector columns exist, this fails instead of
    silently dropping every embedding. Drop those tables in their own migration first.
    """
    op.execute("DROP EXTENSION IF EXISTS vector")
