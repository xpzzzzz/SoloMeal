"""Recipe favorites, like/dislike feedback and cooking method tags."""

import sqlalchemy as sa
from alembic import op

revision = "b52e9c4a7d18"
down_revision = "a71f0d4c9b23"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("recipe_feedback",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("recipe_id", sa.String(36), nullable=False),
        sa.Column("favorite", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("rating", sa.String(8), nullable=False, server_default="neutral"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["recipe_id", "user_id"], ["recipes.id", "recipes.user_id"]),
        sa.UniqueConstraint("user_id", "recipe_id", name="uq_feedback_recipe"),
        sa.CheckConstraint("rating IN ('neutral', 'like', 'dislike')", name="ck_feedback_rating"))
    op.create_index("ix_recipe_feedback_user_id", "recipe_feedback", ["user_id"])

    # NULL is what a pre-tag recipe reads as: an empty list. Tags are never inferred for
    # existing rows, and MySQL will not accept NOT NULL JSON with a default here.
    op.add_column("recipes", sa.Column("cooking_methods", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("recipes", "cooking_methods")
    op.drop_index("ix_recipe_feedback_user_id", table_name="recipe_feedback")
    op.drop_table("recipe_feedback")
