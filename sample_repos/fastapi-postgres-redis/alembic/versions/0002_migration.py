"""Migration 2."""
from alembic import op
import sqlalchemy as sa

revision = "0002"


def upgrade() -> None:
    op.add_column("orders", sa.Column("note_2", sa.String(200), nullable=True))
