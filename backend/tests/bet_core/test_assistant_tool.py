"""Outil Assistant « étude BET complète » : lecture IA simulée, correction après contrôle, livrables stockés."""
import asyncio
import base64
import copy
import io
import json
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

from engines.bet_core import assistant_tool, checks, pipeline, reader

CASE = json.loads((Path(__file__).parents[2] / "engines/bet_core/cases/la_courneuve.json").read_text(encoding="utf-8"))


def _pdf(titles):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=landscape(A3))
    for t in titles:
        c.drawString(50, 50, t)
        c.rect(100, 100, 800, 500)
        c.showPage()
    c.save()
    return buf.getvalue()


class Coll:
    def __init__(self):
        self.docs = []

    def _match(self, d, q):
        return all(d.get(k) == v for k, v in q.items())

    async def find_one(self, q, proj=None):
        for d in self.docs:
            if self._match(d, q):
                out = copy.deepcopy(d)
                for k, v in (proj or {}).items():
                    if v == 0:
                        out.pop(k, None)
                return out
        return None

    def find(self, q, proj=None):
        docs = [copy.deepcopy(d) for d in self.docs if self._match(d, q)]

        class Cur:
            def sort(self, key, direction=1):
                docs.sort(key=lambda d: d.get(key), reverse=direction < 0)
                return self

            def __aiter__(self):
                self._it = iter(docs)
                return self

            async def __anext__(self):
                try:
                    return next(self._it)
                except StopIteration:
                    raise StopAsyncIteration
        return Cur()

    async def update_one(self, q, upd, upsert=False):
        for d in self.docs:
            if self._match(d, q):
                d.update(upd.get("$set", {}))
                return
        if upsert:
            d = dict(q)
            d.update(upd.get("$setOnInsert", {}))
            d.update(upd.get("$set", {}))
            self.docs.append(d)


class DB:
    def __init__(self):
        self.assistant_docs, self.assistant_artifacts, self.bet_study_jobs, self.bet_models = Coll(), Coll(), Coll(), Coll()
        self.assistant_doc_chunks = Coll()


def _llm(responses):
    calls = []

    async def llm(system, text, images=None, model=None, max_tokens=0):
        calls.append({"text": text, "n_images": len(images or [])})
        return responses[min(len(calls) - 1, len(responses) - 1)]
    return llm, calls


def test_classification_fr_pt():
    assert reader.classify("PCMI 02.2 PLAN DU REZ-DE-CHAUSSÉE éch 1/100") == "plan"
    assert reader.classify("COUPE 1") == "coupe"
    assert reader.classify("FAÇADE RUE") == "facade"
    assert reader.classify("PLANTA DO RÉS-DO-CHÃO") == "plan"
    assert reader.classify("ALÇADO NORTE") == "facade"
    assert reader.classify("Rapport G2 AVP sondages pressiométriques") == "g2"


def test_reader_retries_after_blocking_check():
    bad = copy.deepcopy(CASE)
    bad["openings"].append(dict(bad["openings"][0], id="DOUBLON"))      # baie comptée deux fois → GEO-04 bloquant
    _, an = pipeline.validate(bad)
    assert any(a["level"] == checks.BLOCK for a in an)
    llm, calls = _llm(["```json\n" + json.dumps(bad) + "\n```", json.dumps(CASE)])
    pdf = _pdf(["PLAN DU REZ-DE-CHAUSSEE", "COUPE 1", "FACADE RUE"])
    res = asyncio.run(reader.read_building([("PC.pdf", pdf)], "planchers poutrelles hourdis", "FR", llm=llm))
    assert res["ok"] and res["attempts"] == 2
    assert calls[0]["n_images"] == 3 and "ANOMALIES BLOQUANTES" in calls[1]["text"]


def test_reader_gives_questions_when_unfixable():
    bad = copy.deepcopy(CASE)
    del bad["levels"]
    llm, _ = _llm([json.dumps(bad)])
    res = asyncio.run(reader.read_building([("PC.pdf", _pdf(["PLAN DU RDC"]))], "", "FR", llm=llm, max_fix=1))
    assert not res["ok"] and res["questions"]


def test_tool_end_to_end_stores_three_artifacts():
    db = DB()
    pdf = _pdf(["PLAN DU SOUS-SOL", "PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"])
    db.assistant_docs.docs.append({"doc_id": "doc_1", "user_id": "u1", "filename": "PC.pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(pdf).decode()})
    llm, _ = _llm([json.dumps(CASE)])
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["doc_1"], "hypotheses": "", "country": "FR"},
                                             user, conv, db, llm=llm, background=False))
    assert out["ok"]
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, user, conv, db))
    assert st["status"] == "done", st
    assert {a["format"] for a in st["artifacts"]} == {"pdf", "zip", "xlsx"}
    assert st["blocking"] == 0 and len(st["sheets"]) >= 20
    assert len(db.assistant_artifacts.docs) == 3
    # un autre utilisateur ne voit ni le job ni les documents
    other = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, {"user_id": "u2"}, conv, db))
    assert "error" in other
    denied = asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["doc_1"], "hypotheses": "", "country": "FR"},
                                                {"user_id": "u2"}, conv, db, llm=llm, background=False))
    assert "error" in denied


def test_tool_specs_are_strict():
    for t in assistant_tool.TOOLS:
        assert t["strict"] and t["parameters"]["additionalProperties"] is False
        assert set(t["parameters"]["required"]) == set(t["parameters"]["properties"])


