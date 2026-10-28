from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from .food import Input

METHOD_WORDS = {
    "stir_fry": ("炒",), "steam": ("蒸",), "boil": ("煮",),
    "stew": ("炖",), "bake": ("烤",), "pan_fry": ("煎",),
    "cold": ("凉拌",),
}


class MemoryInput(Input):
    category: Literal["ingredient", "cooking_method", "time"]
    target: str = Field(min_length=1, max_length=80)
    polarity: Literal[-1, 1]

    @field_validator("target")
    @classmethod
    def target_is_trimmed(cls, value):
        if not value.strip() or value != value.strip():
            raise ValueError("Target must be nonblank and trimmed")
        return value

    @model_validator(mode="after")
    def valid_time(self):
        if self.category == "cooking_method" and self.target not in METHOD_WORDS:
            raise ValueError("Unsupported cooking method")
        if self.category == "time" and (
            not self.target.isascii() or not self.target.isdigit()
            or not 1 <= int(self.target) <= 480 or self.polarity != 1
        ):
            raise ValueError("Time preference must be 1 to 480 minutes and positive")
        return self


class SuggestMemoryInput(MemoryInput):
    source_quote: str = Field(min_length=2, max_length=500)


class ConfirmMemoryInput(MemoryInput):
    run_id: UUID
    step: int = Field(ge=1, le=8, strict=True)
