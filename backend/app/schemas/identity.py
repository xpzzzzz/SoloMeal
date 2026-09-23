from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_]+$")
    password: str = Field(min_length=10, max_length=128)

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value):
        return value.lower()


class UserView(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    username: str


class SessionView(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: int


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    equipment: list[Label] = Field(default_factory=list, max_length=30)
    excluded_ingredients: list[Label] = Field(default_factory=list, max_length=100)
    default_servings: int = Field(default=1, ge=1, le=10, strict=True)
    max_minutes: int = Field(default=30, ge=1, le=480, strict=True)
    personal_time_enabled: bool = Field(default=True, strict=True)
    personalization_enabled: bool = Field(default=True, strict=True)