def test_branding_only_for_pro_and_business():
    class U:
        def __init__(self, doc): self.doc = doc
        async def find_one(self, q, proj=None): return dict(self.doc)
    db = DB()
    db.users = U({"brand_company_name": "ACME BTP", "brand_logo_b64": None, "brand_accent_color": "#123456"})
    for at, branded in (("pro", True), ("pro_business", True), ("particulier", False), (None, False)):
        b = asyncio.run(assistant_tool._default_branding(db, "u1", {"user_id": "u1", "account_type": at}))
        assert bool(b and b.get("company_name") == "ACME BTP") is branded, at


def test_out_of_domain_model_gives_questions_not_crash(tmp_path):
    bad = copy.deepcopy(CASE)
    bad["envelope"]["width_y"] = 14.0            # portée 13,6 m : hors domaine poutrelles-hourdis
    _, an = pipeline.validate(bad)
    assert any(a["code"] == "GEO-40" and a["level"] == checks.BLOCK for a in an)
    res = pipeline.run(bad, tmp_path, stem="T")
    assert res["status"] == "MODELE_INVALIDE" and not res["files"]


def test_pipeline_catches_engine_errors(tmp_path, monkeypatch):
    from engines.bet_core import structure
    monkeypatch.setattr(structure, "compute", lambda m: (_ for _ in ()).throw(ValueError("boom")))
    res = pipeline.run(copy.deepcopy(CASE), tmp_path, stem="T")
    assert res["status"] == "MODELE_INVALIDE" and any(a["code"] == "CALC-00" for a in res["anomalies"])


def test_same_documents_give_same_results_without_rereading():
    db = DB()
    pdf = _pdf(["PLAN DU SOUS-SOL", "PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"])
    db.assistant_docs.docs.append({"doc_id": "doc_1", "user_id": "u1", "filename": "PC.pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(pdf).decode()})
    llm, calls = _llm([json.dumps(CASE)])
    user = {"user_id": "u1"}
    res = []
    for req in ("r1", "r2"):                         # deux demandes distinctes, mêmes pièces, mêmes hypothèses
        conv = {"conversation_id": "c1", "_quote_request_id": req}
        out = asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["doc_1"], "hypotheses": "", "country": "FR"},
                                                 user, conv, db, llm=llm, background=False))
        res.append(asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, user, conv, db)))
    assert len(calls) == 1 and res[1]["cached"] is True
    assert res[0]["devis_ht"] == res[1]["devis_ht"] and res[0]["sheets"] == res[1]["sheets"]
    # hypothèses différentes (ex. correction de l'utilisateur) → nouveau relevé
    conv = {"conversation_id": "c1", "_quote_request_id": "r3"}
    asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["doc_1"], "hypotheses": "murs parpaing 20", "country": "FR"},
                                       user, conv, db, llm=llm, background=False))
    assert len(calls) == 2


def test_large_pdf_stored_in_chunks_is_read():
    """PC / G2 de plus de 8 Mo : l'Assistant .fr les stocke en morceaux de 1 Mo (assistant_doc_chunks)."""
    db = DB()
    pdf = _pdf(["PLAN DU SOUS-SOL", "PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"])
    parts = [pdf[i:i + 1000] for i in range(0, len(pdf), 1000)]
    db.assistant_docs.docs.append({"doc_id": "big", "user_id": "u1", "filename": "PCMI01.pdf", "mime": "application/pdf", "chunk_count": len(parts)})
    for i, part in enumerate(parts):
        db.assistant_doc_chunks.docs.append({"doc_id": "big", "user_id": "u1", "index": i, "data_b64": base64.b64encode(part).decode()})
    db.assistant_docs.docs.append({"doc_id": "dup", "user_id": "u1", "filename": "PCMI01 (2).pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(pdf).decode()})
    docs = asyncio.run(assistant_tool._load_assistant_docs(db, ["big", "dup"], "u1"))
    assert len(docs) == 1 and docs[0][1] == pdf                     # morceaux recollés, doublon écarté
    llm, _ = _llm([json.dumps(CASE)])
    out = asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["big", "dup"], "hypotheses": "", "country": "FR"},
                                             {"user_id": "u1"}, {"conversation_id": "c1"}, db, llm=llm, background=False))
    assert out["ok"]
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, {"user_id": "u1"}, {}, db))
    assert st["status"] == "done"
    db.assistant_doc_chunks.docs.pop()                              # morceau manquant → message clair, pas de plantage
    bad = asyncio.run(assistant_tool.execute("generate_full_bet_study", {"document_ids": ["big"], "hypotheses": "", "country": "FR"},
                                             {"user_id": "u1"}, {"conversation_id": "c2"}, db, llm=llm, background=False))
    assert "réimportez" in bad["error"]


def test_read_is_robust_to_datetimes_and_bad_ids():
    from datetime import datetime, timedelta
    db = DB()
    db.bet_study_jobs.docs.append({"job_id": "j1", "user_id": "u1", "status": "running",
                                   "updated_at": datetime.utcnow() - timedelta(hours=2)})      # datetime naïf (pas une chaîne)
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": "j1"}, {"user_id": "u1"}, {}, db))
    assert st["status"] == "failed" and "relancez" in st["error"]
    assert "error" in asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": ""}, {"user_id": "u1"}, {}, db))
