"""Read-only "today" home aggregate. Four blocks, each of which may fail alone.

Nothing here recomputes a recommendation, a shortage or a cooking deduction: the
recommendation block calls the existing planner, and the other three only project
rows the owning endpoints already expose.
"""

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select

from ..core.errors import AppError
from ..models.food import CookingRecord, Ingredient, InventoryBatch
from ..models.shopping import ShoppingList
from ..schemas.planning import PlanningInput
from .food import feedback_map
from .planning import recommend

ATTENTION_DAYS = 3
ATTENTION_LIMIT = 5
SHOPPING_LIMIT = 3
RECENT_LIMIT = 5
SECTIONS = ("attention", "recommendations", "shopping", "recent")
# Asia/Shanghai has no DST, so a fixed offset keeps the display rule portable on
# hosts without the optional IANA tzdata package (the same call personalization makes).
SHANGHAI = timezone(timedelta(hours=8))
HOME_SECTION_FAILED = "HOME_SECTION_FAILED"


def utc_today(now: datetime) -> date:
    return now.astimezone(timezone.utc).date()


def shanghai_day(value: datetime) -> date:
    naive = value.tzinfo is None
    return (value.replace(tzinfo=timezone.utc) if naive else value).astimezone(SHANGHAI).date()


def _batch_conditions():
    return (
        InventoryBatch.archived.is_(False),
        InventoryBatch.quantity > 0,
        InventoryBatch.expires_on.is_not(None),
    )


def attention(db, user_id, today):
    """Expired first, then the three-day window: the list a user should act on now."""
    window = today + timedelta(days=ATTENTION_DAYS)
    rows = db.execute(
        select(InventoryBatch, Ingredient)
        .join(Ingredient, InventoryBatch.ingredient_id == Ingredient.id)
        .where(InventoryBatch.user_id == user_id, *_batch_conditions())
        .where(InventoryBatch.expires_on <= window)
        .order_by(InventoryBatch.expires_on, Ingredient.name, InventoryBatch.id)
        .limit(ATTENTION_LIMIT)
    ).all()

    # Counted over every batch, not the five shown, so the queue can never understate itself.
    def counted(*extra):
        return int(db.scalar(
            select(func.count())
            .select_from(InventoryBatch)
            .join(Ingredient, InventoryBatch.ingredient_id == Ingredient.id)
            .where(InventoryBatch.user_id == user_id, *_batch_conditions(), *extra)
        ) or 0)

    expired = counted(InventoryBatch.expires_on < today)
    soon = counted(InventoryBatch.expires_on >= today, InventoryBatch.expires_on <= window)
    return {
        "days": ATTENTION_DAYS,
        "items": [
            {
                "batch_id": batch.id,
                "ingredient_id": batch.ingredient_id,
                "name": item.name,
                "quantity": str(batch.quantity),
                "unit": item.unit,
                "location": batch.location,
                "expires_on": batch.expires_on.isoformat(),
                "days_left": (batch.expires_on - today).days,
                "state": "expired" if batch.expires_on < today else "expiring_soon",
                "version": batch.version,
            }
            for batch, item in rows
        ],
        "expired_count": expired,
        "expiring_count": soon,
        "total_count": expired + soon,
        "truncated": expired + soon > len(rows),
    }


def recommendations(db, user_id, today):
    """The reviewed planner's own answer, echoed as a request so the shared panel can reuse it."""
    body = PlanningInput(scenario="default")
    result = recommend(db, user_id, body)
    return {
        **result,
        # Cards need the saved favourite to show its real state, not to guess it.
        "favorites": feedback_map(db, user_id, [c["recipe"]["id"] for c in result["candidates"]]),
        "request": {
            "scenario": body.scenario,
            "score_weights": body.score_weights.model_dump(),
            "max_minutes": None,
            "include_optional": body.include_optional,
            "budget": None,
        },
        "shown_limit": 3,
    }


