"""Independent agent conversations and bounded context."""

import sqlalchemy as sa
from alembic import op

revision = "da41905c772e"
down_revision = "c730e618af42"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("agent_sessions",
                    sa.Column("id", sa.String(36), primary_key=True),
                    sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
                    sa.Column("title", sa.String(80), nullable=False),
                    sa.Column("version", sa.Integer(), nullable=False),
                    sa.Column("latest_run_id", sa.String(36)),
                    sa.UniqueConstraint("id", "user_id", name="uq_agent_session_owner"))
    op.create_index("ix_agent_sessions_user_id", "agent_sessions", ["user_id"])
    with op.batch_alter_table("agent_runs") as batch:
        batch.add_column(sa.Column("session_id", sa.String(36)))
        batch.add_column(sa.Column("constraints", sa.JSON(), nullable=True))
        batch.add_column(sa.Column("context_summary", sa.JSON(), nullable=True))
        batch.create_foreign_key("fk_run_session_owner", "agent_sessions",
                                 ["session_id", "user_id"], ["id", "user_id"])
        batch.create_index("ix_agent_runs_session_id", ["session_id"])
    bind = op.get_bind()
    runs = sa.table("agent_runs", sa.column("id"), sa.column("user_id"), sa.column("session_id"),
                    sa.column("constraints", sa.JSON()), sa.column("context_summary", sa.JSON()))
    sessions = sa.table("agent_sessions", sa.column("id"), sa.column("user_id"),
                        sa.column("title"), sa.column("version"), sa.column("latest_run_id"))
    # Legacy parent references were not persisted: retain each old run as its own conversation.
    for row in bind.execute(sa.select(runs.c.id, runs.c.user_id)).mappings().all():
        bind.execute(sessions.insert().values(id=row["id"], user_id=row["user_id"],
                     title="历史对话", version=1, latest_run_id=row["id"]))
        bind.execute(runs.update().where(runs.c.id == row["id"]).values(
            session_id=row["id"], constraints={}, context_summary={}))
    with op.batch_alter_table("agent_runs") as batch:
        batch.alter_column("constraints", existing_type=sa.JSON(), nullable=False)
        batch.alter_column("context_summary", existing_type=sa.JSON(), nullable=False)


def downgrade():
    with op.batch_alter_table("agent_runs") as batch:
        batch.drop_constraint("fk_run_session_owner", type_="foreignkey")
        batch.drop_index("ix_agent_runs_session_id")
        batch.drop_column("context_summary")
        batch.drop_column("constraints")
        batch.drop_column("session_id")
    # Drop the table with its FK-supporting index; MySQL cannot drop that index first.
    op.drop_table("agent_sessions")
