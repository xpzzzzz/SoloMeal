"""Run a new, bounded MySQL acceptance batch; preserve the interrupted batch."""

import argparse
import hashlib
import json
import os
import runpy
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
prior = runpy.run_path(str(Path(__file__).with_name("mysql-acceptance-0914.py")))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, choices=("diagnostic", "engineering", "regression"))
    parser.add_argument("selectors", nargs="*")
    args = parser.parse_args()
    url = prior["make_url"](prior["Settings"]().database_url)
    if (url.get_backend_name(), url.host, url.port, url.database) != (
        "mysql", "127.0.0.1", 13316, "solomeal"
    ):
        raise SystemExit("Unexpected database endpoint")
    output = ROOT / f"docs/validation/mysql-{args.batch}-0915"
    output.mkdir(exist_ok=False)
    before = prior["snapshot"](url)
    previous = json.loads((ROOT / "docs/validation/mysql-acceptance-0914/report.json").read_text())
    selectors = args.selectors
    if args.batch == "engineering":
        data = json.loads((ROOT / "evaluation/scenarios-v1.json").read_text(encoding="utf-8"))
        selectors = [c["selector"] for c in data["scenarios"] if c["track"] == "engineering"]
        # Include all current MySQL-exclusive cases, beyond the frozen catalog.
        selectors += ["tests/test_agent_sessions.py::test_mysql_concurrent_session_continuation",
                      "tests/test_receipt_vision.py::test_mysql_pending_parse_admission_across_requests",
                      "tests/test_receipts.py::test_mysql_edit_during_parser_does_not_hold_owner_lock_or_overwrite",
                      "tests/test_crud.py::test_mysql_archive_cooking_race"]
        selectors = list(dict.fromkeys(selectors))
    if not selectors:
        raise SystemExit("Explicit selectors required")
    hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for folder in ("backend/app", "backend/tests", "backend/scripts", "evaluation")
              for p in sorted((ROOT / folder).rglob("*"))
              if p.suffix in (".py", ".json") and "__pycache__" not in p.parts}
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "selectors": selectors,
              "source_hashes": hashes, "development_before": before,
              "matches_0914_development_snapshot": before == previous["development_before"],
              "test_before": prior["snapshot"](url.set(database="solomeal_test")),
              "real_model_calls": 0}
    target = output / "report.json"
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    env = dict(os.environ)
    env.update(SOLOMEAL_AGENT_ENABLED="false", SOLOMEAL_RECEIPT_VISION_ENABLED="false",
               SOLOMEAL_MODEL_API_KEY="", SOLOMEAL_MODEL_NAME="", PYTHONDONTWRITEBYTECODE="1",
               PYTHONIOENCODING="utf-8")
    with (output / "pytest.log").open("w", encoding="utf-8") as log:
        result = subprocess.run([sys.executable, "scripts/test_mysql.py", "-vv", "-x",
                                 "--show-capture=no", "--junitxml", str(output / "junit.xml"),
                                 *selectors], cwd=BACKEND, env=env, stdout=log,
                                stderr=subprocess.STDOUT, check=False)
    after = prior["snapshot"](url)
    report.update(exit_code=result.returncode, development_after=after,
                  development_unchanged=before == after,
                  test_after=prior["snapshot"](url.set(database="solomeal_test")),
                  finished_at=datetime.now(timezone.utc).isoformat())
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"exit_code": result.returncode, "development_unchanged": before == after}))
    return result.returncode or (0 if before == after else 1)


if __name__ == "__main__":
    raise SystemExit(main())
