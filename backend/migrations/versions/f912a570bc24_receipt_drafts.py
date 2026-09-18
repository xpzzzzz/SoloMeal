"""Private receipt uploads and editable drafts; no inventory mutation."""
import sqlalchemy as sa
from alembic import op

revision = "f912a570bc24"
down_revision = "e821b469a103"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("receipt_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("file_key", sa.String(36), nullable=False, unique=True),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("media_type", sa.String(32), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("parse_status", sa.String(16), nullable=False),
        sa.Column("parsed", sa.JSON(), nullable=False),
        sa.Column("draft", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_receipt_imports_user_id", "receipt_imports", ["user_id"])
    op.create_index("ix_receipt_owner_hash", "receipt_imports", ["user_id", "file_hash"])


def downgrade():
    op.drop_table("receipt_imports")
