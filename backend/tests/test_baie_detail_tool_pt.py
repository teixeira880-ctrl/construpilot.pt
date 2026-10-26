"""Ferramenta do Assistente draw_window_detail (.pt): esquema estrito, 3 artefactos, idempotência, erro legível."""
import asyncio

from engines import baie_detail_tool as W


class _Coll:
    def __init__(self):
        self.docs = []

    async def update_one(self, q, upd, upsert=False):
        if not any(all(d.get(k) == v for k, v in q.items()) for d in self.docs):
            self.docs.append(dict(upd["$setOnInsert"]))


class _DB:
    assistant_artifacts = _Coll()


def _args(**over):
    a = {k: None for k in W.WINDOW_TOOLS[0]["parameters"]["properties"]}
    a.update(ouvrage="fenetre", pose="applique_int", coffre="aucun", isolation="iti", materiau="pvc", mur="parpaing", seuil_pmr=False, lang="fr")
    a.update(over)
    return a


def test_descricao_em_portugues_e_esquema_estrito():
    t = W.WINDOW_TOOLS[0]
    assert t["strict"] and "PORMENOR DE MONTAGEM" in t["description"]
    assert sorted(t["parameters"]["required"]) == sorted(t["parameters"]["properties"])


def test_tres_artefactos_e_forca_pt():
    db = _DB()
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(W.execute_window_tool("draw_window_detail", _args(), user, conv, db))
    assert out["ok"], out
    assert [a["format"] for a in (out["artifact"], out["horizontal_artifact"], out["pdf_artifact"])] == ["png", "png", "pdf"]
    assert len(db.assistant_artifacts.docs) == 3 and db.assistant_artifacts.docs[0]["schema_args"]["lang"] == "pt"
    asyncio.run(W.execute_window_tool("draw_window_detail", _args(), user, conv, db))
    assert len(db.assistant_artifacts.docs) == 3
