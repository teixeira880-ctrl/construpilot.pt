"""Testes para registry.pricing_claude e registry.zonas_sismicas_pt."""
from __future__ import annotations

import pytest

from engines.bet_agent.registry.pricing_claude import (
    PRICING_USD_PER_MTOK,
    Usage,
    available_models,
    estimate_cost_eur,
    is_known_model,
)
from engines.bet_agent.registry.zonas_sismicas_pt import (
    AGR_TIPO1_M_S2,
    AGR_TIPO2_M_S2,
    SeismicConfidence,
    get_seismic_params,
)


# ---------------------------------------------------------------------------
# pricing_claude
# ---------------------------------------------------------------------------

def test_pricing_opus_input_output_tokens() -> None:
    """1 M input + 0.5 M output no Opus 5.5 ⇒ 4 + 10 = 14 USD → 14 × 0.93 ≈ 13.02 EUR."""
    usage = Usage(input_tokens=1_000_000, output_tokens=500_000)
    eur = estimate_cost_eur("claude-opus-5-5", usage, usd_eur_rate=0.93)
    assert eur == pytest.approx(14.0 * 0.93, abs=1e-4)


def test_pricing_sonnet_cheaper_than_opus_for_same_usage() -> None:
    usage = Usage(input_tokens=100_000, output_tokens=10_000)
    opus_eur = estimate_cost_eur("claude-opus-5-5", usage)
    sonnet_eur = estimate_cost_eur("claude-sonnet-5-5", usage)
    assert sonnet_eur < opus_eur


def test_pricing_cache_read_cheapest_component() -> None:
    """Cache read deve custar aproximadamente 1/20 do input normal (Opus)."""
    pricing = PRICING_USD_PER_MTOK["claude-opus-5-5"]
    assert pricing["cache_read"] < pricing["input"] / 10


def test_pricing_cache_write_1h_costlier_than_5m() -> None:
    for model in ("claude-opus-5-5", "claude-sonnet-5-5"):
        p = PRICING_USD_PER_MTOK[model]
        assert p["cache_write_1h"] > p["cache_write_5m"]


def test_pricing_unknown_model_uses_opus_fallback() -> None:
    usage = Usage(input_tokens=1_000, output_tokens=500)
    eur_unknown = estimate_cost_eur("future-model-x-99", usage)
    eur_opus = estimate_cost_eur("claude-opus-5-5", usage)
    assert eur_unknown == pytest.approx(eur_opus, abs=1e-8)


def test_pricing_cache_write_ttl_switch() -> None:
    usage = Usage(input_tokens=0, output_tokens=0, cache_creation_input_tokens=1_000_000)
    eur_5m = estimate_cost_eur("claude-opus-5-5", usage, cache_write_ttl="5m")
    eur_1h = estimate_cost_eur("claude-opus-5-5", usage, cache_write_ttl="1h")
    assert eur_1h > eur_5m


def test_pricing_known_models_includes_opus_and_sonnet() -> None:
    assert is_known_model("claude-opus-5-5")
    assert is_known_model("claude-sonnet-5-5")
    assert not is_known_model("not-a-real-model")
    models = available_models()
    assert "claude-opus-5-5" in models
    assert "claude-sonnet-5-5" in models


# ---------------------------------------------------------------------------
# zonas_sismicas_pt
# ---------------------------------------------------------------------------

def test_lisboa_zone_confirmed() -> None:
    p = get_seismic_params("Lisboa", classe_solo="C")
    assert p.tipo1_zone == "1.3"
    assert p.tipo2_zone == "2.3"
    assert p.agR_tipo1_m_s2 == pytest.approx(1.50)
    assert p.agR_tipo2_m_s2 == pytest.approx(1.70)
    assert p.confidence == SeismicConfidence.CONFIRMADO


def test_porto_zone_pendente_validacao() -> None:
    p = get_seismic_params("Porto", classe_solo="C")
    assert p.tipo1_zone == "1.6"
    assert p.tipo2_zone == "2.5"
    assert p.confidence == SeismicConfidence.PENDENTE


def test_unknown_municipio_returns_pendente_with_none_zones() -> None:
    p = get_seismic_params("Vila-das-Fictícias", classe_solo="A")
    assert p.tipo1_zone is None
    assert p.tipo2_zone is None
    assert p.confidence == SeismicConfidence.PENDENTE


def test_normalize_accents_and_hyphens() -> None:
    """'Évora' deve mapear como 'evora'."""
    p = get_seismic_params("Évora", classe_solo="B")
    assert p.tipo1_zone == "1.4"


def test_unknown_soil_class_fallback_a_pendente() -> None:
    p = get_seismic_params("Lisboa", classe_solo="Z")
    assert p.classe_solo == "A"
    assert p.confidence == SeismicConfidence.PENDENTE


def test_agr_tables_complete() -> None:
    for z in ("1.1", "1.2", "1.3", "1.4", "1.5", "1.6"):
        assert z in AGR_TIPO1_M_S2
    for z in ("2.1", "2.2", "2.3", "2.4", "2.5"):
        assert z in AGR_TIPO2_M_S2


def test_note_pt_mentions_predimensioning() -> None:
    p = get_seismic_params("Lisboa", "C")
    assert "pré-dimensionamento" in p.note_pt.lower()
    assert "técnico responsável" in p.note_pt.lower()
