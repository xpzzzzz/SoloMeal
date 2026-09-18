"""Run tests only against the dedicated solomeal_test database; no URL output."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.core.config import Settings
from sqlalchemy.engine import make_url

url = make_url(Settings().database_url)
if url.get_backend_name() != "mysql":
    raise SystemExit("Configure the dedicated MySQL instance first")
env = os.environ.copy()
env["SOLOMEAL_TEST_DATABASE_URL"] = url.set(database="solomeal_test").render_as_string(
    hide_password=False
)
env["PYTHONDONTWRITEBYTECODE"] = "1"
with tempfile.TemporaryDirectory(prefix="solomeal-pytest-") as temp:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--tb=short", f"--basetemp={temp}/run", *sys.argv[1:]], cwd=ROOT, env=env
    )
raise SystemExit(result.returncode)
