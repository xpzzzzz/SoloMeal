from sqlalchemy import JSON, ForeignKey, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .identity import new_id


class AgentSession(Base):
    __tablename__ = "agent_sessions"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_agent_session_owner"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(80))
    version: Mapped[int] = mapped_column(Integer, default=1)
    latest_run_id: Mapped[str | None] = mapped_column(String(36))


class AgentRun(Base):
    __tablename__ = "agent_runs"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_run_owner"),
        ForeignKeyConstraint(["session_id", "user_id"], ["agent_sessions.id", "agent_sessions.user_id"],
                             name="fk_run_session_owner"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    session_id: Mapped[str | None] = mapped_column(String(36), index=True)
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    context_summary: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="ready")
    messages: Mapped[list] = mapped_column(JSON)
    pending: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    steps: Mapped[int] = mapped_column(Integer, default=0)
    event_seq: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    lease: Mapped[str] = mapped_column(String(36), default="")
    lease_until: Mapped[int] = mapped_column(Integer, default=0)


class ToolExecution(Base):
    __tablename__ = "tool_executions"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "user_id"], ["agent_runs.id", "agent_runs.user_id"]),
        UniqueConstraint("run_id", "step", name="uq_run_step"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(String(36))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    step: Mapped[int] = mapped_column(Integer)
    tool: Mapped[str] = mapped_column(String(80))
    arguments: Mapped[dict] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON)
    elapsed_ms: Mapped[int] = mapped_column(Integer)


class RunEvent(Base):
    __tablename__ = "agent_run_events"
    __table_args__ = (
        ForeignKeyConstraint(["run_id", "user_id"], ["agent_runs.id", "agent_runs.user_id"]),
    )
    run_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    payload: Mapped[dict] = mapped_column(JSON)
