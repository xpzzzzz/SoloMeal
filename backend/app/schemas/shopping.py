from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import Field, model_validator

from .food import BatchInput, VersionInput
from .planning import PriceQuote


class SaveQuoteInput(PriceQuote):
    currency: Literal["CNY"] = "CNY"
    expected_version: int = Field(ge=0, strict=True)

    @model_validator(mode="after")
    def valid_date(self):
        if self.observed_on > date.today():
            raise ValueError("Price date cannot be in the future")
        return self


class ShoppingCreateInput(VersionInput):
    plan_id: UUID


class PurchaseItem(BatchInput):
    actual_cost: Decimal | None = Field(default=None, ge=0, max_digits=8, decimal_places=2)
    currency: Literal["CNY"] = "CNY"


class ShoppingEditInput(VersionInput):
    items: list[PurchaseItem] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_items(self):
        ids = [i.ingredient_id for i in self.items]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate ingredient")
        return self
