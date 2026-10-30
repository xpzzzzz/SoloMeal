"""Persistence and state transitions for proactive suggestions."""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..core.errors import AppError
from ..models.food import InventoryBatch, Recipe
from ..models.identity import User
from ..models.proactivity import ProactiveItem, ProactiveSetting
from ..models.shopping import ShoppingList
from .food import run_operation
from .home import shanghai_day
from .proactivity import DecisionContext, _utc, build_action, collect, select_signals

# M1 plan section 5: three consecutive dismissals suppress the kind for seven days.
DISMISSAL_STREAK = 3
SUPPRESSION_DAYS = 7


def expire_overdue(db, now: datetime, user_id: str | None = None) -> int:
    query = update(ProactiveItem).where(ProactiveItem.status == "pending",
                                        ProactiveItem.expires_at.is_not(None),
                                        ProactiveItem.expires_at <= _utc(now).replace(tzinfo=None))
    if user_id is not None:
        query = query.where(ProactiveItem.user_id == user_id)
    result = db.execute(query.values(status="expired", resolved_at=_utc(now).replace(tzinfo=None),
                                     version=ProactiveItem.version + 1))
    return result.rowcount


def suppressed_kinds(db, user_id: str, now: datetime) -> set[str]:
    kinds = db.scalars(select(ProactiveItem.kind).where(
        ProactiveItem.user_id == user_id, ProactiveItem.status.in_(("accepted", "dismissed")),
    ).distinct()).all()
    result = set()
    for kind in kinds:
        latest = db.scalars(select(ProactiveItem).where(
            ProactiveItem.user_id == user_id, ProactiveItem.kind == kind,
            ProactiveItem.status.in_(("accepted", "dismissed")),
        ).order_by(ProactiveItem.resolved_at.desc(), ProactiveItem.id.desc()).limit(DISMISSAL_STREAK)).all()
        if (len(latest) == DISMISSAL_STREAK and all(row.status == "dismissed" for row in latest)
                and latest[0].resolved_at is not None
                and _utc(latest[0].resolved_at) <= _utc(now) < _utc(latest[0].resolved_at) + timedelta(days=SUPPRESSION_DAYS)):
            result.add(kind)
    return result


def tick_user(db, user_id: str, now: datetime, *, commit: bool = True) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")
    expired = expire_overdue(db, now, user_id)
    setting = db.get(ProactiveSetting, user_id)
    day = shanghai_day(now).isoformat()
    rows = db.scalars(select(ProactiveItem).where(ProactiveItem.user_id == user_id,
                                                  ProactiveItem.delivery_slot.like(f"{day}:%"))).all()
    used_slots = {row.delivery_slot for row in rows}
    existing_keys = {row.dedupe_key for row in rows}
    suppressed = suppressed_kinds(db, user_id, now)
    signals = [signal for signal in collect(db, user_id, now)
               if f"{signal.kind}:{signal.subject_key}:{day}" not in existing_keys]
    ctx = DecisionContext(now=now, enabled=setting.enabled if setting else True,
                          daily_limit=setting.daily_limit if setting else 1,
                          used_today=len(rows), quiet_start=setting.quiet_start if setting else "22:00",
                          quiet_end=setting.quiet_end if setting else "08:00",
                          snooze_until=setting.snooze_until if setting else None,
                          suppressed_kinds=frozenset(suppressed))
    selected = select_signals(signals, ctx)
    slots = [f"{day}:{number}" for number in range(ctx.daily_limit)
             if f"{day}:{number}" not in used_slots]
    created = 0
    for signal, slot in zip(selected, slots, strict=False):
        try:
            # The separate unique daily slot also bounds concurrent ticks that select different subjects.
            with db.begin_nested():
                db.add(ProactiveItem(user_id=user_id, kind=signal.kind, subject_key=signal.subject_key,
                    dedupe_key=f"{signal.kind}:{signal.subject_key}:{day}", delivery_slot=slot,
                    priority=signal.priority, title=signal.title, body=signal.body, why=signal.why,
                    payload=signal.payload, snapshot_version=signal.snapshot_version,
                    created_at=_utc(now).replace(tzinfo=None),
                    expires_at=signal.expires_at.replace(tzinfo=None) if signal.expires_at else None))
                db.flush()
            created += 1
        except IntegrityError:
            # A concurrent tick claimed this subject or daily slot; do not discard other inserts.
            continue
    if commit:
        db.commit()
    else:
        db.flush()
    return {"created": created, "expired": expired, "suppressed": len(suppressed)}


def settings_view(row):
    return {"enabled": row.enabled if row else True, "daily_limit": row.daily_limit if row else 1,
            "quiet_start": row.quiet_start if row else "22:00", "quiet_end": row.quiet_end if row else "08:00",
            "snooze_until": _utc(row.snooze_until).isoformat() if row and row.snooze_until else None,
            "version": row.version if row else 0}


def item_view(row):
    return {"id": row.id, "kind": row.kind, "priority": row.priority, "title": row.title,
            "body": row.body, "why": row.why, "payload": row.payload, "action": build_action(row.payload),
            "suppress_hint": "以后别推这类", "status": row.status, "version": row.version,
            "created_at": _utc(row.created_at).isoformat(),
            "expires_at": _utc(row.expires_at).isoformat() if row.expires_at else None}