def shopping(db, user_id, today):
    """Unfinished lists, aggregated across every row rather than the first page."""
    drafts = db.scalars(
        select(ShoppingList)
        .where(ShoppingList.user_id == user_id, ShoppingList.status == "draft")
        .order_by(ShoppingList.created_at.desc(), ShoppingList.id.desc())
    ).all()
    items = []
    pending_total = 0
    for row in drafts:
        checked = {str(x) for x in row.checked_ingredient_ids or []}
        pending = len([x for x in row.items if str(x["ingredient_id"]) not in checked])
        pending_total += pending
        items.append({
            "id": row.id,
            "version": row.version,
            "kind": row.origin.get("kind", "single_plan"),
            "recipe_name": row.origin.get("recipe_name", ""),
            "items_count": len(row.items),
            "pending_count": pending,
            "created_at": row.created_at.isoformat(),
        })
    return {
        "items": items[:SHOPPING_LIMIT],
        "list_count": len(drafts),
        "pending_total": pending_total,
        "truncated": len(drafts) > SHOPPING_LIMIT,
    }


def recent(db, user_id, today):
    """Completed records only; a retracted meal stays visible in history but counts as nothing."""
    completed = int(db.scalar(
        select(func.count())
        .select_from(CookingRecord)
        .where(CookingRecord.user_id == user_id, CookingRecord.status == "completed")
    ) or 0)
    rows = db.scalars(
        select(CookingRecord)
        .where(CookingRecord.user_id == user_id, CookingRecord.status == "completed")
        .order_by(CookingRecord.created_at.desc(), CookingRecord.id.desc())
        .limit(RECENT_LIMIT)
    ).all()
    return {
        "completed_count": completed,
        "items": [
            {
                "id": row.id,
                "recipe_name": (row.recipe_snapshot or {}).get("name", ""),
                "servings": row.servings,
                "cooked_on": shanghai_day(row.created_at).isoformat(),
                "actual_minutes": row.actual_minutes,
                "duration_source": row.duration_source,
            }
            for row in rows
        ],
        "truncated": completed > len(rows),
    }


BUILDERS = {
    # Every builder takes the same arguments so one block can be retried alone.
    "attention": attention,
    "recommendations": recommendations,
    "shopping": shopping,
    "recent": recent,
}


def _meta(now: datetime) -> dict:
    today = utc_today(now)
    # Validity is UTC; the page names the day the user is living through, which is
    # the same calendar day for every Asia/Shanghai viewer.
    return {
        "as_of": today.isoformat(),
        "display_date": shanghai_day(now).isoformat(),
        "timezone": "Asia/Shanghai",
    }


def selected(names: str | None):
    """Which blocks to compute; a refresh of the cheap blocks must not re-run the planner."""
    if names is None:
        return SECTIONS
    wanted = tuple(dict.fromkeys(n for n in names.split(",") if n))
    if not wanted or any(n not in BUILDERS for n in wanted):
        raise AppError(422, "VALIDATION_ERROR", "Unknown home section requested")
    return wanted


def build(db, user_id, names=SECTIONS):
    """One envelope per block: a failure is reported in that block, never as a blank page."""
    now = datetime.now(timezone.utc)
    today = utc_today(now)
    sections = {}
    for name in names:
        try:
            sections[name] = {"status": "ok", "data": BUILDERS[name](db, user_id, today)}
        except Exception as exc:
            # A statement error leaves the session unusable, so the next block starts fresh.
            db.rollback()
            sections[name] = {
                "status": "error",
                "error": {"code": HOME_SECTION_FAILED, "message": type(exc).__name__},
            }
    return {**_meta(now), "sections": sections}


def build_section(db, user_id, name):
    if name not in BUILDERS:
        return None
    now = datetime.now(timezone.utc)
    section = build(db, user_id, (name,))["sections"][name]
    return {**_meta(now), "section": name, **section}
