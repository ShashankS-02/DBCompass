"""Migration 1."""
from alembic import op
import sqlalchemy as sa

revision = "0001"


def upgrade() -> None:
    op.create_table("customers", sa.Column("id", sa.Integer, primary_key=True))
