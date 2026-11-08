"""Migration 6."""
from alembic import op
import sqlalchemy as sa

revision = "0006"


def upgrade() -> None:
    op.add_column("orders", sa.Column("note_6", sa.String(200), nullable=True))
