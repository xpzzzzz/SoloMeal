import os
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from threading import Barrier, Lock

import pytest
from app.models.food import Ingredient, InventoryBatch
from app.models.identity import User
from app.models.proactivity import ProactiveItem, ProactiveSetting
from app.models.shopping import ShoppingList
from app.services import proactivity_store
from app.services.proactivity import in_quiet_hours
from app.services.proactivity_store import inbox, tick_user
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from test_proactivity_signals import signal_db  # noqa: F401

NOW = datetime(2026, 10, 30, 4, tzinfo=timezone.utc)


@pytest.mark.parametrize(("hour", "minute", "quiet"), [(13, 59, False), (14, 0, True),
                                                       (16, 0, True), (23, 59, True), (0, 0, False)])
def test_quiet_window_midnight_boundaries(hour, minute, quiet):
    # UTC 14:00 is 22:00 Shanghai; UTC midnight is 08:00 Shanghai.
    instant = NOW.replace(hour=hour, minute=minute)
    assert in_quiet_hours(instant, "22:00", "08:00") is quiet


@pytest.fixture
def tick_db(request):
    if os.environ.get("SOLOMEAL_TEST_DATABASE_URL"):
        client = request.getfixturevalue("client")
        with client.app.state.sessions() as db:
            yield db
    else:
        # The SQLite fixture already contains the user and ingredient.
        db = request.getfixturevalue("signal_db")
        yield db


def setup(db, *, limit=1, shopping=False):
    if not db.get(User, "u"):
        db.add(User(id="u", username="tick-user", password_hash="unused"))
        db.flush()
        db.add(Ingredient(id="i", user_id="u", name="菠菜", unit="g"))
        db.flush()
    db.add_all([
        InventoryBatch(id="b", user_id="u", ingredient_id="i", quantity=Decimal("300"),
                       expires_on=NOW.date() + timedelta(days=1)),
        ProactiveSetting(user_id="u", daily_limit=limit, updated_at=NOW.replace(tzinfo=None)),
    ])
    if shopping:
        db.add(ShoppingList(id="s", user_id="u", origin={}, items=[{"ingredient_id": "i"}],
                            checked_ingredient_ids=[], created_at=(NOW - timedelta(days=3)).replace(tzinfo=None)))
    db.commit()


def history(db, statuses, kind="expiring_batch"):
    for i, status in enumerate(statuses):
        stamp = (NOW - timedelta(days=len(statuses) - i)).replace(tzinfo=None)
        db.add(ProactiveItem(id=f"history-{i}", user_id="u", kind=kind, subject_key=f"old:{i}",
                             dedupe_key=f"old:{i}", delivery_slot=f"old:{i}", priority=80,
                             title="old", body="old", why="old", payload={}, snapshot_version=1,
                             status=status, created_at=stamp, resolved_at=stamp))
    db.commit()


def test_daily_limit_one_creates_single_item(tick_db):
    with nullcontext(tick_db) as db:
        setup(db, shopping=True)
        assert tick_user(db, "u", NOW)["created"] == 1
        assert db.scalars(select(ProactiveItem)).one().kind == "expiring_batch"


def test_second_tick_same_day_creates_nothing(tick_db):
    with nullcontext(tick_db) as db:
        setup(db)
        assert tick_user(db, "u", NOW)["created"] == 1
        assert tick_user(db, "u", NOW)["created"] == 0


def test_tick_inside_quiet_hours_creates_nothing(tick_db):
    with nullcontext(tick_db) as db:
        setup(db)
        assert tick_user(db, "u", NOW.replace(hour=15))["created"] == 0  # 23:00 Shanghai


def test_three_consecutive_dismissals_suppress_kind_for_7_days(tick_db):
    with nullcontext(tick_db) as db:
        setup(db)
        history(db, ["dismissed"] * 3)
        assert tick_user(db, "u", NOW)["created"] == 0
        assert inbox(db, "u", NOW)["meta"]["suppression_until"] == {"expiring_batch": "2026-11-05"}
        from app.services.proactivity_store import suppressed_kinds
        assert suppressed_kinds(db, "u", NOW + timedelta(days=6)) == set()


def test_mixed_kinds_respect_suppression(tick_db):
    with nullcontext(tick_db) as db:
        setup(db, shopping=True)
        history(db, ["dismissed"] * 3)
        assert tick_user(db, "u", NOW)["created"] == 1
        assert db.scalars(select(ProactiveItem).where(ProactiveItem.status == "pending")).one().kind == "shopping_stale"


def test_dismiss_breaks_suppression_streak(tick_db):
    with nullcontext(tick_db) as db:
        setup(db)
        history(db, ["dismissed", "accepted", "dismissed"])
        assert tick_user(db, "u", NOW)["created"] == 1


def test_overdue_items_marked_expired_on_tick(tick_db):
    with nullcontext(tick_db) as db:
        setup(db)
        history(db, ["dismissed"])
        row = db.get(ProactiveItem, "history-0")
        row.status = "pending"
        row.expires_at = (NOW - timedelta(seconds=1)).replace(tzinfo=None)
        db.commit()
        assert tick_user(db, "u", NOW)["expired"] == 1
        db.refresh(row)
        assert row.status == "expired" and row.resolved_at == NOW.replace(tzinfo=None)


def test_daily_slot_rejects_a_different_subject(tick_db):
    setup(tick_db)
    assert tick_user(tick_db, "u", NOW)["created"] == 1
    original = tick_db.scalars(select(ProactiveItem)).one()
    duplicate_slot = ProactiveItem(user_id="u", kind="shopping_stale", subject_key="shopping:other",
                                   dedupe_key="different-subject", delivery_slot=original.delivery_slot,
                                   priority=50, title="x", body="x", why="x", payload={},
                                   snapshot_version=1, created_at=NOW.replace(tzinfo=None))
    with pytest.raises(IntegrityError):
        with tick_db.begin_nested():
            tick_db.add(duplicate_slot)
            tick_db.flush()


@pytest.mark.parametrize("different_subjects", [False, True])
def test_mysql_concurrent_ticks_respect_daily_limit(tick_db, monkeypatch, different_subjects):
    if tick_db.bind.dialect.name != "mysql":
        pytest.skip("requires real MySQL concurrency")
    setup(tick_db)
    tick_db.add(InventoryBatch(id="b2", user_id="u", ingredient_id="i", quantity=Decimal("300"),
                               expires_on=NOW.date() + timedelta(days=1)))
    tick_db.commit()
    barrier = Barrier(2, timeout=20)
    guard = Lock()
    calls = []
    real_collect = proactivity_store.collect

    def collect_together(db, user_id, now):
        signals = real_collect(db, user_id, now)
        with guard:
            index = len(calls)
            calls.append(index)
        barrier.wait()
        return [signals[index if different_subjects else 0]]

    monkeypatch.setattr(proactivity_store, "collect", collect_together)
    sessions = sessionmaker(bind=tick_db.bind, expire_on_commit=False)

    def invoke():
        with sessions() as db:
            return tick_user(db, "u", NOW)["created"]

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(invoke) for _ in range(2)]
        assert sorted(future.result(timeout=30) for future in futures) == [0, 1]
    tick_db.expire_all()
    assert len(tick_db.scalars(select(ProactiveItem)).all()) == 1
