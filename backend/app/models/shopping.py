from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..core.database import Base
from .food import utcnow
from .identity import new_id


class SavedQuote(Base):
    __tablename__ = "price_quotes"
    __table_args__ = (
        UniqueConstraint("user_id", "ingredient_id", name="uq_quote_ingredient"),
        ForeignKeyConstraint(["ingredient_id", "user_id"], ["ingredients.id", "ingredients.user_id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ingredient_id: Mapped[str] = mapped_column(String(36))
    package_quantity: Mapped[Decimal] = mapped_column(Numeric(11, 3))
    package_price: Mapped[Decimal] = mapped_column(Numeric(8, 2))
    currency: Mapped[str] = mapped_column(String(3), default="CNY")
    source: Mapped[str] = mapped_column(String(80))
    observed_on: Mapped[date] = mapped_column(Date)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ShoppingList(Base):
    __tablename__ = "shopping_lists"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # Immutable provenance and validated decimal strings; items are edited as one version.
    origin: Mapped[dict] = mapped_column(JSON)
    items: Mapped[list] = mapped_column(JSON)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
