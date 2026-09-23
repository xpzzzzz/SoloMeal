from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
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
from .identity import new_id


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Ingredient(Base):
    __tablename__ = "ingredients"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_ingredient_name"),
        UniqueConstraint("id", "user_id", name="uq_ingredient_owner"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    unit: Mapped[str] = mapped_column(String(10))
    is_staple: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class IngredientAlias(Base):
    __tablename__ = "ingredient_aliases"
    __table_args__ = (
        UniqueConstraint("user_id", "alias", name="uq_alias_owner"),
        ForeignKeyConstraint(
            ["ingredient_id", "user_id"], ["ingredients.id", "ingredients.user_id"]
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ingredient_id: Mapped[str] = mapped_column(String(36))
    alias: Mapped[str] = mapped_column(String(80))


class InventoryBatch(Base):
    __tablename__ = "inventory_batches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["ingredient_id", "user_id"], ["ingredients.id", "ingredients.user_id"]
        ),
        UniqueConstraint("id", "user_id", name="uq_batch_owner"),
        CheckConstraint("quantity >= 0", name="ck_batch_nonnegative"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    ingredient_id: Mapped[str] = mapped_column(String(36))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    expires_on: Mapped[date | None] = mapped_column(Date)
    expiry_source: Mapped[str] = mapped_column(String(16), default="unknown")
    location: Mapped[str] = mapped_column(String(40), default="fridge")
    version: Mapped[int] = mapped_column(Integer, default=1)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Operation(Base):
    __tablename__ = "operations"
    __table_args__ = (
        UniqueConstraint("user_id", "key", name="uq_operation_key"),
        UniqueConstraint("id", "user_id", name="uq_operation_owner"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    key: Mapped[str] = mapped_column(String(80))
    request_hash: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(30))
    result: Mapped[dict] = mapped_column(JSON, default=dict)


class InventoryEvent(Base):
    __tablename__ = "inventory_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["batch_id", "user_id"], ["inventory_batches.id", "inventory_batches.user_id"]
        ),
        ForeignKeyConstraint(["operation_id", "user_id"], ["operations.id", "operations.user_id"]),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    batch_id: Mapped[str] = mapped_column(String(36))
    operation_id: Mapped[str] = mapped_column(String(36))
    delta: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    reason: Mapped[str] = mapped_column(String(20))
    batch_version: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Recipe(Base):
    __tablename__ = "recipes"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_recipe_owner"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    servings: Mapped[int] = mapped_column(Integer)
    minutes: Mapped[int] = mapped_column(Integer)
    equipment: Mapped[list] = mapped_column(JSON)
    steps: Mapped[list] = mapped_column(JSON)
    source: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    # Legacy `source` stays the human-readable note; these record how the row was produced.
    source_type: Mapped[str] = mapped_column(String(16), default="manual", server_default="manual")
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Nullable because rows written before tags exist must read as "no tags" rather than
    # inherit a guess; MySQL cannot add a NOT NULL JSON column with a default.
    cooking_methods: Mapped[list | None] = mapped_column(JSON, nullable=True)


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        ForeignKeyConstraint(["recipe_id", "user_id"], ["recipes.id", "recipes.user_id"]),
        ForeignKeyConstraint(
            ["ingredient_id", "user_id"], ["ingredients.id", "ingredients.user_id"]
        ),
        UniqueConstraint("recipe_id", "ingredient_id", name="uq_recipe_ingredient"),
        CheckConstraint("quantity > 0", name="ck_recipe_quantity"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    recipe_id: Mapped[str] = mapped_column(String(36))
    ingredient_id: Mapped[str] = mapped_column(String(36))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
    optional: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class RecipeFeedback(Base):
    __tablename__ = "recipe_feedback"
    __table_args__ = (
        ForeignKeyConstraint(["recipe_id", "user_id"], ["recipes.id", "recipes.user_id"]),
        UniqueConstraint("user_id", "recipe_id", name="uq_feedback_recipe"),
        CheckConstraint("rating IN ('neutral', 'like', 'dislike')", name="ck_feedback_rating"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipe_id: Mapped[str] = mapped_column(String(36))
    # Wanting to keep a recipe is not the same as liking it, so the two stay independent.
    favorite: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    rating: Mapped[str] = mapped_column(String(8), default="neutral", server_default="neutral")
    version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CookingRecord(Base):
    __tablename__ = "cooking_records"
    __table_args__ = (UniqueConstraint("id", "user_id", name="uq_cook_owner"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    recipe_snapshot: Mapped[dict] = mapped_column(JSON)
    servings: Mapped[int] = mapped_column(Integer)
    actual_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_source: Mapped[str | None] = mapped_column(String(8), nullable=True)
    feedback_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    status: Mapped[str] = mapped_column(String(16), default="completed")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CookingConsumption(Base):
    __tablename__ = "cooking_consumptions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["cooking_id", "user_id"], ["cooking_records.id", "cooking_records.user_id"]
        ),
        ForeignKeyConstraint(
            ["batch_id", "user_id"], ["inventory_batches.id", "inventory_batches.user_id"]
        ),
        CheckConstraint("quantity > 0", name="ck_consumption_quantity"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    cooking_id: Mapped[str] = mapped_column(String(36), index=True)
    batch_id: Mapped[str] = mapped_column(String(36))
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3))
