"""Smoothing of what this user actually took, from records that match this recipe exactly.

The weights below are v1 product rules chosen so a hand-checkable number comes out, not
parameters trained on data. Only a completed record with a recorded duration, the same
recipe version and the same servings speaks for how long this kitchen needs.
"""

from datetime import timedelta

from sqlalchemy import select

from ..models.food import CookingRecord, utcnow
from ..models.identity import UserPreference

WINDOW_DAYS = 180
MAX_SAMPLES = 20
# weight = n / (n + 3), held at 4/5 from twelve samples on, so the standard time keeps a say.
WEIGHT_OFFSET = 3
CAP_FROM = 12
CAP_WEIGHT = (4, 5)


def weight_fraction(count):
    if count >= CAP_FROM:
        return CAP_WEIGHT
    return count, count + WEIGHT_OFFSET


def median_numerator(samples):
    """Twice the median: the middle pair of an even count stays an exact integer."""
    ordered = sorted(samples)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return 2 * ordered[middle]
    return ordered[middle - 1] + ordered[middle]


def estimated_minutes(standard, samples):
    """ceil((1 - weight) * standard + weight * median) with the ceiling taken once, exactly."""
    numerator, denominator = weight_fraction(len(samples))
    top = 2 * (denominator - numerator) * standard + numerator * median_numerator(samples)
    return -(-top // (2 * denominator))


def duration_samples(db, user_id, servings):
    """{(recipe id, recipe version): minutes}, newest first and at most MAX_SAMPLES long."""
    rows = db.scalars(
        select(CookingRecord)
        .where(
            CookingRecord.user_id == user_id,
            CookingRecord.status == "completed",
            CookingRecord.actual_minutes.is_not(None),
            CookingRecord.created_at >= utcnow() - timedelta(days=WINDOW_DAYS),
        )
        .order_by(CookingRecord.created_at.desc(), CookingRecord.id.desc())
    ).all()
    grouped = {}
    for row in rows:
        snapshot = row.recipe_snapshot or {}
        version = snapshot.get("version")
        # A snapshot without a version predates versioned cooking: shown, never matched.
        if version is None or row.servings != servings:
            continue
        bucket = grouped.setdefault((str(snapshot.get("id")), version), [])
        if len(bucket) < MAX_SAMPLES:
            bucket.append(row.actual_minutes)
    return grouped


def estimate(recipe, servings, samples, *, personal_time_enabled=True):
    """The number the time filter uses, plus what it was built from."""
    fields = {
        "recipe_id": recipe["id"],
        "recipe_version": recipe["version"],
        "servings": servings,
        "standard_minutes": recipe["minutes"],
        "sample_count": len(samples),
        "sample_median": None,
        "weight": 0,
        "estimated_minutes": recipe["minutes"],
        "source": "standard",
    }
    median = median_numerator(samples) / 2 if samples else None
    if not personal_time_enabled:
        # The switch is why standard time applies, so it stays the source even with no history:
        # "nothing recorded yet" and "records deliberately unused" are different states to show.
        return {**fields, "sample_median": median, "source": "standard_disabled"}
    if not samples:
        return fields
    numerator, denominator = weight_fraction(len(samples))
    return {
        **fields,
        "sample_median": median,
        "weight": numerator / denominator,
        "estimated_minutes": estimated_minutes(recipe["minutes"], samples),
        "source": "personalized",
    }


def enabled(db, user_id):
    preference = db.get(UserPreference, user_id)
    return True if preference is None else bool(preference.personal_time_enabled)


def effective(db, user_id, recipe, servings):
    """One recipe read fresh, for paths that cannot reuse a recommendation's samples."""
    samples = duration_samples(db, user_id, servings)
    return estimate(recipe, servings,
                    samples.get((str(recipe["id"]), recipe["version"]), []),
                    personal_time_enabled=enabled(db, user_id))
