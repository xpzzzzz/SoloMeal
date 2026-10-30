from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .food import utcnow
from .identity import new_id


class ProactiveItem(Base):
    __tablename__ = "proactive_items"
    __table_args__ = (
        UniqueConstraint("user_id", "dedupe_key", name="uq_proactive_dedupe"),
        UniqueConstraint("user_id", "delivery_slot", name="uq_proactive_daily_slot"),
        Index("ix_proactive_inbox", "user_id", "status", "priority", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    kind: Mapped[str] = mapped_column(String(32))
    subject_key: Mapped[str] = mapped_column(String(128))
    dedupe_key: Mapped[str] = mapped_column(String(200))
    delivery_slot: Mapped[str] = mapped_column(String(16))
    priority: Mapped[int] = mapped_column(SmallInteger)
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(String(500))
    why: Mapped[str] = mapped_column(String(300))
    payload: Mapped[dict] = mapped_column(JSON)
    snapshot_version: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    action_completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ProactiveSetting(Base):
    __tablename__ = "proactive_settings"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    daily_limit: Mapped[int] = mapped_column(SmallInteger, default=1, server_default="1")
    quiet_start: Mapped[str] = mapped_column(String(5), default="22:00", server_default="22:00")
    quiet_end: Mapped[str] = mapped_column(String(5), default="08:00", server_default="08:00")
    snooze_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
