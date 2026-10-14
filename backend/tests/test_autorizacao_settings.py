"""Testes da flag de ativação da venda (Lote N4)."""

import asyncio
from datetime import datetime, timezone

import pytest


# Fake Mongo mínimo com suporte a upsert
class _Col:
    def __init__(self):
        self.docs: list = []

    async def find_one(self, filt):
        for d in self.docs:
            if all(d.get(k) == v for k, v in filt.items()):
                return dict(d)
        return None

    async def update_one(self, filt, update, upsert=False):
        for i, d in enumerate(self.docs):
            if all(d.get(k) == v for k, v in filt.items()):
                self.docs[i] = {**d, **(update.get("$set") or {})}
                return
        if upsert:
            self.docs.append({**filt, **(update.get("$set") or {})})


class _DB:
    def __init__(self):
        self._cols = {}

    def __getattr__(self, name):
        if name not in self._cols:
            self._cols[name] = _Col()
        return self._cols[name]


@pytest.fixture(autouse=True)
def db_patch(monkeypatch):
    from engines.autorizacao_obras_pt import settings as settings_mod
    monkeypatch.setattr(settings_mod, "db", _DB(), raising=False)
    yield


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_defaults_sao_sale_desativada():
    from engines.autorizacao_obras_pt.settings import get_settings
    s = _run(get_settings())
    assert s["sale_enabled"] is False
    assert s["price_eur"] == 39
    assert s["included_in_pro"] is True
    assert s["included_in_business"] is True


def test_set_persiste_e_atualiza():
    from engines.autorizacao_obras_pt.settings import get_settings, set_settings
    s = _run(set_settings({"sale_enabled": True, "price_eur": 49}, admin_user_id="admin1"))
    assert s["sale_enabled"] is True
    assert s["price_eur"] == 49
    # re-leitura
    s2 = _run(get_settings())
    assert s2["sale_enabled"] is True
    assert s2["price_eur"] == 49


def test_set_rejeita_preco_negativo():
    from engines.autorizacao_obras_pt.settings import set_settings
    s = _run(set_settings({"price_eur": -10}))
    assert s["price_eur"] == 39  # repõe default


def test_set_ignora_chaves_desconhecidas():
    from engines.autorizacao_obras_pt.settings import set_settings
    s = _run(set_settings({"malicioso": "x", "sale_enabled": True}))
    assert "malicioso" not in s
    assert s["sale_enabled"] is True


def test_guia_pepu_pdf_valido():
    from engines.autorizacao_obras_pt.guia_pepu import gerar_guia_pepu_pdf
    pdf = gerar_guia_pepu_pdf()
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000
