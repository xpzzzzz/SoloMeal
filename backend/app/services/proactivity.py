"""Read-only signal collection for proactive suggestions; no model is involved."""

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone

from sqlalchemy import select

from ..models.food import Ingredient, InventoryBatch, Recipe, RecipeIngredient
from ..models.shopping import ShoppingList
from .home import SHANGHAI, shanghai_day
from .quantities import format_quantity

# M1 plan section 5: only today/tomorrow and drafts at least 48 hours old.
EXPIRING_DAYS = 1
STALE_HOURS = 48


@dataclass(frozen=True)
class Signal:
    kind: str
    subject_key: str
    priority: int
    title: str
    body: str
    why: str
    payload: dict
    snapshot_version: int
    expires_at: datetime | None


@dataclass(frozen=True)
class DecisionContext:
    now: datetime
    enabled: bool = True
    daily_limit: int = 1
    used_today: int = 0
    quiet_start: str = "22:00"
    quiet_end: str = "08:00"
    snooze_until: datetime | None = None
    suppressed_kinds: frozenset[str] = frozenset()


def in_quiet_hours(now: datetime, start: str, end: str) -> bool:
    current = now.astimezone(SHANGHAI).time().replace(tzinfo=None)
    first, last = time.fromisoformat(start), time.fromisoformat(end)
    if first == last:
        return False
    return first <= current < last if first < last else current >= first or current < last


def select_signals(signals: list[Signal], ctx: DecisionContext) -> list[Signal]:
    if not ctx.enabled or (ctx.snooze_until and ctx.now < _utc(ctx.snooze_until)):
        return []
    if in_quiet_hours(ctx.now, ctx.quiet_start, ctx.quiet_end):
        return []
    room = max(0, ctx.daily_limit - ctx.used_today)
    candidates = [item for item in signals if item.kind not in ctx.suppressed_kinds]
    candidates.sort(key=lambda item: (-item.priority, item.expires_at or datetime.max.replace(tzinfo=timezone.utc),
                                      item.subject_key))
    return candidates[:room]


def build_action(payload: dict) -> dict:
    if payload.get("kind") == "shopping_stale":
        return {"type": "open_shopping", "shopping_id": payload["shopping_id"]}
    if payload.get("recipe_id"):
        return {"type": "open_plan_flow", "recipe_id": payload["recipe_id"], "prefill": {"servings": 1}}
    return {"type": "open_inventory", "batch_id": payload["batch_id"]}


def _utc(value: datetime) -> datetime:
    # Existing database DATETIME columns store UTC without a timezone.
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def collect(db, user_id: str, now: datetime) -> list[Signal]:
    """Read signals for a user at an explicitly supplied, timezone-aware instant."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    today = shanghai_day(now)
    rows = db.execute(
        select(InventoryBatch, Ingredient)
        .join(Ingredient, (InventoryBatch.ingredient_id == Ingredient.id)
              & (InventoryBatch.user_id == Ingredient.user_id))
        .where(InventoryBatch.user_id == user_id, InventoryBatch.archived.is_(False),
               InventoryBatch.quantity > 0, InventoryBatch.expires_on >= today,
               InventoryBatch.expires_on <= today + timedelta(days=EXPIRING_DAYS))
        .order_by(InventoryBatch.expires_on, InventoryBatch.id)
    ).all()
    signals = []
    for batch, ingredient in rows:
        recipes = db.scalars(
            select(Recipe).join(RecipeIngredient, (Recipe.id == RecipeIngredient.recipe_id)
                                & (Recipe.user_id == RecipeIngredient.user_id))
            .where(Recipe.user_id == user_id, RecipeIngredient.ingredient_id == ingredient.id)
            .order_by(Recipe.name, Recipe.id)
        ).all()
        recipe = recipes[0] if recipes else None
        days = (batch.expires_on - today).days
        expiry = "今天" if days == 0 else "明天"
        quantity = format_quantity(batch.quantity, ingredient.unit)
        payload = {"kind": "expiring_batch", "batch_id": batch.id,
                   "ingredient_id": ingredient.id, "ingredient_name": ingredient.name,
                   "quantity": str(batch.quantity), "unit": ingredient.unit,
                   "expires_on": batch.expires_on.isoformat(), "days_left": days,
                   "recipe_id": recipe.id if recipe else None,
                   "recipe_name": recipe.name if recipe else None,
                   "recipe_minutes": recipe.minutes if recipe else None}
        expires_at = datetime.combine(batch.expires_on + timedelta(days=1), time.min, SHANGHAI).astimezone(timezone.utc)
        signals.append(Signal(
            "expiring_batch", f"batch:{batch.id}", 90 if days == 0 else 80,
            f"{ingredient.name} {quantity} {expiry}到期",
            f"可以考虑做「{recipe.name}」" if recipe else "可以考虑尽快使用这份食材",
            f"{expiry}到期 · {len(recipes)} 道菜谱可用", payload, batch.version, expires_at,
        ))
    drafts = db.scalars(select(ShoppingList).where(
        ShoppingList.user_id == user_id, ShoppingList.status == "draft",
        ShoppingList.created_at <= (now.astimezone(timezone.utc) - timedelta(hours=STALE_HOURS)).replace(tzinfo=None),
    ).order_by(ShoppingList.created_at, ShoppingList.id)).all()
    for draft in drafts:
        checked = {str(value) for value in draft.checked_ingredient_ids or []}
        pending = sum(str(item["ingredient_id"]) not in checked for item in draft.items)
        if not pending:
            continue
        created = _utc(draft.created_at)
        days = (now.astimezone(timezone.utc) - created).days
        name = draft.origin.get("recipe_name") or "采购清单"
        payload = {"kind": "shopping_stale", "shopping_id": draft.id, "recipe_name": name,
                   "items_count": len(draft.items), "pending_count": pending,
                   "created_at": created.isoformat().replace("+00:00", "Z")}
        signals.append(Signal("shopping_stale", f"shopping:{draft.id}", 50,
                              f"{name}已放置 {days} 天", f"还有 {pending} 项未勾选",
                              f"采购草稿已超过 {STALE_HOURS} 小时", payload, draft.version, None))
    return signals
