from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .food import Input, Quantity
from .planning import AgentPlanningInput


class RunInput(Input):
    message: str = Field(min_length=1, max_length=4000)
    parent_run_id: UUID | None = None
    session_id: UUID | None = None
    expected_session_version: int | None = Field(default=None, ge=1, strict=True)
    constraints: AgentPlanningInput | None = None

    @model_validator(mode="after")
    def validate_context(self):
        if not self.message.strip():
            raise ValueError("Message cannot be blank")
        if (self.session_id is None) != (self.expected_session_version is None):
            raise ValueError("Session and version must be supplied together")
        if self.session_id and self.parent_run_id:
            raise ValueError("Choose a session or a parent run")
        return self


class EmptyInput(Input):
    pass


class UndoInput(Input):
    cooking_id: UUID


class PurchaseEstimateInput(Input):
    """A user-stated shortage, priced from that ingredient's saved quote."""

    ingredient_id: UUID
    quantity: Quantity
    unit: Literal["g", "kg", "ml", "l", "piece"]
    budget: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
