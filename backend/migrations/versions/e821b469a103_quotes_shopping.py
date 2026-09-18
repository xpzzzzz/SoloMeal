"""User prices and versioned shopping drafts."""

import sqlalchemy as sa
from alembic import op

revision = "e821b469a103"
down_revision = "da41905c772e"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("price_quotes",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("ingredient_id", sa.String(36), nullable=False),
        sa.Column("package_quantity", sa.Numeric(11, 3), nullable=False),
        sa.Column("package_price", sa.Numeric(8, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("source", sa.String(80), nullable=False),
        sa.Column("observed_on", sa.Date(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.UniqueConstraint("user_id", "ingredient_id", name="uq_quote_ingredient"),
        sa.ForeignKeyConstraint(["ingredient_id", "user_id"], ["ingredients.id", "ingredients.user_id"]))
    op.create_index("ix_price_quotes_user_id", "price_quotes", ["user_id"])
    op.create_table("shopping_lists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("origin", sa.JSON(), nullable=False),
        sa.Column("items", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_shopping_lists_user_id", "shopping_lists", ["user_id"])


def downgrade():
    op.drop_table("shopping_lists")
    op.drop_table("price_quotes")
