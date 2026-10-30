"""Isolation guards: these tools must never accept the development/live database."""
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sandbox import require_models_off, require_sandbox
from run_m1 import context


class IsolationTests(unittest.TestCase):
    def test_wrong_database_or_host_rejected(self):
        with patch.dict(os.environ, {"SOLOMEAL_PERF_SANDBOX": "1"}):
            require_sandbox("mysql+pymysql://fake:fake@db/solomeal_perf_m1")
            for url in ("mysql+pymysql://fake:fake@db/solomeal",
                        "mysql+pymysql://fake:fake@127.0.0.1/solomeal_perf_m1",
                        "sqlite:///:memory:"):
                with self.assertRaises(RuntimeError):
                    require_sandbox(url)
        with patch.dict(os.environ, {"SOLOMEAL_PERF_SANDBOX": "0"}):
            with self.assertRaises(RuntimeError):
                require_sandbox("mysql+pymysql://fake:fake@db/solomeal_perf_m1")

    def test_model_configuration_rejected(self):
        from app.core.config import Settings
        settings = Settings(_env_file=None)
        require_models_off(settings)
        for flag in ('receipt_vision_enabled', 'receipt_ocr_enabled'):
            setattr(settings, flag, True)
            with self.assertRaises(RuntimeError):
                require_models_off(settings)
            setattr(settings, flag, False)

    def test_live_compose_project_rejected_before_command(self):
        with tempfile.TemporaryDirectory(prefix="solomeal-perf-guards-") as folder:
            path = Path(folder) / "state.json"
            path.write_text(json.dumps({"project": "solomeal-features-0921"}))
            with self.assertRaises(RuntimeError):
                context(path)


if __name__ == "__main__":
    unittest.main()
