"""Persistence and state transitions for proactive suggestions."""

from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from ..models.proactivity import ProactiveItem, ProactiveSetting
from .home import shanghai_day
from .proactivity import DecisionContext, _utc, collect, select_signals

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


