"""Ponte Assistente ↔ calcul_ucrania: dossier ucraniano em artifact, dossier inglês em artifacts (mostrado pelo cartão de ação)."""
import asyncio
import os

os.environ.setdefault("CP_RENDER_SPP", "1")
os.environ.setdefault("CP_RENDER_W", "160")

from engines.calc_lots.assistant_bridge import execute_calc_tool  # noqa: E402


class _Col:
    def __init__(self):
        self.docs = {}

    async def find_one(self, q, proj=None):
        return self.docs.get(q.get("artifact_id"))

    async def update_one(self, q, upd, upsert=False):
        self.docs.setdefault(q["artifact_id"], upd["$setOnInsert"])


class _DB:
    def __init__(self):
        self.assistant_artifacts = _Col()


def test_dossier_ingles_visivel_no_cartao():
    db = _DB()
    out = asyncio.run(execute_calc_tool("calcul_ucrania", {"exemplo": True, "sistema": "clt", "empresa": "clt-rezult"},
                                        {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}, db))
    assert out["ok"] and out["artifact"]["format"] == "pdf"
    assert len(out["artifacts"]) == 1 and out["artifacts"][0]["format"] == "pdf"
    assert out["artifacts"][0]["artifact_id"] != out["artifact"]["artifact_id"]
    assert len(db.assistant_artifacts.docs) == 3              # UK + pré-visualização + EN


def test_caso_home_a_entrega_pacote_completo():
    db = _DB()
    out = asyncio.run(execute_calc_tool("calcul_ucrania", {"caso": "home_a_rezult_kyiv"}, {"user_id": "u2"},
                                        {"conversation_id": "c2", "_quote_request_id": "r2"}, db))
    nomes = [a["filename"] for a in out["artifacts"]]
    assert out["ok"] and len(nomes) == 5
    for k in ("Dossier-EN", "Drawings-UK", "Drawings-EN", "Estimate-UK", "Estimate-EN"):
        assert any(n.startswith(f"ConstruPilot_{k}_") for n in nomes), k
