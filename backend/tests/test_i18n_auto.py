"""Tradução automática completa da interface (routes/i18n_auto.py) — sem rede nem IA real."""
import json
import os

import pytest

os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "test_i18n")

mongomock_motor = pytest.importorskip("mongomock_motor")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import routes.i18n_auto as m  # noqa: E402


@pytest.fixture()
def env(tmp_path, monkeypatch):
    man = tmp_path / "i18n_manifest.json"
    man.write_text(json.dumps({"version": "t1", "exact": ["Escolher plano", "Guardar"],
                               "patterns": ["Poupa {0} + IVA por ano", "Escolher {0}"]}), "utf-8")
    monkeypatch.setattr(m, "MANIFEST_PATHS", [man])
    monkeypatch.setattr(m, "_manifest_mtime", 0.0)
    monkeypatch.setattr(m, "db", mongomock_motor.AsyncMongoMockClient()["i18n_test"])
    m._dict_cache.clear()
    calls = []

    async def fake_llm(system, prompt, max_tokens):
        calls.append(prompt)
        items = json.loads(prompt.split("\n", 2)[2])
        tr = {"Escolher plano": "Choose plan", "Guardar": "Save",
              "Poupa {0} + IVA por ano": "Save {0} + VAT per year", "Escolher {0}": "Choose {0}"}
        return json.dumps({k: tr.get(v, v) for k, v in items.items()})

    monkeypatch.setattr(m, "_llm", fake_llm)
    app = FastAPI()
    app.state.limiter = m.limiter
    app.include_router(m.router, prefix="/api")
    return TestClient(app), calls


def test_valid_keeps_placeholders():
    assert m._valid("Poupa {0} por ano", "Save {0} per year")
    assert not m._valid("Poupa {0} por ano", "Save per year")
    assert not m._valid("Olá", "")


def test_batches_split_by_size():
    bs = list(m._batches(["a" * 3000, "b" * 3000, "c"]))
    assert len(bs) == 2 and bs[1] == ["b" * 3000, "c"]


@pytest.mark.asyncio
async def test_warm_translates_whole_manifest(env):
    _, calls = env
    res = await m.warm("en")
    assert res["translated"] == 4
    have = await m.cached("en")
    assert have["Poupa {0} + IVA por ano"] == "Save {0} + VAT per year"
    # segunda passagem: nada novo → nenhuma chamada à IA
    n = len(calls)
    res2 = await m.warm("en")
    assert res2["todo"] == 0 and len(calls) == n, res2


def test_translate_only_manifest_strings(env):
    client, calls = env
    r = client.post("/api/i18n/translate", json={"lang": "en", "texts": ["Guardar", "Rua do Cliente 12, Lisboa"]})
    assert r.status_code == 200
    assert r.json()["translations"] == {"Guardar": "Save"}
    assert all("Rua do Cliente" not in c for c in calls)  # dados de clientes nunca saem


def test_dict_after_warm(env):
    client, _ = env
    client.post("/api/i18n/translate", json={"lang": "en", "texts": ["Guardar", "Escolher plano",
                                                                       "Poupa {0} + IVA por ano", "Escolher {0}"]})
    d = client.get("/api/i18n/dict/en").json()
    assert d["complete"] is True and d["version"] == "t1"
    assert d["exact"]["Escolher plano"] == "Choose plan"
    assert ["Escolher {0}", "Choose {0}"] in d["patterns"]


def test_unsupported_lang(env):
    client, _ = env
    assert client.get("/api/i18n/dict/xx").status_code == 404
