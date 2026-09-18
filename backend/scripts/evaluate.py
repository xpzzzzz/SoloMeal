"""Offline P8 engineering evaluation; never invokes a real model or loads .env."""

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "evaluation" / "scenarios-v1.json"
PROTOCOL = ROOT / "evaluation" / "protocol-v1.json"


def load_dataset(path=DATASET):
    raw = path.read_bytes()
    data = json.loads(raw)
    cases = data["scenarios"]
    if len(cases) != 100 or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Dataset must contain 100 unique scenarios")
    selectors = []
    for case in cases:
        if case["track"] == "engineering":
            selector = case["selector"]
            file, function = selector.split("::")
            if not file.startswith("tests/test_") or not file.endswith(".py"):
                raise ValueError("Invalid test path")
            if "/" in file[6:] or "\\" in file or not function.startswith("test_"):
                raise ValueError("Invalid selector")
            selectors.append(selector)
        elif case["track"] == "agent":
            if case["split"] not in ("debug", "holdout") or not case["oracle"]:
                raise ValueError("Agent scenario needs a split and oracle")
        else:
            raise ValueError("Unknown track")
    if len(selectors) != len(set(selectors)):
        raise ValueError("Do not count the same engineering test twice")
    return data, hashlib.sha256(raw).hexdigest()


def summarize(data, xml_path):
    tests = ET.parse(xml_path).getroot().findall(".//testcase")
    rows = []
    for case in data["scenarios"]:
        row = {"id": case["id"], "track": case["track"], "split": case["split"]}
        if case["track"] != "engineering":
            row.update(status="not_run", reason="Real model comparison runner pending")
        else:
            file, function = case["selector"].split("::")
            classname = file[:-3].replace("/", ".")
            matches = [t for t in tests if t.get("classname") == classname
                       and t.get("name", "").split("[")[0] == function]
            results = ["failed" if t.find("failure") is not None or t.find("error") is not None
                       else "skipped" if t.find("skipped") is not None else "passed"
                       for t in matches]
            status = ("not_run" if not results else "failed" if "failed" in results
                      else "skipped" if "skipped" in results else "passed")
            row.update(status=status, instances=len(matches),
                       instance_results=results,
                       elapsed_seconds=sum(float(t.get("time", "0")) for t in matches))
        rows.append(row)
    engineering = [r for r in rows if r["track"] == "engineering"]
    counts = {s: sum(r["status"] == s for r in engineering)
              for s in ("passed", "failed", "skipped", "not_run")}
    return {"scenarios": rows, "engineering_counts": counts,
            "engineering_gate": "passed" if counts["passed"] == len(engineering) else "incomplete",
            "p8_gate": "incomplete", "real_model_calls": 0,
            "agent_metrics": None, "cost": None}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="New evidence directory; existing paths are rejected")
    args = parser.parse_args(argv)
    data, digest = load_dataset()
    # SQLite only. MySQL remains the separately guarded, serial test_mysql.py workflow.
    if os.environ.get("SOLOMEAL_TEST_DATABASE_URL"):
        parser.error("Unset SOLOMEAL_TEST_DATABASE_URL; this runner uses isolated SQLite")
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    env = dict(os.environ)
    env.update(SOLOMEAL_AGENT_ENABLED="false", SOLOMEAL_RECEIPT_VISION_ENABLED="false",
               SOLOMEAL_MODEL_API_KEY="", SOLOMEAL_MODEL_NAME="", PYTHONDONTWRITEBYTECODE="1")
    revision = subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", "rev-parse", "HEAD"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.strip()
    # Include untracked application sources in the identity of this dirty checkout.
    source_files = sorted(p for directory in ("backend/app", "backend/tests", "backend/scripts")
                          for p in (ROOT / directory).rglob("*.py") if "__pycache__" not in p.parts)
    source_hash = hashlib.sha256()
    for path in source_files:
        source_hash.update(path.relative_to(ROOT).as_posix().encode())
        source_hash.update(b"\0" + path.read_bytes() + b"\0")
    metadata = {"dataset_version": data["version"], "dataset_sha256": digest,
                "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
                "source_sha256": source_hash.hexdigest(), "commit": revision,
                "httpx_version": version("httpx"), "pytest_version": version("pytest"),
                "python": platform.python_version(), "database": "isolated SQLite",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "mode": "engineering_regression", "model": None,
                "prompt_version": None, "sampling": None, "repetitions": 1}
    (output / "attempt.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="solomeal-p8-") as temp:
        command = [sys.executable, "-m", "pytest", "-o", "addopts=", "-p", "no:cacheprovider",
                   "--basetemp", str(Path(temp) / "pytest"),
                   "--junitxml", str(output / "junit.xml"), "-q"]
        command += [c["selector"] for c in data["scenarios"] if c["track"] == "engineering"]
        with (output / "pytest.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(command, cwd=ROOT / "backend", env=env,
                                    stdout=log, stderr=subprocess.STDOUT, check=False)
    if (output / "junit.xml").exists():
        report = summarize(data, output / "junit.xml")
    else:
        report = {"engineering_gate": "incomplete", "p8_gate": "incomplete",
                  "reason": "pytest did not produce XML", "real_model_calls": 0}
    if result.returncode:
        report["engineering_gate"] = "incomplete"
    report.update(metadata, pytest_exit_code=result.returncode)
    (output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "engineering_gate": report["engineering_gate"],
                      "p8_gate": report["p8_gate"]}, ensure_ascii=False))
    return 1 if result.returncode else 0


if __name__ == "__main__":
    raise SystemExit(main())
