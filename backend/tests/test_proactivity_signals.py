from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from app.core.database import Base, build_engine, build_session_factory
from app.models.food import Ingredient, InventoryBatch, Recipe, RecipeIngredient
from app.models.identity import User
from app.models.shopping import ShoppingList
from app.services.proactivity import collect

NOW = datetime(2026, 10, 30, 4, tzinfo=timezone.utc)


@pytest.fixture
def signal_db():
    engine = build_engine("sqlite://")
    Base.metadata.create_all(engine)
    with build_session_factory(engine)() as db:
        db.add(User(id="u", username="proactive", password_hash="unused"))
        db.flush()
        db.add(Ingredient(id="i", user_id="u", name="菠菜", unit="g"))
        db.commit()
        yield db
    engine.dispose()


def add_batch(db, days=1, quantity="300", archived=False):
    db.add(InventoryBatch(id="b", user_id="u", ingredient_id="i", quantity=Decimal(quantity),
                          expires_on=(NOW + timedelta(days=days)).date(), archived=archived))
    db.commit()


def add_recipe(db):
    db.add(Recipe(id="r", user_id="u", name="菠菜炒蛋", servings=1, minutes=15,
                  equipment=[], steps=[], source=""))
    db.flush()
    db.add(RecipeIngredient(user_id="u", recipe_id="r", ingredient_id="i", quantity=Decimal("100")))
    db.commit()


def add_draft(db, hours, checked=()):
    db.add(ShoppingList(id="s", user_id="u", origin={"recipe_name": "菠菜炒蛋"},
                        items=[{"ingredient_id": "i"}], checked_ingredient_ids=list(checked),
                        created_at=(NOW - timedelta(hours=hours)).replace(tzinfo=None)))
    db.commit()


def test_expiring_batch_creates_signal_with_recipe(signal_db):
    add_batch(signal_db)
    add_recipe(signal_db)
    signal, = collect(signal_db, "u", NOW)
    assert signal.priority == 80 and signal.payload["recipe_id"] == "r"
    assert "菠菜炒蛋" in signal.body and "300g" in signal.title


def test_expiring_batch_without_recipe_still_signals(signal_db):
    add_batch(signal_db)
    signal, = collect(signal_db, "u", NOW)
    assert signal.payload["recipe_id"] is None and "食材" in signal.body


def test_batch_expiring_in_three_days_is_ignored(signal_db):
    add_batch(signal_db, days=3)
    assert collect(signal_db, "u", NOW) == []


@pytest.mark.parametrize(("quantity", "archived"), [("0", False), ("10", True)])
def test_archived_or_zero_quantity_batch_ignored(signal_db, quantity, archived):
    add_batch(signal_db, quantity=quantity, archived=archived)
    assert collect(signal_db, "u", NOW) == []


def test_shopping_draft_stale_after_48h(signal_db):
    add_draft(signal_db, 48)
    signal, = collect(signal_db, "u", NOW)
    assert signal.kind == "shopping_stale" and signal.payload["pending_count"] == 1


def test_shopping_draft_with_all_items_checked_ignored(signal_db):
    add_draft(signal_db, 49, checked=("i",))
    assert collect(signal_db, "u", NOW) == []


def test_shopping_draft_younger_than_48h_ignored(signal_db):
    add_draft(signal_db, 47)
    assert collect(signal_db, "u", NOW) == []
