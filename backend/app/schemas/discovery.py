from typing import Annotated
from uuid import UUID

from pydantic import Field, StringConstraints, field_validator

from .food import Input, Label, VersionInput

# Draft storage is deliberately permissive: one unusable quantity must not hide the
# rest of a candidate batch. Validation reports the field, acceptance enforces it.
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
RawText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=1000)]


def as_text(value):
    """Keep model-authored values as editable text instead of failing the whole payload."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("Expected text or a number")
    if isinstance(value, (str, int, float)):
        return str(value).strip()
    raise ValueError("Expected text or a number")


class DraftIngredientLine(Input):
    name: Text = ""
    quantity: str | None = None
    unit: str | None = None
    optional: bool = Field(default=False, strict=True)
    resolved_ingredient_id: UUID | None = None

    @field_validator("quantity", "unit", mode="before")
    @classmethod
    def accept_plain_numbers(cls, value):
        return as_text(value)


class DraftPayload(Input):
    name: Text = ""
    # Numbers stay text until acceptance: "两人份" must display and be fixable, not 422.
    servings: str | None = None
    minutes: str | None = None
    equipment: list[RawText] = Field(default_factory=list, max_length=25)
    steps: list[RawText] = Field(default_factory=list, max_length=40)
    ingredients: list[DraftIngredientLine] = Field(default_factory=list, max_length=60)
    # Tags a human picks; stored as text so an unknown value stays visible and fixable.
    cooking_methods: list[Text] = Field(default_factory=list, max_length=8)

    @field_validator("servings", "minutes", mode="before")
    @classmethod
    def accept_plain_counts(cls, value):
        return as_text(value)

    @field_validator("equipment", "steps", "cooking_methods", mode="before")
    @classmethod
    def accept_single_string(cls, value):
        return [value] if isinstance(value, str) else value


class DiscoveryInput(Input):
    """Conditions for one generation. Price and inventory facts stay server-side."""

    servings: int | None = Field(default=None, ge=1, le=10, strict=True)
    max_minutes: int | None = Field(default=None, ge=1, le=480, strict=True)
    equipment: list[Label] | None = Field(default=None, max_length=15)
    excluded_ingredients: list[Label] = Field(default_factory=list, max_length=100)
    requirement: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=0, max_length=500)
    ] = ""
    prefer_inventory: bool = Field(default=True, strict=True)


class DraftCreateInput(Input):
    payload: DraftPayload


class DraftEditInput(VersionInput):
    payload: DraftPayload


class DraftValidateInput(Input):
    payload: DraftPayload | None = None


class DraftAcceptInput(VersionInput):
    acknowledge_warnings: bool = Field(default=False, strict=True)
