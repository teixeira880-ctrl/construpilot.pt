"""Testes do fluxo de subscrição (Lote N3 + endurecimento N5)."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest


# ------- Fake Mongo (motor-like) -------------------------------------------

class _AsyncCursor:
    def __init__(self, docs):
        self._docs = list(docs)

    def __aiter__(self):
        self._i = 0
        return self

    async def __anext__(self):
        if self._i >= len(self._docs):
            raise StopAsyncIteration
        d = self._docs[self._i]; self._i += 1
        return dict(d)


class _FakeCollection:
    def __init__(self):
        self.docs: list = []

    def _match(self, d, filt):
        for k, v in filt.items():
            if isinstance(v, dict):
                if "$ne" in v and d.get(k) == v["$ne"]:
                    return False
            else:
                if d.get(k) != v:
                    return False
        return True

    async def insert_one(self, doc):
        self.docs.append(dict(doc))

    async def find_one(self, filt):
        for d in self.docs:
            if self._match(d, filt):
                return dict(d)
        return None

    def find(self, filt=None):
        return _AsyncCursor(d for d in self.docs if self._match(d, filt or {}))

    async def find_one_and_update(self, filt, update, return_document=True):
        for i, d in enumerate(self.docs):
            if not self._match(d, filt):
                continue
            nd = {**d, **(update.get("$set") or {})}
            self.docs[i] = nd
            return nd
        return None

    async def delete_one(self, filt):
        for i, d in enumerate(self.docs):
            if self._match(d, filt):
                self.docs.pop(i)
                return type("R", (), {"deleted_count": 1})
        return type("R", (), {"deleted_count": 0})


class _FakeDB:
    def __init__(self):
        self._cols: dict = {}

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

def test_catalogo_json_vazio_em_producao():
    import json
    from engines.autorizacao_obras_pt.subscricao import CATALOGO_PATH
    data = json.loads(CATALOGO_PATH.read_text(encoding="utf-8"))
    assert data == [], "JSON do catálogo tem de ficar vazio — demo copiada para _demo.json"


def test_listar_tecnicos_vazio_quando_sem_dados():
    from engines.autorizacao_obras_pt.subscricao import listar_tecnicos
    lista = _run(listar_tecnicos())
    assert lista == []


def test_criar_e_listar_tecnico_via_admin():
    from engines.autorizacao_obras_pt.subscricao import criar_tecnico, listar_tecnicos
    t = _run(criar_tecnico({"nome": "Ana", "email": "ana@ex.pt", "especialidade": "arquitetura"}))
    assert t["id"].startswith("tec_") and t["ativo"] is True
    lista = _run(listar_tecnicos())
    assert len(lista) == 1 and lista[0]["nome"] == "Ana"


def test_tecnico_desconhecido_falha():
    from engines.autorizacao_obras_pt.subscricao import criar_pedido_subscricao
    with pytest.raises(ValueError):
        _run(criar_pedido_subscricao({"x": 1}, tecnico_id="nao_existe"))


def test_tecnico_customizado_cria_pedido():
    from engines.autorizacao_obras_pt.subscricao import criar_pedido_subscricao
    out = _run(criar_pedido_subscricao(
        {"procedimento": "licenciamento"},
        tecnico_custom={"nome": "José Silva", "email": "jose@silva.pt",
                        "especialidade": "arquitetura", "numero": "9999"},
        requerente_nome="Cliente Teste",
    ))
    assert len(out["signing_token"]) > 20
    assert out["tecnico"]["origem"] == "indicado_pelo_requerente"
    assert out["link_subscrever"].startswith("/subscrever/")
    assert "expires_at" in out


def test_tecnico_customizado_sem_email_falha():
    from engines.autorizacao_obras_pt.subscricao import criar_pedido_subscricao
    with pytest.raises(ValueError):
        _run(criar_pedido_subscricao({}, tecnico_custom={"nome": "x", "email": "sem_arroba"}))


def test_fluxo_subscrever_e_impede_reutilizacao():
    from engines.autorizacao_obras_pt.subscricao import (
        criar_pedido_subscricao, ler_pedido_por_token, registar_termo_responsabilidade,
    )
    out = _run(criar_pedido_subscricao(
        {"dossier_id": "d1"},
        tecnico_custom={"nome": "T1", "email": "t1@a.pt", "especialidade": "arquitetura"},
    ))
    token = out["signing_token"]
    doc = _run(ler_pedido_por_token(token))
    assert doc and doc.get("estado") == "pendente"

    res = _run(registar_termo_responsabilidade(
        token, "T1", "OA", "123", "arquitetura", assinatura_b64=None))
    assert res["ok"] is True

    # Reutilização bloqueada
    res2 = _run(registar_termo_responsabilidade(token, "Outro", "OA", "999", "arquitetura"))
    assert res2["ok"] is False and res2["error"] == "ja_assinado"

    # Leitura após assinatura devolve erro «ja_assinado»
    doc2 = _run(ler_pedido_por_token(token))
    assert doc2 and doc2.get("error") == "ja_assinado"


def test_token_expirado(monkeypatch):
    from engines.autorizacao_obras_pt import subscricao as sub
    from engines.autorizacao_obras_pt.subscricao import (
        criar_pedido_subscricao, ler_pedido_por_token, registar_termo_responsabilidade,
    )
    out = _run(criar_pedido_subscricao(
        {"d": 1}, tecnico_custom={"nome": "T", "email": "t@a.pt", "especialidade": "arquitetura"}))
    token = out["signing_token"]

    # Força expiração: substitui _now para devolver uma data > expires_at
    futuro = datetime.now(timezone.utc) + timedelta(days=60)
    monkeypatch.setattr(sub, "_now", lambda: futuro)

    doc = _run(ler_pedido_por_token(token))
    assert doc and doc.get("error") == "expirado"

    res = _run(registar_termo_responsabilidade(token, "T", "OA", "123", "arquitetura"))
    assert res["ok"] is False and res["error"] == "expirado"


def test_assistant_tool_devolve_diagnostico():
    from engines.assistant_autorizacao_tool import run_autorizacao_tool
    r = _run(run_autorizacao_tool("preparar_autorizacao_obras",
                                   {"tipo_obra": "anexo", "altura_m": 2.0, "area_implantacao_m2": 8,
                                    "confina_via_publica": False}, {}, {}))
    assert r["ok"] is True
    assert r["procedimento"] == "isento"
    assert r["cta_pagina"] == "/particulares/autorizacao-obras"
