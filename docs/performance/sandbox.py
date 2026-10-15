"""Guards shared by diagnostic tools, never imported by the application."""
import os

from sqlalchemy.engine import make_url


def require_sandbox(url):
    parsed = make_url(url)
    if (os.environ.get("SOLOMEAL_PERF_SANDBOX") != "1"
            or parsed.drivername != "mysql+pymysql"
            or parsed.host != "db"
            or parsed.database != "solomeal_perf_m1"):
        raise RuntimeError("Only the isolated Compose performance database is allowed")


def require_models_off(settings):
    if any((settings.agent_enabled, settings.receipt_vision_enabled, settings.receipt_ocr_enabled,
            settings.recipe_discovery_enabled, settings.model_name,
            settings.model_api_key and settings.model_api_key.get_secret_value())):
        raise RuntimeError("Performance tools require every model path disabled")
