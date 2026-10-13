"""Piloto automático Google Ads — testes puros de `plan_actions` (sem rede)."""
from __future__ import annotations

from datetime import datetime, timezone

from growth.ads_autopilot import plan_actions

TODAY = datetime(2026, 10, 14, 12, 0, tzinfo=timezone.utc)

SETTINGS_BASE = {
    "max_daily_increase_pct": 20,
    "pause_cost_no_conv_eur": 40,
    "min_daily_budget_eur": 3,
    "activate_growth_campaigns": True,
}


def _mk(id_, name, status, daily_budget, month_cost, cost14, conv14):
    return {
        "id": id_, "name": name, "status": status,
        "daily_budget": daily_budget, "month_cost": month_cost,
        "cost14": cost14, "conv14": conv14,
        "budget_shared": False, "budget_resource": f"customers/x/campaignBudgets/{id_}",
        "resource": f"customers/x/campaigns/{id_}",
    }


def _camps():
    return [
        _mk("A", "A", "ENABLED", 10.0, 120.0, 100.0, 5),
        _mk("B", "B", "ENABLED", 10.0, 90.0, 60.0, 0),
        _mk("C", "Growth · x", "PAUSED", 5.0, 0.0, 0.0, 0),
        _mk("D", "D", "ENABLED", 5.0, 30.0, 30.0, 1),
    ]


def test_cap_300_pausa_B_e_D_reduz_A_e_nao_ativa_C():
    """Com teto 300 €: pausa B (sem conversões), pausa D (sem margem), reduz A para 3,00 €/dia, NÃO ativa C."""
    s = {**SETTINGS_BASE, "monthly_cap_eur": 300}
    actions = plan_actions(_camps(), s, TODAY)
    by_type = {}
    for a in actions:
        by_type.setdefault(a["type"], []).append(a)
    paused_ids = {a["campaign"]["id"] for a in by_type.get("pause", [])}
    enabled_ids = {a["campaign"]["id"] for a in by_type.get("enable", [])}
    budget_actions = {a["campaign"]["id"]: a for a in by_type.get("budget", [])}
    assert "B" in paused_ids, f"B deve ser pausada por 0 conversões em 14 dias; actions={actions}"
    assert "D" in paused_ids, f"D deve ser pausada por falta de margem; actions={actions}"
    assert "C" not in enabled_ids, f"C NÃO deve ser ativada; actions={actions}"
    assert "A" in budget_actions, f"A deve ter ajuste de orçamento; actions={actions}"
    assert abs(budget_actions["A"]["to"] - 3.0) < 0.01, \
        f"A deve ser reduzida para 3,00 €/dia, foi {budget_actions['A']['to']}; actions={actions}"


def test_cap_200_pausa_tudo_teto_atingido():
    """Com teto 200 € e 240 € já gastos: pausa A, B e D (todas as ENABLED)."""
    s = {**SETTINGS_BASE, "monthly_cap_eur": 200}
    actions = plan_actions(_camps(), s, TODAY)
    assert all(a["type"] == "pause" for a in actions), f"só pausas esperadas; actions={actions}"
    paused_ids = {a["campaign"]["id"] for a in actions}
    assert paused_ids == {"A", "B", "D"}, f"paused={paused_ids}; actions={actions}"


def test_cap_zero_lista_vazia():
    """Com teto 0 € (não definido): `plan_actions` devolve []."""
    s = {**SETTINGS_BASE, "monthly_cap_eur": 0}
    assert plan_actions(_camps(), s, TODAY) == []
