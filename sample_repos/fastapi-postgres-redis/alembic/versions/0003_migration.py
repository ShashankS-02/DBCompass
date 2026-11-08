"""Migration 3."""
from alembic import op
import sqlalchemy as sa

revision = "0003"


def upgrade() -> None:
    op.add_column("orders", sa.Column("note_3", sa.String(200), nullable=True))
