from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field, StringConstraints, model_validator

from .food import Input, Label, Quantity, VersionInput


class ReceiptLine(Input):
    name: Label
    quantity: Quantity | None = None
    unit: Literal["g", "kg", "ml", "l", "piece"] | None = None
    amount: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    # No confidence score can authorize an inventory mutation.
    uncertain: bool = Field(default=True, strict=True)
    excluded: bool = Field(default=False, strict=True)

    @model_validator(mode="after")
    def unknown_requires_review(self):
        if self.quantity is None or self.unit is None:
            self.uncertain = True
        return self


class ParsedReceipt(Input):
    purchased_on: date | None = None
    items: list[ReceiptLine] = Field(default_factory=list, max_length=100)


class DraftLine(ReceiptLine):
    ingredient_id: UUID | None = None
    expires_on: date | None = None
    expiry_source: Literal["user", "package", "estimate", "unknown"] = "unknown"
    location: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] = "fridge"


class ReceiptDraft(Input):
    purchased_on: date | None = None
    items: list[DraftLine] = Field(default_factory=list, max_length=100)


class ReceiptEditInput(VersionInput):
    draft: ReceiptDraft
