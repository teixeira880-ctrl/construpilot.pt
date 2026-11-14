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


def test_home_a_foto_3d_so_fotos_com_a_geometria_dos_planos():
    """14/11 (Martinho): «foto 3D da casa» com o Home A → só as fotos, feitas da geometria lida nos planos (recanto de entrada
    a sudeste no −1 e no R/C, 1.º andar em L), nunca o pacote de planos de execução nem um volume genérico."""
    from engines.calc_lots import pacote_ua
    m = pacote_ua.parametros("home_a_rezult_kyiv")["modelo_estrutural"]
    recanto = [[0, 0], [7.108, 0], [7.108, 1.831], [10.918, 1.831], [10.918, 13.527], [0, 13.527], [0, 0]]
    fechados = [mu for mu in m["muros"] if mu["pontos"][0] == mu["pontos"][-1]]
    assert sum(mu["pontos"] == recanto for mu in fechados) == 2                       # −1 e R/C
    assert not any(mu["pontos"] == [[0, 0], [10.918, 0], [10.918, 13.527], [0, 13.527], [0, 0]] for mu in fechados)
    db = _DB()
    out = asyncio.run(execute_calc_tool("calcul_ucrania", {"caso": "home_a_rezult_kyiv", "so_fotos": True}, {"user_id": "u3"},
                                        {"conversation_id": "c3", "_quote_request_id": "r3"}, db))
    assert out["ok"], out
    fmts = [a["format"] for a in out["artifacts"]]
    assert fmts and all(f in ("png", "jpg") for f in fmts)                          # só imagens
    assert not any("Drawings" in a["filename"] or "Estimate" in a["filename"] for a in out["artifacts"])
    assert "geometry read in the plans" in out["resume"]
