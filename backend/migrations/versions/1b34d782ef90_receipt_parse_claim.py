"""Persist receipt parse admission across workers and restarts."""

import sqlalchemy as sa
from alembic import op

revision = "1b34d782ef90"
down_revision = "0a23c671de89"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("receipt_imports", sa.Column("parse_started_at", sa.DateTime(), nullable=True))
    op.add_column("receipt_imports", sa.Column("parse_finished_at", sa.DateTime(), nullable=True))
    op.create_index("ix_receipt_owner_parse_started", "receipt_imports", ["user_id", "parse_started_at"])


def downgrade():
    op.drop_index("ix_receipt_owner_parse_started", table_name="receipt_imports")
    op.drop_column("receipt_imports", "parse_finished_at")
    op.drop_column("receipt_imports", "parse_started_at")
