"""Local Compose operations. Backups stop writers; restores only accept empty volumes."""

import argparse
import hashlib
import json
import os
import re
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def initialize(path, port):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(f"DB_PASSWORD={secrets.token_hex(24)}\nDB_ROOT_PASSWORD={secrets.token_hex(32)}\n"
                     f"BIND_ADDRESS=127.0.0.1\nHTTP_PORT={port}\nIMAGE_TAG=local\n"
                     "SOLOMEAL_AGENT_ENABLED=false\nSOLOMEAL_RECEIPT_VISION_ENABLED=false\n")


class Deployment:
    def __init__(self, project, env_file):
        if not re.fullmatch(r"solomeal-[a-z0-9][a-z0-9-]{0,48}", project):
            raise ValueError("Use an explicit solomeal- project name")
        if project in ("solomeal-dev", "solomeal-test"):
            raise ValueError("Reserved development/test project")
        values = dict(line.split("=", 1) for line in env_file.read_text(encoding="utf-8").splitlines()
                      if line and not line.startswith("#") and "=" in line)
        for name in ("DB_PASSWORD", "DB_ROOT_PASSWORD"):
            if not re.fullmatch(r"[a-f0-9]{32,128}", values.get(name, "")):
                raise ValueError("Database passwords must be generated hexadecimal values")
        self.project = project
        self.command = ["docker", "compose", "--project-directory", str(ROOT),
                        "--env-file", str(env_file.resolve()), "-f", str(ROOT / "compose.yaml"), "-p", project]

    def run(self, *args, stdin=None, stdout=None):
        result = subprocess.run([*self.command, *args], stdin=stdin,
                                stdout=stdout or subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        if result.returncode:
            # Compose expansion and DB diagnostics may carry credentials or user data.
            raise RuntimeError(f"Compose operation {args[0]} failed (exit {result.returncode})")
        return result.stdout or b""

    def sql(self, query):
        return self.run("exec", "-T", "db", "sh", "-c",
                        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot -N -B -D solomeal -e "$1"',
                        "sh", query).decode().strip()

    def upload(self, action, **streams):
        return self.run("run", "--rm", "--no-deps", "-T", "api",
                        "python", "scripts/archive_uploads.py", action, **streams)

    def backup(self, folder):
        folder.mkdir(parents=True, exist_ok=False)
        running = self.run("ps", "--services", "--status", "running").decode().split()
        writers = [s for s in ("web", "api") if s in running]
        try:
            if writers:
                self.run("stop", *writers)
            revision = self.sql("SELECT version_num FROM alembic_version")
            with (folder / "database.sql").open("xb") as stream:
                self.run("exec", "-T", "db", "sh", "-c",
                    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysqldump -uroot --single-transaction '
                    '--no-tablespaces --set-gtid-purged=OFF --hex-blob --default-character-set=utf8mb4 solomeal',
                    stdout=stream)
            with (folder / "uploads.tar").open("xb") as stream:
                self.upload("export", stdout=stream)
            manifest = {"format": "solomeal-backup-v1", "source_project": self.project,
                "created_at": datetime.now(timezone.utc).isoformat(), "schema_revision": revision,
                "consistency": "Compose web/api stopped during database and upload capture",
                "files": {name: digest(folder / name) for name in ("database.sql", "uploads.tar")}}
            pending = folder / "manifest.json.pending"
            with pending.open("x", encoding="utf-8") as stream:
                json.dump(manifest, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            pending.replace(folder / "manifest.json")
        finally:
            if writers:
                self.run("start", *reversed(writers))

    def restore(self, folder):
        manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
        if manifest.get("format") != "solomeal-backup-v1" or set(manifest.get("files", {})) != {"database.sql", "uploads.tar"}:
            raise ValueError("Unsupported backup manifest")
        if not isinstance(manifest.get("schema_revision"), str) or not manifest["schema_revision"]:
            raise ValueError("Missing backup schema revision")
        for name, expected in manifest["files"].items():
            if digest(folder / name) != expected:
                raise ValueError("Backup checksum mismatch")
        running = self.run("ps", "--services", "--status", "running").decode().split()
        if any(s in running for s in ("web", "api", "migrate")):
            raise ValueError("Restore requires application and migration services stopped")
        self.run("up", "-d", "--wait", "--wait-timeout", "180", "db")
        if self.sql("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='solomeal'") != "0":
            raise ValueError("Restore refuses non-empty database; use a new project")
        self.upload("empty")
        with (folder / "database.sql").open("rb") as stream:
            self.run("exec", "-T", "db", "sh", "-c",
                     'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -uroot --default-character-set=utf8mb4 solomeal',
                     stdin=stream)
        with (folder / "uploads.tar").open("rb") as stream:
            self.upload("import", stdin=stream)
        if self.sql("SELECT version_num FROM alembic_version") != manifest["schema_revision"]:
            raise ValueError("Restored migration revision differs from backup")
        # A failure leaves the target stopped and inspectable; never delete or retry into partial data.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("init", "backup", "restore"))
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--project")
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()
    if args.action == "init":
        if not 1024 <= args.port <= 65535:
            parser.error("Port must be between 1024 and 65535")
        initialize(args.env_file, args.port)
    else:
        if not args.project or not args.directory:
            parser.error("Backup/restore require explicit --project and --directory")
        deployment = Deployment(args.project, args.env_file)
        getattr(deployment, args.action)(args.directory.resolve())
    print(f"{args.action} completed")


if __name__ == "__main__":
    main()
