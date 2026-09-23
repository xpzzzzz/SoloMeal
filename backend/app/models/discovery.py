from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .food import utcnow
from .identity import new_id


class RecipeDiscoveryBatch(Base):
    """One user-initiated candidate generation; the row is the claim that guards the network call."""

    __tablename__ = "recipe_discovery_batches"
    __table_args__ = (
        UniqueConstraint("user_id", "request_key", name="uq_discovery_request"),
        UniqueConstraint("id", "user_id", name="uq_discovery_owner"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    request_key: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16), default="pending")
    # Conditions actually used: stored preferences merged with the request, never model-authored.
    constraints: Mapped[dict] = mapped_column(JSON, default=dict)
    model_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Null until a provider reports real usage; an estimate never stands in for it.
    usage: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class RecipeDraft(Base):
    __tablename__ = "recipe_drafts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "user_id"],
            ["recipe_discovery_batches.id", "recipe_discovery_batches.user_id"],
        ),
        UniqueConstraint("id", "user_id", name="uq_draft_owner"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    batch_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    validation_errors: Mapped[list] = mapped_column(JSON, default=list)
    validation_warnings: Mapped[list] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(16), default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    accepted_recipe_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
