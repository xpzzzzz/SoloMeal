from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Label = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=11, decimal_places=3)]


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StapleInput(Input):
    is_staple: bool = Field(strict=True)


class IngredientInput(Input):
    name: Label
    unit: Literal["g", "ml", "piece"]
    is_staple: bool = Field(default=False, strict=True)


class AliasInput(Input):
    alias: Label


class BatchInput(Input):
    ingredient_id: UUID
    quantity: Quantity
    unit: Literal["g", "kg", "ml", "l", "piece"]
    expires_on: date | None = None
    expiry_source: Literal["user", "package", "estimate", "unknown"] = "unknown"
    location: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
    ] = "fridge"

    @model_validator(mode="after")
    def validate_expiry(self):
        if (self.expires_on is None) != (self.expiry_source == "unknown"):
            raise ValueError("Date and its source must be supplied together")
        return self


class AdjustmentInput(Input):
    quantity: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=3)] | None = None
    expected_version: int = Field(ge=1, strict=True)
    expires_on: date | None = None
    expiry_source: Literal["user", "package", "estimate", "unknown"] | None = None
    location: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)
    ] | None = None

    @model_validator(mode="after")
    def validate_changes(self):
        fields = self.model_fields_set - {"expected_version"}
        if not fields:
            raise ValueError("Supply at least one change")
        for field in fields - {"expires_on"}:
            if getattr(self, field) is None:
                raise ValueError("Only the expiry date may be cleared")
        if fields & {"expires_on", "expiry_source"}:
            if not {"expires_on", "expiry_source"} <= fields:
                raise ValueError("Date and its source must be supplied together")
            if (self.expires_on is None) != (self.expiry_source == "unknown"):
                raise ValueError("Date and its source must be supplied together")
        return self


class VersionInput(Input):
    expected_version: int = Field(ge=1, strict=True)


class ArchiveInput(VersionInput):
    archived: bool = Field(strict=True)


class RecipeItem(Input):
    optional: bool = Field(default=False, strict=True)
    ingredient_id: UUID
    quantity: Quantity
    unit: Literal["g", "kg", "ml", "l", "piece"]


class RecipeInput(Input):
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    servings: int = Field(ge=1, le=10, strict=True)
    minutes: int = Field(ge=1, le=480, strict=True)
    equipment: list[Label] = Field(min_length=1, max_length=15)
    steps: list[
        Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    ] = Field(min_length=1, max_length=30)
    source: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    ingredients: list[RecipeItem] = Field(min_length=1, max_length=40)

    @model_validator(mode="after")
    def required_item(self):
        if not any(not item.optional for item in self.ingredients):
            raise ValueError("At least one required ingredient is needed")
        return self


class RecipeUpdateInput(RecipeInput):
    expected_version: int = Field(ge=1, strict=True)


class CookingInput(Input):
    include_optional: bool = Field(default=False, strict=True)
    recipe_id: UUID
    servings: int = Field(ge=1, le=10, strict=True)

    plan_id: UUID | None = None
    expected_plan_version: int | None = Field(default=None, ge=1, strict=True)

    @model_validator(mode="after")
    def plan_fields(self):
        if (self.plan_id is None) != (self.expected_plan_version is None):
            raise ValueError("Plan id and version must be supplied together")
        return self
