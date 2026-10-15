"""Explain captured SELECTs and profile service computation in the sandbox."""
import argparse
import cProfile
import json
import pstats
import re
from pathlib import Path

from sqlalchemy import text

from app.core.config import Settings
from app.core.database import build_engine, build_session_factory
from app.schemas.planning import PlanningInput
from app.services.planning import recommend
from sandbox import require_models_off, require_sandbox


def collect(directory):
    settings = Settings(_env_file=None)
    require_sandbox(settings.database_url)
    require_models_off(settings)
    engine = build_engine(settings.database_url)
    queries = {}
    for line in (directory / "diagnostics.jsonl").read_text().splitlines():
        row = json.loads(line)
        match = re.search(r"-r(10|100|500)-", row["tag"])
        if not match or not row["tag"].startswith("serial-"):
            continue
        scale = int(match.group(1))
        for key, value in row["queries"].items():
            if value["parameters"] is not None and value["sql"].upper().startswith("SELECT"):
                queries.setdefault((scale, key), value)
    plans = []
    with engine.connect() as db:
        for (scale, key), value in queries.items():
            statement, params = value["sql"], value["parameters"]
            if isinstance(params, list):
                params = tuple(params)
            plan = db.exec_driver_sql("EXPLAIN FORMAT=JSON " + statement, params).scalar_one()
            analyzed = db.exec_driver_sql("EXPLAIN ANALYZE " + statement, params).scalars().all()
            plans.append({"scale": scale, "fingerprint": key, "sql": statement, "parameters": params,
                          "explain": json.loads(plan), "analyze": analyzed})
        metadata = dict(db.execute(text("SELECT VERSION() AS version, @@session.transaction_isolation AS isolation_level, @@max_connections AS max_connections, @@innodb_buffer_pool_size AS innodb_buffer_pool_bytes")).mappings().one())
    fixture = json.loads((directory / "fixture.json").read_text())
    factory = build_session_factory(engine)
    profiles = []
    for scale in (10, 100, 500):
        uid = next(r["user_id"] for r in fixture["users"] if r["scale"] == scale)
        with factory() as db:
            profiler = cProfile.Profile()
            profiler.enable()
            result = recommend(db, uid, PlanningInput(scenario="default"))
            profiler.disable()
            stats = pstats.Stats(profiler)
            functions = [{"file": f, "line": line, "function": name, "primitive_calls": cc,
                          "calls": nc, "self_seconds": tt, "cumulative_seconds": ct}
                         for (f, line, name), (cc, nc, tt, ct, _) in stats.stats.items()]
            profiles.append({"scale": scale, "candidates": len(result["candidates"]),
                             "profile_seconds": stats.total_tt,
                             "functions": sorted(functions, key=lambda r: -r["cumulative_seconds"])[:100]})
    engine.dispose()
    with (directory / "sql-plans-and-profiles.json").open("x", encoding="utf-8") as out:
        json.dump({"mysql": metadata, "plans": plans, "profiles": profiles}, out, indent=2, default=str)
    print(json.dumps({"explained_select_patterns": len(plans), "profile_scales": [10, 100, 500]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory", type=Path, default=Path("/perf-output"))
    collect(parser.parse_args().directory)
