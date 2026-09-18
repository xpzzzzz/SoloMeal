"""Synthetic P9 faults: isolated tmpfs and a fresh Compose project, no model calls."""

import argparse
import errno
import io
import json
import subprocess
import tarfile
import tempfile
from pathlib import Path
from uuid import uuid4

from manage import ROOT, Deployment, digest, initialize


def storage_fault(mode):
    import sys
    sys.path.insert(0, "/work/backend")
    from scripts.archive_uploads import export_files, import_files

    root = Path("/tmp/uploads")
    root.mkdir()
    name = str(uuid4())
    data = b"x" * (2 * 1024 * 1024)
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode="w") as target:
        member = tarfile.TarInfo(name)
        member.size = len(data)
        target.addfile(member, io.BytesIO(data))
    archive.seek(0)
    if mode == "buffer":
        tempfile.tempdir = "/full"
    if mode == "import":
        root = Path("/full")
    try:
        if mode == "export":
            (root / name).write_bytes(data)
            with Path("/full/uploads.tar").open("xb") as target:
                export_files(root, target)
        else:
            import_files(root, archive)
    except OSError as exc:
        assert exc.errno == errno.ENOSPC, exc
    else:
        raise AssertionError("Expected real ENOSPC")
    if mode == "buffer":
        assert list(root.iterdir()) == []
    elif mode == "import":
        assert 0 < (root / name).stat().st_size < len(data)
        try:
            import_files(root, io.BytesIO())
        except ValueError as exc:
            assert "empty" in str(exc)
        else:
            raise AssertionError("Partial restore was overwritten")
    else:
        assert (root / name).read_bytes() == data
    print(json.dumps({"case": mode, "errno": errno.ENOSPC, "passed": True}))


def host_drill(evidence):
    evidence.mkdir(parents=True, exist_ok=False)
    results = []
    for mode in ("export", "buffer", "import"):
        command = ["docker", "run", "--rm", "--network", "none",
                   "--memory", "256m", "--cpus", "1", "--read-only",
                   "--tmpfs", "/tmp:rw,size=16m,mode=1777",
                   "--tmpfs", "/full:rw,size=1m,mode=1777",
                   "--mount", f"type=bind,source={ROOT},target=/work,readonly",
                   "solomeal-api:local", "python", "/work/deploy/fault_drill.py",
                   "--storage", mode]
        process = subprocess.run(command, capture_output=True, text=True, timeout=60)
        (evidence / f"{mode}.log").write_text(process.stdout + process.stderr, encoding="utf-8")
        if process.returncode:
            raise RuntimeError(f"Storage drill {mode} failed; inspect its log")
        results.append(json.loads(process.stdout))

    private = Path(tempfile.mkdtemp(prefix="solomeal-p9-fault-"))
    env_file = private / "isolated.env"
    initialize(env_file, 18089)
    project = "solomeal-fault-" + uuid4().hex[:12]
    deployment = Deployment(project, env_file)
    backup = evidence / "synthetic-backup"
    backup.mkdir()
    (backup / "database.sql").write_text(
        "CREATE TABLE fault_marker (id INT PRIMARY KEY);\n"
        "INSERT INTO fault_marker VALUES (1);\n"
        "THIS IS DELIBERATELY INVALID SQL;\n", encoding="utf-8")
    with tarfile.open(backup / "uploads.tar", "w"):
        pass
    (backup / "manifest.json").write_text(json.dumps({
        "format": "solomeal-backup-v1", "schema_revision": "synthetic-fault",
        "files": {name: digest(backup / name) for name in ("database.sql", "uploads.tar")},
    }), encoding="utf-8")
    (evidence / "target.json").write_text(json.dumps({
        "project": project, "private_env": str(env_file), "synthetic_only": True,
    }, indent=2), encoding="utf-8")
    try:
        try:
            deployment.restore(backup)
        except RuntimeError as exc:
            assert "exec failed" in str(exc), exc
        else:
            raise AssertionError("Invalid SQL unexpectedly restored")
        assert deployment.sql("SELECT COUNT(*) FROM fault_marker") == "1"
        running = deployment.run("ps", "--services", "--status", "running").decode().split()
        assert running == ["db"], running
        try:
            deployment.restore(backup)
        except ValueError as exc:
            assert "non-empty" in str(exc), exc
        else:
            raise AssertionError("Partial database was overwritten")
        assert deployment.sql("SELECT COUNT(*) FROM fault_marker") == "1"
        results.append({"case": "mysql_partial_import", "passed": True,
                        "marker_rows": 1, "running_services": running,
                        "retry_refused": True})
    finally:
        deployment.run("stop")
    (evidence / "results.json").write_text(json.dumps({
        "cases": results, "project": project, "stopped": True, "volumes_retained": True,
        "model_requests": 0,
    }, indent=2), encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--storage", choices=("export", "buffer", "import"))
    parser.add_argument("--evidence", type=Path)
    args = parser.parse_args()
    if args.storage:
        storage_fault(args.storage)
    elif args.evidence:
        host_drill(args.evidence)
    else:
        parser.error("Choose --storage or --evidence")
