import importlib.util
import io
import json
import tarfile
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.archive_uploads import export_files, import_files

spec = importlib.util.spec_from_file_location("deployment_manage", Path(__file__).resolve().parents[2] / "deploy/manage.py")
manage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manage)


def archive_entry(name, kind=tarfile.REGTYPE, content=b"image"):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        member = tarfile.TarInfo(name)
        member.type = kind
        member.size = len(content) if kind == tarfile.REGTYPE else 0
        member.linkname = "../../outside"
        archive.addfile(member, io.BytesIO(content) if member.size else None)
    buffer.seek(0)
    return buffer


def test_upload_round_trip_bytes_and_refuse_overwrite(tmp_path):
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    name = str(uuid4())
    (source / name).write_bytes(b"\x89PNG\x00binary\xff")
    buffer = io.BytesIO()
    export_files(source, buffer)
    buffer.seek(0)
    import_files(target, buffer)
    assert (target / name).read_bytes() == (source / name).read_bytes()
    with pytest.raises(ValueError, match="empty"):
        import_files(target, io.BytesIO())


@pytest.mark.parametrize("name,kind", [
    ("../../outside", tarfile.REGTYPE), ("/absolute", tarfile.REGTYPE),
    (str(uuid4()), tarfile.SYMTYPE), (str(uuid4()), tarfile.LNKTYPE),
    (str(uuid4()), tarfile.DIRTYPE), ("bad-name", tarfile.REGTYPE),
])
def test_archive_rejects_paths_links_and_nonfiles_before_writing(tmp_path, name, kind):
    with pytest.raises(ValueError):
        import_files(tmp_path, archive_entry(name, kind))
    assert list(tmp_path.iterdir()) == []


def test_duplicate_names_rejected_before_any_restore(tmp_path):
    buffer = io.BytesIO()
    name = str(uuid4())
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for _ in range(2):
            member = tarfile.TarInfo(name)
            member.size = 1
            archive.addfile(member, io.BytesIO(b"x"))
    buffer.seek(0)
    with pytest.raises(ValueError):
        import_files(tmp_path, buffer)
    assert list(tmp_path.iterdir()) == []


def test_env_creation_is_exclusive_and_project_boundary(tmp_path):
    path = tmp_path / "deploy.env"
    manage.initialize(path, 18080)
    original = path.read_bytes()
    with pytest.raises(FileExistsError):
        manage.initialize(path, 18080)
    assert path.read_bytes() == original
    for project in ("mindbridge", "solomeal-dev", "solomeal-test", "solomeal-x;echo"):
        with pytest.raises(ValueError):
            manage.Deployment(project, path)


