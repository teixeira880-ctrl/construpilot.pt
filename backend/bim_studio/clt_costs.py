"""CLT budget and physical progress. Decimal arithmetic throughout."""
from __future__ import annotations

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Stage = Literal["compra", "producao", "transporte", "montagem", "entrega"]
Unit = Literal["m3", "m2", "m", "kg", "h", "un", "viagem", "lote", "L"]
Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=6)]
Quantity = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=6)]
Code = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")]
STAGES = ("compra", "producao", "transporte", "montagem", "entrega")
ZERO = Decimal(0)
CENT = Decimal("0.01")


def money(value):
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def percent(numerator, denominator):
    return money(numerator * 100 / denominator) if denominator else None


class Rate(BaseModel):
    code: Code
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["compra", "producao", "venda"]
    unit: Unit
    rate_eur: Money
    effective_from: date


class CostLine(BaseModel):
    code: Code
    stage: Stage
    name: str = Field(min_length=1, max_length=120)
    unit: Unit
    rate_id: str | None = Field(default=None, max_length=64)
    rate_eur: Money
    baseline_qty: Quantity = Field(gt=0)
    planned_to_date_qty: Quantity = ZERO
    accepted_qty: Quantity = ZERO
    actual_eur: Money = ZERO
    open_commitment_eur: Money = ZERO
    uncommitted_remaining_eur: Money | None = None
    actual_reference: str | None = Field(default=None, max_length=200)
    source_reference: str = Field(min_length=1, max_length=250)

    @model_validator(mode="after")
    def check_plan(self):
        if self.planned_to_date_qty > self.baseline_qty:
            raise ValueError("O avanço previsto não pode exceder a quantidade do orçamento.")
        if self.actual_eur and not (self.actual_reference or "").strip():
            raise ValueError("Indique a referência documental do custo real.")
        if not self.source_reference.strip():
            raise ValueError("Indique a referência de medição.")
        return self


class CostLot(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    revenue_eur: Money
    planned_delivery: date
    forecast_delivery: date | None = None
    accepted_delivery: date | None = None
    lines: list[CostLine] = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def check_lines(self):
        if len({line.code for line in self.lines}) != len(self.lines):
            raise ValueError("Cada artigo do lote deve ter um código único.")
        return self


def summary(lot: CostLot):
    grouped = {stage: [] for stage in STAGES}
    for line in lot.lines:
        grouped[line.stage].append(line)

    def aggregate(lines):
        budget = sum((x.baseline_qty * x.rate_eur for x in lines), ZERO)
        planned = sum((x.planned_to_date_qty * x.rate_eur for x in lines), ZERO)
        earned = sum((min(x.accepted_qty, x.baseline_qty) * x.rate_eur for x in lines), ZERO)
        actual = sum((x.actual_eur for x in lines), ZERO)
        committed = sum((x.open_commitment_eur for x in lines), ZERO)
        forecast = None
        if all(x.uncommitted_remaining_eur is not None for x in lines):
            forecast = actual + committed + sum((x.uncommitted_remaining_eur for x in lines), ZERO)
        return {
            "budget_eur": money(budget), "actual_eur": money(actual),
            "open_commitment_eur": money(committed), "earned_eur": money(earned),
            "cost_overrun_to_date_eur": money(actual - earned),
            "planned_percent": percent(planned, budget), "accepted_percent": percent(earned, budget),
            "forecast_cost_eur": money(forecast) if forecast is not None else None,
        }, forecast

    totals, forecast = aggregate(lot.lines)
    delivery = lot.accepted_delivery or lot.forecast_delivery
    margin = lot.revenue_eur - forecast if forecast is not None else None
    return {**totals, "revenue_eur": money(lot.revenue_eur),
            "forecast_margin_eur": money(margin) if margin is not None else None,
            "forecast_margin_percent": percent(margin, lot.revenue_eur) if margin is not None else None,
            "delay_days": (delivery - lot.planned_delivery).days if delivery else None,
            "stages": {stage: aggregate(lines)[0] for stage, lines in grouped.items() if lines}}
