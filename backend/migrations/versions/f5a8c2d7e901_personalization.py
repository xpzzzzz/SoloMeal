"""Persist the independent implicit preference switch."""

import sqlalchemy as sa
from alembic import op

revision = "f5a8c2d7e901"
down_revision = "e4a7c1b9d305"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("user_preferences", sa.Column("personalization_enabled", sa.Boolean(), nullable=False, server_default="1"))


def downgrade():
    op.drop_column("user_preferences", "personalization_enabled")
