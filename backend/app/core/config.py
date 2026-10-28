from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOLOMEAL_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )
    database_url: str = Field(default="mysql+pymysql://solomeal:CHANGE_ME@127.0.0.1:3306/solomeal?charset=utf8mb4", repr=False)
    session_ttl_seconds: int = Field(default=86400, ge=60, le=604800)

    agent_enabled: bool = False
    model_base_url: str = "https://api.openai.com/v1"
    model_name: str = ""
    model_tool_protocol: Literal["native", "json"] = "native"
    # Explicit provider extension for chat, independent of receipt vision.
    model_enable_thinking: bool | None = Field(default=None, strict=True)

    @field_validator("model_enable_thinking", "receipt_model_enable_thinking", mode="before")
    @classmethod
    def parse_optional_thinking(cls, value):
        if value == "omit":
            return None
        if isinstance(value, str) and value.lower() in ("true", "false"):
            return value.lower() == "true"
        return value

    model_max_completion_tokens: int = Field(default=1500, ge=1, le=3000, strict=True)

    @field_validator("model_max_completion_tokens", "discovery_max_output_tokens", mode="before")
    @classmethod
    def parse_chat_budget(cls, value):
        # Environment variables arrive as strings; keep bools and fractions invalid.
        if isinstance(value, str) and value.isascii() and value.isdecimal():
            return int(value)
        return value

    model_api_key: SecretStr | None = None
    # Hosted Mem0 is optional and independent of the chat model.
    mem0_enabled: bool = False
    mem0_api_key: SecretStr | None = None
    mem0_timeout_seconds: float = Field(default=2, gt=0, le=10)
    # Recipe discovery reuses the chat endpoint but has its own switch and output budget,
    # so enabling it cannot silently change the existing Agent's limits.
    recipe_discovery_enabled: bool = False
    discovery_max_output_tokens: int = Field(default=3000, ge=1, le=3000, strict=True)
    discovery_timeout_seconds: float = Field(default=30, gt=0, le=60)
    receipt_storage_dir: Path = Path(__file__).resolve().parents[2] / "private_uploads"
    receipt_parser_timeout_seconds: float = Field(default=30, gt=0, le=60)
    receipt_vision_enabled: bool = False
    # Provider extension; None omits the field for standard-compatible endpoints.
    receipt_model_enable_thinking: bool | None = Field(default=None, strict=True)
    receipt_parse_daily_limit: int = Field(default=10, ge=1, le=100)
    receipt_broker_url: SecretStr = SecretStr("amqp://guest:guest@127.0.0.1:5672//")
    receipt_task_max_attempts: int = Field(default=3, ge=1, le=5)
    receipt_task_deadline_seconds: int = Field(default=900, ge=30, le=3600)
    receipt_task_lease_seconds: int = Field(default=120, ge=15, le=300)
    receipt_worker_hard_limit_seconds: int = Field(default=90, ge=5, le=180)
    receipt_retry_seconds: float = Field(default=10, ge=0.1, le=60)
    receipt_dispatch_interval_seconds: float = Field(default=5, ge=0.1, le=30)
    receipt_worker_concurrency: int = Field(default=1, ge=1, le=4)
    receipt_recognition_mode: Literal["ocr_only", "vlm_only", "hybrid"] = "vlm_only"
    receipt_ocr_enabled: bool = False
    receipt_ocr_model_dir: Path | None = None
    receipt_ocr_min_confidence: float = Field(default=.85, ge=0, le=1)

    @model_validator(mode="after")
    def receipt_execution_bounds(self):
        if self.receipt_task_lease_seconds < self.receipt_worker_hard_limit_seconds + 10:
            raise ValueError("Receipt lease must exceed the worker hard limit by ten seconds")
        return self
