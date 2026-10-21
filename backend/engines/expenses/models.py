from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from engines.expenses.catalog import PROVIDERS, UNITS


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @field_validator("source_ref", check_fields=False, mode="before")
    @classmethod
    def trim_reference(cls, value):
        return value.strip() if isinstance(value, str) else value


class Amount(StrictModel):
    amount: Decimal = Field(ge=-1000000000, le=1000000000, max_digits=18, decimal_places=6)
    currency: str = Field(pattern=r"^[A-Z]{3}$")

    @field_validator("amount")
    @classmethod
    def finite(cls, value):
        if not value.is_finite():
            raise ValueError("Finite amount required")
        return value


class ExpenseInput(Amount):
    provider: str
    source_ref: str = Field(min_length=3, max_length=180)
    occurred_on: date
    feature: str = Field(default="invoice", min_length=1, max_length=80, pattern=r"^[\w .:/-]+$")
    user_id: str | None = Field(default=None, max_length=100)
    company_id: str | None = Field(default=None, max_length=100)
    scope: Literal["single", "monthly_total"] = "single"
    settled_eur: Decimal | None = Field(default=None, ge=-1000000000, le=1000000000, max_digits=18, decimal_places=6)
    settlement_ref: str | None = Field(default=None, max_length=180)
    confirmed_charge: Literal[True]
    is_test: bool = False

    @field_validator("provider")
    @classmethod
    def provider_exists(cls, value):
        if value not in PROVIDERS:
            raise ValueError("Unknown provider")
        return value

    @model_validator(mode="after")
    def settlement_evidence(self):
        if self.scope == "monthly_total" and (self.user_id or self.company_id):
            raise ValueError("Monthly provider totals cannot be attributed to individual users or companies")
        if self.currency == "EUR" and self.settled_eur is not None and self.settled_eur != self.amount:
            raise ValueError("EUR settlement must match EUR amount")
        if self.currency != "EUR" and self.settled_eur is not None and not (self.settlement_ref or "").strip():
            raise ValueError("Bank settlement reference required; no implicit FX")
        return self


class ConfirmationInput(Amount):
    source_ref: str = Field(min_length=3, max_length=180)
    settled_eur: Decimal | None = Field(default=None, ge=-1000000000, le=1000000000, max_digits=18, decimal_places=6)
    settlement_ref: str | None = Field(default=None, max_length=180)
    confirmed_charge: Literal[True]
    version: int = Field(ge=0)

    @model_validator(mode="after")
    def settlement_evidence(self):
        if self.currency == "EUR" and self.settled_eur is not None and self.settled_eur != self.amount:
            raise ValueError("EUR settlement must match EUR amount")
        if self.currency != "EUR" and self.settled_eur is not None and not (self.settlement_ref or "").strip():
            raise ValueError("Bank settlement reference required")
        return self


class BudgetInput(StrictModel):
    provider: str = "all"
    month: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount_eur: Decimal = Field(gt=0, le=1000000000, max_digits=15, decimal_places=2)
    warning_percent: int = Field(default=80, ge=1, le=99)

    @field_validator("provider")
    @classmethod
    def valid_provider(cls, value):
        if value != "all" and value not in PROVIDERS:
            raise ValueError("Unknown provider")
        return value


class RateInput(StrictModel):
    provider: str
    model: str = Field(default="", max_length=120)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    mode: Literal["tokens", "unit"]
    unit: str = "calls"
    per_units: Decimal = Field(default=1, gt=0, le=1000000000)
    price: Decimal = Field(default=0, ge=0, le=1000000000, max_digits=18, decimal_places=6)
    input_price: Decimal = Field(default=0, ge=0, le=1000000000, max_digits=18, decimal_places=6)
    output_price: Decimal = Field(default=0, ge=0, le=1000000000, max_digits=18, decimal_places=6)
    effective_from: date
    source_ref: str = Field(min_length=3, max_length=180)

    @field_validator("provider")
    @classmethod
    def provider_exists(cls, value):
        if value not in PROVIDERS:
            raise ValueError("Unknown provider")
        return value

    @field_validator("unit")
    @classmethod
    def unit_exists(cls, value):
        if value not in UNITS:
            raise ValueError("Unknown usage unit")
        return value


class EventOut(BaseModel):
    entry_id: str
    provider: str
    feature: str
    model: str = ""
    user_id: str | None = None
    company_id: str | None = None
    user_name: str | None = None
    company_name: str | None = None
    occurred_at: datetime
    state: str
    evidence: Literal["confirmed", "estimated", "unavailable", "reconciled", "local"]
    amount: str | None = None
    currency: str | None = None
    amount_eur: str | None = None
    units: dict[str, float] = Field(default_factory=dict)
    source_ref: str
    origin: str
    version: int = 0
    is_test: bool = False
    source_kind: str | None = None
    reconciled_by: str | None = None
    rate_ref: str | None = None
    scope: str = "single"


class LedgerOut(BaseModel):
    items: list[EventOut]
    total: int
    page: int
    page_size: int