from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import Field, model_validator

from .food import Input, Label, Quantity


class PriceQuote(Input):
    ingredient_id: UUID
    package_quantity: Quantity
    package_price: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    source: Label
    observed_on: date


class ScoreWeights(Input):
    inventory: int = Field(default=60, ge=0, le=100, strict=True)
    expiry: int = Field(default=40, ge=0, le=100, strict=True)
    repetition: int = Field(default=10, ge=0, le=100, strict=True)
    purchase_cost: int = Field(default=0, ge=0, le=100, strict=True)

    @model_validator(mode="after")
    def nonzero(self):
        if not any(self.model_dump().values()):
            raise ValueError("At least one score weight must be positive")
        return self


class AgentPlanningInput(Input):
    """Conditions the agent may choose. Price facts are absent: source and date come from the
    user's saved quote records, never from a model-authored value."""

    use_saved_quotes: bool = Field(default=True, strict=True)
    score_weights: ScoreWeights = Field(default_factory=ScoreWeights)
    include_optional: bool = Field(default=False, strict=True)
    servings: int | None = Field(default=None, ge=1, le=10, strict=True)
    max_minutes: int | None = Field(default=None, ge=1, le=480, strict=True)
    equipment: list[Label] | None = Field(default=None, max_length=15)
    excluded_ingredients: list[Label] = Field(default_factory=list, max_length=100)
    budget: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)

    def as_planning(self):
        """PlanningInput with no request-time quotes; only the server supplies price facts."""
        return PlanningInput(**self.model_dump())


class PlanningInput(AgentPlanningInput):
    quotes: list[PriceQuote] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def unique_quotes(self):
        ids = [q.ingredient_id for q in self.quotes]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate price quote")
        if any(q.observed_on > date.today() for q in self.quotes):
            raise ValueError("Price date cannot be in the future")
        return self


class PlanInput(Input):
    recipe_id: UUID
    constraints: PlanningInput = Field(default_factory=PlanningInput)


class AgentPlanInput(Input):
    recipe_id: UUID
    constraints: AgentPlanningInput = Field(default_factory=AgentPlanningInput)


class RevisePlanInput(PlanInput):
    expected_version: int = Field(ge=1, strict=True)


class ConfirmPlanInput(Input):
    expected_version: int = Field(ge=1, strict=True)
