"""Testes do metering de custos (cost.py)."""
from __future__ import annotations

import os

import pytest

from engines.bet_agent.cost import DossierMeter


def test_meter_records_single_call_opus() -> None:
    meter = DossierMeter(project_id="t")
    meter.record("claude-opus-5-5", input_tokens=10_000, output_tokens=5_000, cache_read_tokens=0)
    cb = meter.to_breakdown()
    assert cb.input_tokens == 10_000
    assert cb.output_tokens == 5_000
    # opus: 13.80 input + 69.00 output / 1M
    # = 10_000*13.80/1_000_000 + 5_000*69.00/1_000_000 = 0.138 + 0.345 = 0.483
    assert cb.eur_total == pytest.approx(0.483, abs=1e-4)
    assert cb.exceeded_limit is False


def test_meter_sums_multiple_calls() -> None:
    meter = DossierMeter(project_id="t")
    meter.record("claude-sonnet-5-5", 20_000, 5_000, 0)
    meter.record("claude-opus-5-5", 50_000, 10_000, 0)
    cb = meter.to_breakdown()
    assert cb.input_tokens == 70_000
    assert cb.output_tokens == 15_000


def test_meter_exceeds_limit_triggers_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BET_AGENT_COST_LIMIT_EUR", "0.1")
    meter = DossierMeter(project_id="t")
    # ~0.5 EUR com 5000 output opus
    meter.record("claude-opus-5-5", 10_000, 5_000, 0)
    cb = meter.to_breakdown()
    assert cb.exceeded_limit is True
    assert cb.eur_limit == 0.1


def test_meter_unknown_model_falls_back_to_opus() -> None:
    meter = DossierMeter(project_id="t")
    meter.record("some-future-model", 1_000, 500, 0)
    cb = meter.to_breakdown()
    # Deve estar acima de zero (não é silenciosamente zero).
    assert cb.eur_total > 0


def test_meter_cache_read_tokens_discounted() -> None:
    meter = DossierMeter(project_id="t")
    meter.record("claude-opus-5-5", 0, 0, cache_read_tokens=100_000)
    cb = meter.to_breakdown()
    # cache_read opus = 1.38 EUR/1M; 100k * 1.38 / 1e6 = 0.138
    assert cb.eur_total == pytest.approx(0.138, abs=1e-4)


def test_meter_calls_detail_available() -> None:
    meter = DossierMeter(project_id="t")
    meter.record("claude-sonnet-5-5", 1_000, 500, 0)
    meter.record("claude-opus-5-5", 2_000, 1_000, 100)
    detail = meter.calls_detail()
    assert len(detail) == 2
    assert detail[0]["model"] == "claude-sonnet-5-5"
    assert detail[1]["model"] == "claude-opus-5-5"
    assert all("eur" in d for d in detail)
