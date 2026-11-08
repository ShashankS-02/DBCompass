"""Migration 4."""
from alembic import op
import sqlalchemy as sa

revision = "0004"


def upgrade() -> None:
    op.add_column("orders", sa.Column("note_4", sa.String(200), nullable=True))
