"""Recipe discovery batches, editable drafts and recipe provenance columns."""

import sqlalchemy as sa
from alembic import op

revision = "a71f0d4c9b23"
down_revision = "1b34d782ef90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("recipe_discovery_batches",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("request_key", sa.String(80), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("constraints", sa.JSON(), nullable=False),
        sa.Column("model_name", sa.String(120), nullable=True),
        sa.Column("usage", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(40), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("user_id", "request_key", name="uq_discovery_request"),
        sa.UniqueConstraint("id", "user_id", name="uq_discovery_owner"))
    op.create_index("ix_recipe_discovery_batches_user_id", "recipe_discovery_batches", ["user_id"])

    op.create_table("recipe_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("batch_id", sa.String(36), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("validation_errors", sa.JSON(), nullable=False),
        sa.Column("validation_warnings", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(16), nullable=False),
        sa.Column("source_ref", sa.String(500), nullable=True),
        # Kept as a plain reference: deleting an accepted recipe must stay possible.
        sa.Column("accepted_recipe_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["batch_id", "user_id"],
                                ["recipe_discovery_batches.id", "recipe_discovery_batches.user_id"]),
        sa.UniqueConstraint("id", "user_id", name="uq_draft_owner"))
    op.create_index("ix_recipe_drafts_user_id", "recipe_drafts", ["user_id"])
    op.create_index("ix_recipe_drafts_batch_id", "recipe_drafts", ["batch_id"])

    # Existing rows keep their old录入方式 as manual; nothing is inferred about their author.
    op.add_column("recipes", sa.Column("source_type", sa.String(16), nullable=False,
                                       server_default="manual"))
    op.add_column("recipes", sa.Column("source_ref", sa.String(500), nullable=True))


def downgrade():
    op.drop_column("recipes", "source_ref")
    op.drop_column("recipes", "source_type")
    op.drop_index("ix_recipe_drafts_batch_id", table_name="recipe_drafts")
    op.drop_index("ix_recipe_drafts_user_id", table_name="recipe_drafts")
    op.drop_table("recipe_drafts")
    op.drop_index("ix_recipe_discovery_batches_user_id", table_name="recipe_discovery_batches")
    op.drop_table("recipe_discovery_batches")
