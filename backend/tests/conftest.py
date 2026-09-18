import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient
from sqlalchemy.engine import make_url


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = os.environ.get("SOLOMEAL_TEST_DATABASE_URL")
    if url:
        parsed = make_url(url)
        # Never run destructive migration tests on the development or another app database.
        if parsed.get_backend_name() != "mysql" or parsed.database != "solomeal_test":
            raise RuntimeError("MySQL tests require the dedicated solomeal_test database")
    else:
        url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    monkeypatch.setenv("SOLOMEAL_DATABASE_URL", url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    # Parallel test workers are intentionally unsupported: one isolated schema per suite.
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    app = create_app(Settings(_env_file=None, receipt_storage_dir=tmp_path / "uploads"))
    try:
        with TestClient(app) as result:
            yield result
    finally:
        command.downgrade(config, "base")
