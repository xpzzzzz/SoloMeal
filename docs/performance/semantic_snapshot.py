"""Fixed-clock full response comparison on the unchanged synthetic MySQL fixture."""
import argparse
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.models.food import Recipe
from app.schemas.planning import PlanningInput
from app.services import food, home, personal_time, personalization, planning
from sandbox import require_models_off, require_sandbox


def capture(destination):
    settings = Settings(_env_file=None)
    require_models_off(settings)
    require_sandbox(settings.database_url)
    manifest = json.loads(Path('/perf-output/fixture.json').read_text())
    fixed = datetime.fromisoformat(manifest['as_of'] + 'T12:00:00')

    class FixedDate(date):
        @classmethod
        def today(cls):
            return fixed.date()

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed.replace(tzinfo=timezone.utc).astimezone(tz) if tz else fixed

    planning.date = food.date = FixedDate
    home.datetime = FixedDatetime
    personalization.utcnow = personal_time.utcnow = lambda: fixed
    factory = build_session_factory(build_engine(settings.database_url))
    results = {}
    for scale in (10, 100, 500):
        uid = next(u['user_id'] for u in manifest['users'] if u['scale'] == scale)
        bodies = [{'scenario': s} for s in ('default', 'quick', 'clear_fridge', 'less_shopping', 'variety')]
        bodies += [{'scenario': 'custom', 'include_optional': True, 'servings': 2, 'budget': '30'},
                   {'scenario': 'custom', 'equipment': [], 'max_minutes': 1}]
        for index, body in enumerate(bodies):
            with factory() as db:
                results[f'r{scale}-planning-{index}'] = planning.recommend(db, uid, PlanningInput(**body))
        with factory() as db:
            results[f'r{scale}-home'] = home.build(db, uid)
            ids = db.scalars(select(Recipe.id).where(Recipe.user_id == uid)
                             .order_by(Recipe.name, Recipe.id).limit(100).offset(5)).all()
            results[f'r{scale}-recipes'] = [food.recipe_view(db, uid, rid) for rid in ids]
    encoded = jsonable_encoder(results)
    digest = hashlib.sha256(json.dumps(encoded, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    with destination.open('x', encoding='utf-8') as output:
        json.dump({'fixed_now': fixed.isoformat(), 'sha256': digest, 'responses': encoded}, output, ensure_ascii=False)
    print(json.dumps({'cases': len(results), 'sha256': digest}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('destination', type=Path)
    capture(parser.parse_args().destination)
