"""Typed contracts shared by the deterministic metré engine (readings → calculations → findings → quantities)."""
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field

State = Literal["confirmed", "probable", "indeterminate", "not_verifiable"]
STATE_LABEL_FR = {"confirmed": "confirmé", "probable": "probable", "indeterminate": "indéterminé",
                  "not_verifiable": "não verificável com os dados disponíveis"}


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


class Evidence(BaseModel):
    kind: Literal["plan_reading", "native_text", "zoom_crop", "user_statement", "calculation", "source"]
    ref: str | None = None
    page: int | None = None
    text: str | None = None


class Reading(BaseModel):
    """A dimension as read: a single value or several OCR candidates that are still undecided."""
    label: str
    value_m: float | None = None
    candidates_m: list[float] = Field(default_factory=list)
    origin: Literal["plan_reading", "native_text", "user_statement", "assumption"] = "plan_reading"
    evidence: Evidence | None = None
    plan_id: str | None = None
    page: int | None = None
    box: list[float] | None = None

    @property
    def state(self) -> State:
        if self.value_m is not None and not self.candidates_m:
            return "confirmed" if self.origin in ("native_text", "user_statement") else "probable"
        return "indeterminate"

    @property
    def usable(self) -> float | None:
        return self.value_m if self.state != "indeterminate" else None


class Calculation(BaseModel):
    calc_id: str = Field(default_factory=lambda: new_id("calc"))
    kind: str
    inputs: list[dict]
    formula: str
    result: float | None
    unit: str
    state: State
    reason: str
    tolerance: dict | None = None


class Finding(BaseModel):
    finding_id: str = Field(default_factory=lambda: new_id("find"))
    subject: str
    severity: Literal["info", "to_clarify", "demonstrated"]
    certainty: State
    explanation: str
    consequence: str | None = None
    action: str | None = None
    calc_id: str | None = None
    evidence: list[str] = Field(default_factory=list)


class QuantityLine(BaseModel):
    line_id: str = Field(default_factory=lambda: new_id("qty"))
    element: str
    location: str | None = None
    unit: str
    dimensions: dict
    formula: str
    gross: float | None
    deductions: list[dict] = Field(default_factory=list)
    net: float | None
    extra_pct: float | None = None
    order_qty: float | None = None
    rule: str | None = None
    sources: list[str] = Field(default_factory=list)
    state: State
    reason: str
    missing: list[str] = Field(default_factory=list)


def worst(*states: State) -> State:
    order = ["confirmed", "probable", "indeterminate", "not_verifiable"]
    return max(states, key=order.index) if states else "confirmed"
