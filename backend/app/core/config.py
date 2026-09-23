from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SOLOMEAL_",
        env_file=Path(__file__).resolve().parents[2] / ".env",
        extra="ignore",
    )
    database_url: str = "mysql+pymysql://solomeal:CHANGE_ME@127.0.0.1:3306/solomeal?charset=utf8mb4"
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
