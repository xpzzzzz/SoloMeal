"""Persist receipt confirmation result without rebuilding existing imports."""

import sqlalchemy as sa
from alembic import op

revision = "0a23c671de89"
down_revision = "f912a570bc24"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("receipt_imports", sa.Column("result", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("receipt_imports", "result")
