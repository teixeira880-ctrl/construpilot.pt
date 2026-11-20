"""20/11: pedido de plantas de um lote depois de um estudo de geometria real → devolve o conjunto «Desenhos», nunca
«o motor de execução não suporta este contorno»."""
import asyncio

from engines.bet_core import assistant_tool as at


class _Col:
    def __init__(self, doc):
        self.doc = doc

    async def find_one(self, q, proj=None, sort=None):
        return dict(self.doc)


class _DB:
    def __init__(self, doc):
        self.bet_study_jobs = _Col(doc)


def test_geo_job_returns_drawings_not_geometry_review():
    job = {"job_id": "bet_x", "status": "done", "execution_verified": False, "points": [],
           "geo_engine": {"sheets": ["A01 Planta de arquitetura cotada", "EL01/EL02 Eletricidade", "AG01 Águas e esgotos",
                                     "VT01 Ventilação", "AQ01/AQ02 Aquecimento", "E02 Fundações cotadas"]},
           "artifacts": [{"artifact_id": "a1", "title": "Desenhos de execução", "kind": "plans_pdf"},
                         {"artifact_id": "a2", "title": "REH", "kind": "pdf"}]}
    out = asyncio.run(at._lot_plans(_DB(job), {"user_id": "u"}, {"conversation_id": "c"},
                                    {"lots": ["electricite", "chauffage"], "hypotheses": "", "job_id": ""}))
    assert out["ok"] and out.get("status") != "geometry_review"
    assert "não suporta" not in out["note"]
    assert out["sheets"]["Électricité"] == ["EL01", "EL02"] and out["sheets"]["Chauffage"] == ["AQ01", "AQ02"]
    assert [a["artifact_id"] for a in out["artifacts"]] == ["a1"]
