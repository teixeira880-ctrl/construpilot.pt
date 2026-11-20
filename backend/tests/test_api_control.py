"""Admin → IA → «Todas as IA e API»: desligar retira a chave do processo (sem a apagar), religar devolve-a;
Emergent nunca se desliga; pelo menos uma IA de conversa fica ligada; crédito nunca expõe a chave."""
import asyncio

import pytest

from engines import api_control as ac


class _Settings:
    def __init__(self):
        self.doc = {}

    async def find_one(self, q, *a, **k):
        return dict(self.doc) if self.doc else None

    async def update_one(self, q, upd, upsert=False):
        for k, v in (upd.get("$set") or {}).items():
            if "." in k:
                a, b = k.split(".", 1)
                self.doc.setdefault(a, {})[b] = v
            else:
                self.doc[k] = v
        for k, v in (upd.get("$push") or {}).items():
            self.doc.setdefault(k, []).extend(v["$each"])


class _Empty:
    def find(self, *a, **k):
        class _C:
            def __aiter__(self):
                return self

            async def __anext__(self):
                raise StopAsyncIteration
        return _C()


class _DB:
    def __init__(self):
        self.app_settings = _Settings()
        self.ai_usage_monthly = _Empty()


@pytest.fixture()
def fake_db(monkeypatch):
    import core.db
    db = _DB()
    monkeypatch.setattr(core.db, "db", db)
    ac._apply(set())
    ac._STASH.clear()
    ac._BAL_CACHE.clear()
    yield db
    ac._apply(set())


def test_desligar_e_religar_devolve_a_chave(fake_db, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-voz")
    st = asyncio.run(ac.set_enabled("elevenlabs", False, who="admin@x"))
    assert st["enabled"] is False and st["configured"] is True
    import os
    assert "ELEVENLABS_API_KEY" not in os.environ
    st = asyncio.run(ac.set_enabled("elevenlabs", True))
    assert os.environ["ELEVENLABS_API_KEY"] == "sk-voz" and st["enabled"]
    assert [x["enabled"] for x in fake_db.app_settings.doc["log"]] == [False, True]


def test_emergent_nao_se_desliga(fake_db):
    with pytest.raises(ValueError):
        asyncio.run(ac.set_enabled("emergent", False))


def test_uma_ia_de_conversa_fica_sempre_ligada(fake_db):
    asyncio.run(ac.set_enabled("anthropic", False))
    asyncio.run(ac.set_enabled("gemini", False))
    with pytest.raises(ValueError):
        asyncio.run(ac.set_enabled("openai", False))
    from engines import assistant_fallback as af
    assert af._on("anthropic") is False and af.claude_available() is False and af.fallback_available() is False


def test_credito_sem_api_de_saldo_e_erro_sem_chave(fake_db, monkeypatch):
    monkeypatch.setenv("PERPLEXITY_API_KEY", "pplx-secret")
    r = asyncio.run(ac.balance("perplexity"))
    assert r["kind"] == "none"

    async def boom():
        raise RuntimeError("401 pplx-secret")
    monkeypatch.setenv("ELEVENLABS_API_KEY", "sk-secret")
    monkeypatch.setitem(ac.BALANCE, "elevenlabs", boom)
    r = asyncio.run(ac.balance("elevenlabs", fresh=True))
    assert r["kind"] == "error" and "secret" not in r["message"]


def test_visao_geral_lista_todas(fake_db, monkeypatch):
    for pid in ac.BALANCE:
        async def ok(pid=pid):
            return {"kind": "balance", "remaining": 1, "unit": "x"}
        monkeypatch.setitem(ac.BALANCE, pid, ok)
    out = asyncio.run(ac.overview())
    ids = [p["id"] for p in out["providers"]]
    assert {"emergent", "openai", "anthropic", "gemini", "kling", "elevenlabs", "perplexity"} <= set(ids)
    assert all("sk-" not in str(p) for p in out["providers"])
