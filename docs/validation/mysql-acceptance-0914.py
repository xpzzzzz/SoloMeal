"""Local MySQL acceptance with a fixed endpoint and read-only dev snapshots."""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

from app.core.config import Settings  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402


def snapshot(url):
    engine = create_engine(url, connect_args={"connect_timeout": 5})
    try:
        with engine.connect() as connection:
            meta = dict(connection.execute(text(
                "SELECT VERSION() AS version, DATABASE() AS database_name"
            )).mappings().one())
            tables = {}
            for name in sorted(inspect(connection).get_table_names()):
                quoted = engine.dialect.identifier_preparer.quote(name)
                rows = connection.execute(text(f"SELECT * FROM {quoted}")).fetchall()
                hashes = sorted(hashlib.sha256(json.dumps(
                    list(row), default=str, ensure_ascii=False
                ).encode()).hexdigest() for row in rows)
                tables[name] = {"rows": len(rows), "sha256": hashlib.sha256(
                    "\n".join(hashes).encode()).hexdigest()}
            return {**meta, "tables": tables}
    finally:
        engine.dispose()


def main():
    url = make_url(Settings().database_url)
    if (url.get_backend_name(), url.host, url.port, url.database) != (
        "mysql", "127.0.0.1", 13316, "solomeal"
    ):
        raise SystemExit("Unexpected endpoint; acceptance stopped")
    output = ROOT / "docs/validation/mysql-acceptance-0914"
    output.mkdir(exist_ok=False)
    before = snapshot(url)
    test_before = snapshot(url.set(database="solomeal_test"))
    report = {"started_at": datetime.now(timezone.utc).isoformat(),
              "endpoint": "127.0.0.1:13316", "development_before": before,
              "test_before": test_before, "real_model_calls": 0}
    report_path = output / "report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    env = dict(os.environ)
    env.update(SOLOMEAL_AGENT_ENABLED="false", SOLOMEAL_RECEIPT_VISION_ENABLED="false",
               SOLOMEAL_MODEL_API_KEY="", SOLOMEAL_MODEL_NAME="",
               PYTHONDONTWRITEBYTECODE="1")
    with (output / "pytest.log").open("w", encoding="utf-8") as log:
        result = subprocess.run(
            [sys.executable, "scripts/test_mysql.py", "--junitxml", str(output / "junit.xml")],
            cwd=BACKEND, env=env, stdout=log, stderr=subprocess.STDOUT, check=False,
        )
    after = snapshot(url)
    report.update(pytest_exit_code=result.returncode, development_after=after,
                  development_unchanged=before == after,
                  test_after=snapshot(url.set(database="solomeal_test")),
                  finished_at=datetime.now(timezone.utc).isoformat())
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"exit_code": result.returncode,
                      "development_unchanged": before == after}))
    return result.returncode or (0 if before == after else 1)


if __name__ == "__main__":
    raise SystemExit(main())
