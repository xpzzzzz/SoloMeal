from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .food import utcnow
from .identity import new_id


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
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
