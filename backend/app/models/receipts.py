from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.mysql import DATETIME

from ..core.database import Base
from .food import utcnow
from .identity import new_id

PRECISE_TIME = DateTime().with_variant(DATETIME(fsp=6), "mysql")


class ReceiptImport(Base):
    __tablename__ = "receipt_imports"
    __table_args__ = (Index("ix_receipt_owner_hash", "user_id", "file_hash"),
                      Index("ix_receipt_owner_parse_started", "user_id", "parse_started_at"))
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    file_key: Mapped[str] = mapped_column(String(36), unique=True)
    file_hash: Mapped[str] = mapped_column(String(64))
    media_type: Mapped[str] = mapped_column(String(32))
    byte_size: Mapped[int] = mapped_column(Integer)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    parse_status: Mapped[str] = mapped_column(String(16), default="manual")
    # Immutable parser output stays separate from user corrections.
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)
    draft: Mapped[dict] = mapped_column(JSON, default=lambda: {"purchased_on": None, "items": []})
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parse_started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parse_finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    parse_task_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    parse_deadline_at: Mapped[datetime | None] = mapped_column(PRECISE_TIME, nullable=True)
    parse_error: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recognition: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReceiptParseTask(Base):
    """MySQL execution state and persistent outbox; RabbitMQ carries only this ID."""
    __tablename__ = "receipt_parse_tasks"
    __table_args__ = (
        Index("ix_receipt_task_dispatch", "status", "dispatch_after"),
        Index("ix_receipt_task_lease", "status", "lease_until"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    receipt_id: Mapped[str] = mapped_column(ForeignKey("receipt_imports.id"), unique=True)
    operation_id: Mapped[str] = mapped_column(ForeignKey("operations.id"), unique=True)
    expected_version: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(16), default="vlm_only", server_default="vlm_only")
    status: Mapped[str] = mapped_column(String(16), default="queued")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer)
    deadline_at: Mapped[datetime] = mapped_column(PRECISE_TIME)
    available_at: Mapped[datetime] = mapped_column(PRECISE_TIME, default=utcnow)
    dispatch_after: Mapped[datetime] = mapped_column(PRECISE_TIME, default=utcnow)
    publish_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    publish_until: Mapped[datetime | None] = mapped_column(PRECISE_TIME, nullable=True)
    dispatch_attempts: Mapped[int] = mapped_column(Integer, default=0)
    dispatched_at: Mapped[datetime | None] = mapped_column(PRECISE_TIME, nullable=True)
    lease_token: Mapped[str | None] = mapped_column(String(36), nullable=True)
    lease_until: Mapped[datetime | None] = mapped_column(PRECISE_TIME, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(32), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(PRECISE_TIME, nullable=True)
    created_at: Mapped[datetime] = mapped_column(PRECISE_TIME, default=utcnow)
