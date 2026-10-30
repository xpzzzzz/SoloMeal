from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DismissInput(Input):
    reason: Literal["not_useful", "too_often", "already_done"] = "not_useful"


class AcceptInput(Input):
    expected_version: int = Field(ge=0, strict=True)


class SettingsInput(Input):
    expected_version: int = Field(ge=0, strict=True)
    enabled: bool = Field(strict=True)
    daily_limit: int = Field(ge=1, le=3, strict=True)
    quiet_start: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    quiet_end: str = Field(pattern=r"^(?:[01][0-9]|2[0-3]):[0-5][0-9]$")
    snooze_until: datetime | None = None

    @field_validator("snooze_until")
    @classmethod
    def aware_datetime(cls, value):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("snooze_until must include a timezone")
        return value


class TickInput(Input):
    user_id: UUID | None = None


class SimulateInput(Input):
    days: int = Field(ge=1, le=30, strict=True)


class ItemOut(BaseModel):
    id: str
    kind: Literal["expiring_batch", "shopping_stale"]
    priority: int
    title: str
    body: str
    why: str
    payload: dict
    action: dict
    suppress_hint: str
    status: Literal["pending", "accepted", "dismissed", "expired", "suppressed", "abandoned"]
    created_at: datetime
    expires_at: datetime | None
    version: int


class InboxMeta(BaseModel):
    as_of: str
    display_date: str
    enabled: bool
    daily_limit: int
    used_today: int
    quiet_hours: dict[str, str]
    suppressed_kinds: list[str]
    suppression_until: dict[str, str] = Field(default_factory=dict)
    pending_total: int
    demo_mode: bool = False


class InboxOut(BaseModel):
    items: list[ItemOut]
    meta: InboxMeta


class ItemResult(BaseModel):
    item: ItemOut


class AcceptResult(ItemResult):
    action: dict


class SettingsOut(BaseModel):
    enabled: bool
    daily_limit: int
    quiet_start: str
    quiet_end: str
    snooze_until: datetime | None
    version: int


class TickResult(BaseModel):
    users: int
    created: int
    expired: int
    suppressed: int
