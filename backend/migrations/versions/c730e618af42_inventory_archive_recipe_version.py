"""Inventory archive and optimistic recipe edits."""

import sqlalchemy as sa
from alembic import op

revision = "c730e618af42"
down_revision = "92d9cff900d6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("inventory_batches", sa.Column("archived", sa.Boolean(), nullable=False, server_default="0"))
    op.add_column("recipes", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("inventory_events", sa.Column("batch_version", sa.Integer(), nullable=True))


def downgrade():
    op.drop_column("inventory_events", "batch_version")
    op.drop_column("recipes", "version")
    op.drop_column("inventory_batches", "archived")
