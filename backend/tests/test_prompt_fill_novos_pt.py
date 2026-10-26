"""Pilotagem por prompt (.pt): extractors «estimativa» (página /estimation) e «fundacao» (leitura de plantas), portados das apps
«devis» e «plan_fondation» do /ai-fill .fr, e medição de custos da chamada IA. LLM sempre simulado (sem rede)."""
import asyncio
import json
import os
import sys
import types
from unittest.mock import patch

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_prompt_fill_pt")
os.environ.setdefault("JWT_SECRET", "test")

from engines.prompt_fill import base, estimativa, fundacao  # noqa: E402
from engines.prompt_fill.base import REGISTRY, run_extractor  # noqa: E402


def _run(ext, resposta, context=None):
    async def go():
        with patch("engines.prompt_fill.base._ask_text", return_value=resposta):
            return await run_extractor(ext, prompt="dummy", context=context or {})
    return asyncio.run(go())


def test_new_apps_are_registered_by_the_route():
    import routes.prompt_fill  # noqa: F401 — o registo é feito pela rota
    assert {"estimativa", "fundacao"} <= set(REGISTRY)
    assert REGISTRY["estimativa"].required_fields() == ["project_type", "surface"]
    assert REGISTRY["fundacao"].required_fields() == ["type"]


def test_estimativa_happy_path_and_region_outside_list_is_dropped():
    ext = estimativa.EstimativaExtractor()
    out = _run(ext, json.dumps({"ok": True, "params": {"project_type": "renovation_appartement", "surface": "90", "finish_level": "standard",
                                                       "region": "Porto", "city": "Matosinhos", "construction_year": "1985"},
                                "ai_filled": ["project_type", "surface", "region", "city"], "defaults_used": ["finish_level"], "notes": []}))
    assert out["ok"] and out["params"]["surface"] == 90.0 and out["params"]["region"] == "Porto" and out["params"]["construction_year"] == 1985
    out = _run(ext, json.dumps({"ok": True, "params": {"project_type": "cuisine", "surface": 12, "region": "Île-de-France"}}))
    assert out["ok"] and "region" not in out["params"]


def test_estimativa_rejects_unknown_type_and_asks_for_missing_area():
    ext = estimativa.EstimativaExtractor()
    out = _run(ext, json.dumps({"ok": True, "params": {"project_type": "nave_espacial", "surface": 50}}))
    assert out["ok"] is False and "desconhecido" in out["error"]
    out = _run(ext, json.dumps({"ok": False, "params": {"project_type": "salle_de_bain"}, "missing_fields": ["surface"],
                                "clarification_question": "Qual é a área da casa de banho em m²?"}))
    assert out["ok"] is False and out["params"] == {"project_type": "salle_de_bain"} and "área" in out["clarification_question"]


def test_estimativa_prompt_is_portuguese_and_lists_pt_regions():
    ext = estimativa.EstimativaExtractor()
    assert "Matosinhos→Porto" in ext.prompt_system and "Madeira" in ext.schema["properties"]["region"]["enum"]
    assert set(ext.schema["properties"]["project_type"]["enum"]) >= {"renovation_complete", "salle_de_bain", "piscine_beton"}


def test_fundacao_converts_and_validates():
    ext = fundacao.FundacaoExtractor()
    out = _run(ext, json.dumps({"ok": True, "params": {"type": "semelle_isolee", "repere": "S1", "longueur_m": "0.80", "largeur_m": 0.8,
                                                       "hauteur_m": 0.4, "nombre": "3"}}))
    assert out["ok"] and out["params"] == {"type": "semelle_isolee", "repere": "S1", "longueur_m": 0.8, "largeur_m": 0.8, "hauteur_m": 0.4, "nombre": 3}
    out = _run(ext, json.dumps({"ok": True, "params": {"type": "estaca_magica"}}))
    assert out["ok"] is False and "desconhecido" in out["error"]
    out = _run(ext, json.dumps({"ok": True, "params": {"type": "longrine", "longueur_m": -2}}))
    assert out["ok"] is False and "inválido" in out["error"]
    out = _run(ext, json.dumps({"ok": False, "clarification_question": "Que tipo de elemento quer acrescentar?"}))
    assert out["ok"] is False and out["clarification_question"].startswith("Que tipo")


def test_llm_call_is_metered(monkeypatch):
    seen = {}

    class FakeMetered:
        def __init__(self, **kw):
            seen.update(kw)

        def with_model(self, *a):
            seen["model"] = a
            return self

        async def send_message(self, msg):
            return '{"ok": true, "params": {}}'

    fake_chat = types.ModuleType("emergentintegrations.llm.chat")
    fake_chat.UserMessage = lambda text: text
    fake_metering = types.ModuleType("engines.expenses.metering")
    fake_metering.MeteredChat = FakeMetered
    monkeypatch.setenv("EMERGENT_LLM_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "emergentintegrations.llm.chat", fake_chat)
    monkeypatch.setitem(sys.modules, "engines.expenses.metering", fake_metering)
    assert asyncio.run(base._ask_text("x")) == '{"ok": true, "params": {}}'
    assert seen["expense_feature"] == "prompt_fill" and seen["api_key"] == "test-key"
