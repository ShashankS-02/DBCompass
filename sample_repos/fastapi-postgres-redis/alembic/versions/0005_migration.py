"""Migration 5."""
from alembic import op
import sqlalchemy as sa

revision = "0005"


def upgrade() -> None:
    op.add_column("orders", sa.Column("note_5", sa.String(200), nullable=True))
