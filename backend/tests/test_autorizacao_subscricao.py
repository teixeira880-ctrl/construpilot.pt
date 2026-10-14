"""Testes do fluxo de subscrição por técnico parceiro (Lote N3).

Usa um fake Mongo in-memory próprio (sem deps novas).
"""

import asyncio
from datetime import datetime

import pytest


# ------- Fake Mongo (minimal) ----------------------------------------------

class _FakeCollection:
    def __init__(self):
        self.docs = []

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, filt):
        for d in self.docs:
            if all(d.get(k) == v for k, v in filt.items() if not isinstance(v, dict)):
                return dict(d)
        return None

    async def find_one_and_update(self, filt, update, return_document=True):
        for i, d in enumerate(self.docs):
            if not all(d.get(k) == v for k, v in filt.items() if not isinstance(v, dict)):
                continue
            # Suporta $ne (estado != "subscrito")
            cond_ok = True
            for k, v in filt.items():
                if isinstance(v, dict) and "$ne" in v:
                    if d.get(k) == v["$ne"]:
                        cond_ok = False
            if not cond_ok:
                continue
            nd = {**d, **(update.get("$set") or {})}
            self.docs[i] = nd
            return nd
        return None


class _FakeDB:
    def __init__(self):
        self._cols: dict[str, _FakeCollection] = {}

    def __getitem__(self, name: str) -> _FakeCollection:
        if name not in self._cols:
            self._cols[name] = _FakeCollection()
        return self._cols[name]

    def __getattr__(self, name: str) -> _FakeCollection:
        return self[name]


@pytest.fixture(autouse=True)
def fake_db(monkeypatch):
    db = _FakeDB()
    from engines.autorizacao_obras_pt import subscricao
    monkeypatch.setattr(subscricao, "db", db, raising=False)
    yield db


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ------- Testes ------------------------------------------------------------

def test_catalogo_tem_tecnicos():
    from engines.autorizacao_obras_pt.subscricao import carregar_tecnicos
    lista = carregar_tecnicos()
    assert len(lista) >= 4
    assert all("id" in t and "nome" in t and "especialidade" in t for t in lista)


def test_filtrar_tecnicos_por_especialidade():
    from engines.autorizacao_obras_pt.subscricao import filtrar_tecnicos
    arqs = filtrar_tecnicos(especialidade="arquitetura")
    assert len(arqs) >= 2
    assert all(t["especialidade"] == "arquitetura" for t in arqs)


def test_tecnico_desconhecido_falha():
    from engines.autorizacao_obras_pt.subscricao import criar_pedido_subscricao
    with pytest.raises(ValueError):
        _run(criar_pedido_subscricao({"x": 1}, "nao_existe"))


def test_fluxo_completo_pedir_ler_subscrever():
    from engines.autorizacao_obras_pt.subscricao import (
        criar_pedido_subscricao, ler_pedido_por_token, registar_termo_responsabilidade,
    )
    out = _run(criar_pedido_subscricao({"dossier_id": "d1", "procedimento": "licenciamento"},
                                        "arq_lisboa_01", "cliente@teste.pt"))
    token = out["signing_token"]
    assert len(token) > 20

    doc = _run(ler_pedido_por_token(token))
    assert doc is not None
    assert doc["estado"] == "pendente"
    assert doc["tecnico"]["id"] == "arq_lisboa_01"

    res = _run(registar_termo_responsabilidade(
        token, "Rita Costa", "OA", "17284", "arquitetura",
        assinatura_b64="iVBORw0KGgoAAAANSUhEUgAA", observacoes="OK"))
    assert res["ok"] is True

    res2 = _run(registar_termo_responsabilidade(
        token, "Outro", "OA", "9999", "arquitetura"))
    assert res2["ok"] is False


def test_assistant_tool_devolve_diagnostico():
    from engines.assistant_autorizacao_tool import run_autorizacao_tool
    r = _run(run_autorizacao_tool("preparar_autorizacao_obras",
                                   {"tipo_obra": "anexo", "altura_m": 2.0, "area_implantacao_m2": 8,
                                    "confina_via_publica": False},
                                   {}, {}))
    assert r["ok"] is True
    assert r["procedimento"] == "isento"
    assert r["cta_pagina"] == "/particulares/autorizacao-obras"
    assert "custo_min_eur" in r["estimativa"]