class FakeDeployment(manage.Deployment):
    def __init__(self, tables="0", running=b"db\n"):
        self.calls, self.tables, self.running = [], tables, running
        self.project = "solomeal-testfixture"

    def run(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == "ps":
            return self.running
        if args[0] == "exec":
            raise RuntimeError("synthetic dump failure")
        return b""

    def sql(self, query):
        return self.tables


def backup_files(folder):
    for name in ("database.sql", "uploads.tar"):
        (folder / name).write_bytes(b"fixture")
    (folder / "manifest.json").write_text(json.dumps({"format": "solomeal-backup-v1",
        "schema_revision": "fixture-revision",
        "files": {name: manage.digest(folder / name) for name in ("database.sql", "uploads.tar")}}))


def test_restore_checksum_failure_precedes_any_docker_operation(tmp_path):
    backup_files(tmp_path)
    (tmp_path / "database.sql").write_bytes(b"corrupt")
    deployment = FakeDeployment()
    with pytest.raises(ValueError, match="checksum"):
        deployment.restore(tmp_path)
    assert deployment.calls == []


def test_restore_refuses_nonempty_database_or_live_app(tmp_path):
    backup_files(tmp_path)
    for deployment in (FakeDeployment(tables="22"), FakeDeployment(running=b"api\ndb\n")):
        with pytest.raises(ValueError):
            deployment.restore(tmp_path)
        assert not any(c[0] in ("exec", "run") for c in deployment.calls)


def test_backup_failure_resumes_only_previously_running_writers(tmp_path):
    deployment = FakeDeployment(running=b"api\ndb\n")
    with pytest.raises(RuntimeError, match="synthetic"):
        deployment.backup(tmp_path / "backup")
    assert ("stop", "api") in deployment.calls and deployment.calls[-1] == ("start", "api")
    assert not (tmp_path / "backup/manifest.json").exists()


class SuccessfulDeployment(FakeDeployment):
    def run(self, *args, **kwargs):
        self.calls.append(args)
        if args[0] == "ps":
            return self.running
        if kwargs.get("stdout") is not None:
            kwargs["stdout"].write(b"synthetic backup")
        return b""


@pytest.mark.parametrize("phase", ["stop", "dump", "uploads", "manifest", "fsync"])
def test_backup_fault_never_publishes_manifest_and_resumes_writers(tmp_path, monkeypatch, phase):
    deployment = SuccessfulDeployment(running=b"web\napi\ndb\n")
    original_run = deployment.run

    def run(*args, **kwargs):
        if (phase == "stop" and args[0] == "stop"
                or phase == "dump" and args[0] == "exec"
                or phase == "uploads" and args[0] == "run"):
            raise OSError(28, "synthetic disk/operation fault")
        return original_run(*args, **kwargs)

    deployment.run = run
    if phase == "manifest":
        def dump(value, stream, **kwargs):
            stream.write('{"format":')
            raise OSError(28, "synthetic full disk")
        monkeypatch.setattr(manage.json, "dump", dump)
    if phase == "fsync":
        def fsync(fd):
            raise OSError(28, "synthetic full disk")
        monkeypatch.setattr(manage.os, "fsync", fsync)
    with pytest.raises(OSError):
        deployment.backup(tmp_path / "backup")
    assert deployment.calls[-1] == ("start", "api", "web")
    assert not (tmp_path / "backup/manifest.json").exists()


def test_completed_manifest_hashes_match_and_writers_stay_stopped(tmp_path):
    deployment = SuccessfulDeployment()
    deployment.backup(tmp_path / "backup")
    manifest = json.loads((tmp_path / "backup/manifest.json").read_text())
    assert all(manage.digest(tmp_path / "backup" / name) == value
               for name, value in manifest["files"].items())
    assert not (tmp_path / "backup/manifest.json.pending").exists()
    assert not any(call[0] in ("start", "stop") for call in deployment.calls)


@pytest.mark.parametrize("phase", ["database", "uploads", "revision"])
def test_restore_failure_keeps_app_stopped_and_retains_partial_data(tmp_path, phase):
    backup_files(tmp_path)

    class PartialRestore(SuccessfulDeployment):
        imported = False

        def sql(self, query):
            if query.startswith("SELECT COUNT"):
                return "1" if self.imported else "0"
            return "wrong-revision"

        def run(self, *args, **kwargs):
            result = super().run(*args, **kwargs)
            if args[0] == "exec":
                self.imported = True
                if phase == "database":
                    raise RuntimeError("partial SQL import")
            if args[0] == "run" and args[-1] == "import" and phase == "uploads":
                raise RuntimeError("partial upload import")
            return result

    deployment = PartialRestore()
    with pytest.raises((RuntimeError, ValueError)):
        deployment.restore(tmp_path)
    assert deployment.imported
    assert not any(call[0] in ("start", "down", "rm") for call in deployment.calls)
    assert all(call[-1] == "db" for call in deployment.calls if call[0] == "up")
    with pytest.raises(ValueError, match="non-empty"):
        deployment.restore(tmp_path)


def test_missing_schema_revision_rejected_before_docker(tmp_path):
    backup_files(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    del manifest["schema_revision"]
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    deployment = FakeDeployment()
    with pytest.raises(ValueError, match="schema"):
        deployment.restore(tmp_path)
    assert deployment.calls == []
