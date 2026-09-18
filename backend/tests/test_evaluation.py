import hashlib
import json

import pytest
from scripts.evaluate import DATASET, load_dataset, main, summarize


def test_frozen_catalog_has_separate_regression_and_unrun_holdout():
    data, digest = load_dataset()
    assert len(digest) == 64
    assert len([c for c in data["scenarios"] if c["split"] == "regression"]) == 60
    assert len([c for c in data["scenarios"] if c["split"] == "debug"]) == 20
    assert len([c for c in data["scenarios"] if c["split"] == "holdout"]) == 20
    assert all(c["status"] == "not_run" for c in data["scenarios"] if c["track"] == "agent")


def test_preregistered_files_match_freeze():
    directory = DATASET.parent
    frozen = json.loads((directory / "freeze-v1.json").read_text(encoding="utf-8"))
    for name, digest in frozen["files"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest


def test_report_never_counts_skips_missing_or_partial_parameterizations_as_pass(tmp_path):
    data = {"scenarios": [
        {"id": str(i), "track": "engineering", "split": "regression",
         "selector": f"tests/test_sample.py::test_{name}"}
        for i, name in enumerate(("ok", "partial", "failed", "missing"))
    ] + [{"id": "agent", "track": "agent", "split": "holdout"}]}
    xml = tmp_path / "junit.xml"
    xml.write_text('''<testsuites><testsuite>
    <testcase classname="tests.test_sample" name="test_ok" time="0.1"/>
    <testcase classname="tests.test_sample" name="test_partial[one]"/>
    <testcase classname="tests.test_sample" name="test_partial[two]"><skipped/></testcase>
    <testcase classname="tests.test_sample" name="test_failed"><failure/></testcase>
    </testsuite></testsuites>''', encoding="utf-8")
    result = summarize(data, xml)
    assert result["engineering_counts"] == {"passed": 1, "failed": 1, "skipped": 1, "not_run": 1}
    assert result["engineering_gate"] == result["p8_gate"] == "incomplete"
    assert result["agent_metrics"] is None and result["cost"] is None
    assert result["scenarios"][-1]["status"] == "not_run"


def test_duplicate_selector_is_rejected(tmp_path):
    data, _ = load_dataset()
    data["scenarios"][1]["selector"] = data["scenarios"][0]["selector"]
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="twice"):
        load_dataset(path)


def test_runner_refuses_database_override_before_creating_output(tmp_path, monkeypatch):
    monkeypatch.setenv("SOLOMEAL_TEST_DATABASE_URL", "mysql://unused/solomeal_test")
    target = tmp_path / "evidence"
    with pytest.raises(SystemExit):
        main(["--output", str(target)])
    assert not target.exists()


def test_runner_refuses_to_overwrite_evidence(tmp_path, monkeypatch):
    monkeypatch.delenv("SOLOMEAL_TEST_DATABASE_URL", raising=False)
    with pytest.raises(FileExistsError):
        main(["--output", str(tmp_path)])