def inbox(db, user_id, now):
    setting = settings_view(db.get(ProactiveSetting, user_id))
    day = shanghai_day(now).isoformat()
    used = db.scalars(select(ProactiveItem.id).where(ProactiveItem.user_id == user_id,
                        ProactiveItem.delivery_slot.like(f"{day}:%"))).all()
    rows = db.scalars(select(ProactiveItem).where(
        ProactiveItem.user_id == user_id,
        (((ProactiveItem.status == "pending") &
          (ProactiveItem.expires_at.is_(None) | (ProactiveItem.expires_at > _utc(now).replace(tzinfo=None)))) |
         ((ProactiveItem.status == "accepted") & ProactiveItem.action_completed_at.is_(None))),
    ).order_by(ProactiveItem.priority.desc(), ProactiveItem.created_at.desc(), ProactiveItem.id)).all()
    suppressed = suppressed_kinds(db, user_id, now)
    suppression_until = {}
    for kind in suppressed:
        last = db.scalar(select(ProactiveItem.resolved_at).where(
            ProactiveItem.user_id == user_id, ProactiveItem.kind == kind, ProactiveItem.status == "dismissed",
        ).order_by(ProactiveItem.resolved_at.desc()).limit(1))
        if last is not None:
            suppression_until[kind] = shanghai_day(_utc(last) + timedelta(days=SUPPRESSION_DAYS)).isoformat()
    return {"items": [item_view(row) for row in rows],
            "meta": {"as_of": day, "display_date": day, "enabled": setting["enabled"],
                     "daily_limit": setting["daily_limit"], "used_today": len(used),
                     "quiet_hours": {"start": setting["quiet_start"], "end": setting["quiet_end"]},
                     "suppressed_kinds": sorted(suppressed), "suppression_until": suppression_until,
                     "pending_total": sum(row.status == "pending" for row in rows)}}


def resolve_item(db, user_id, key, item_id, body, now, *, accept):
    def action(_op):
        row = db.scalar(select(ProactiveItem).where(ProactiveItem.id == item_id,
                                                   ProactiveItem.user_id == user_id).with_for_update())
        if row is None:
            raise AppError(404, "NOT_FOUND", "Proactive item not found")
        if row.status != "pending" or (row.expires_at and _utc(row.expires_at) <= _utc(now)):
            raise AppError(409, "PROACTIVE_CONFLICT", "Proactive item is no longer pending")
        if accept:
            if row.version != body.expected_version:
                raise AppError(409, "PROACTIVE_CONFLICT", "Proactive item version changed")
            model = InventoryBatch if row.kind == "expiring_batch" else ShoppingList
            subject_id = row.payload.get("batch_id" if row.kind == "expiring_batch" else "shopping_id")
            subject = db.scalar(select(model).where(model.id == subject_id, model.user_id == user_id).with_for_update())
            if subject is None or subject.version != row.snapshot_version:
                raise AppError(409, "PROACTIVE_STALE", "Proactive subject changed")
            if row.kind == "expiring_batch" and row.payload.get("recipe_id"):
                recipe = db.scalar(select(Recipe).where(Recipe.id == row.payload["recipe_id"], Recipe.user_id == user_id))
                if recipe is None:
                    raise AppError(409, "PROACTIVE_STALE", "Recipe no longer exists")
        row.status = "accepted" if accept else "dismissed"
        row.resolved_at = _utc(now).replace(tzinfo=None)
        row.version += 1
        result = {"item": item_view(row)}
        if accept:
            result["action"] = build_action(row.payload)
        return result
    return run_operation(db, user_id, key, "proactive_accept" if accept else "proactive_dismiss",
                         {"item_id": item_id, **body.model_dump(mode="json")}, action)


def finish_action(db, user_id, key, item_id, now, *, abandon=False):
    def action(_op):
        row = db.scalar(select(ProactiveItem).where(ProactiveItem.id == item_id,
                                                   ProactiveItem.user_id == user_id).with_for_update())
        if row is None:
            raise AppError(404, "NOT_FOUND", "Proactive item not found")
        if row.status != "accepted" or row.action_completed_at is not None:
            raise AppError(409, "PROACTIVE_CONFLICT", "Proactive action is not awaiting completion")
        if abandon:
            row.status = "abandoned"
            row.resolved_at = _utc(now).replace(tzinfo=None)
        else:
            row.action_completed_at = _utc(now).replace(tzinfo=None)
        row.version += 1
        return {"item": item_view(row)}
    return run_operation(db, user_id, key, "proactive_abandon" if abandon else "proactive_complete",
                         {"item_id": item_id}, action)


def patch_settings(db, user_id, key, body, now):
    def action(_op):
        row = db.get(ProactiveSetting, user_id)
        version = row.version if row else 0
        if body.expected_version != version:
            raise AppError(409, "PROACTIVE_SETTINGS_CONFLICT", "Proactive settings version changed")
        if row is None:
            row = ProactiveSetting(user_id=user_id)
            db.add(row)
        row.enabled = body.enabled
        row.daily_limit = body.daily_limit
        row.quiet_start, row.quiet_end = body.quiet_start, body.quiet_end
        row.snooze_until = _utc(body.snooze_until).replace(tzinfo=None) if body.snooze_until else None
        row.updated_at = _utc(now).replace(tzinfo=None)
        row.version = version + 1
        return settings_view(row)
    return run_operation(db, user_id, key, "proactive_settings", body.model_dump(mode="json"), action)


def tick_all(db, now, user_id=None, offsets=None):
    query = select(User.id).order_by(User.id)
    if user_id:
        query = query.where(User.id == str(user_id))
    ids = db.scalars(query).all()
    result = {"users": len(ids), "created": 0, "expired": 0, "suppressed": 0}
    for owner in ids:
        user_now = now + timedelta(days=(offsets or {}).get(owner, 0))
        counts = tick_user(db, owner, user_now)
        for key, value in counts.items():
            result[key] += value
    return result
