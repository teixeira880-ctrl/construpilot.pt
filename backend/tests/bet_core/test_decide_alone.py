"""Mode « décider seul » : l'agent tranche lui-même quand l'utilisateur dit « je n'ai que ces plans / faites au mieux »,
ne repose plus de questions, et liste ses décisions à la fin. Les questions restent affichées en mode normal."""
import asyncio
import base64
import copy
import io
import json
from pathlib import Path

from reportlab.lib.pagesizes import A3, landscape
from reportlab.pdfgen import canvas

from engines.bet_core import assistant_tool, reader
import importlib.util as _ilu
import pytest as _pt
_NO_RE2020 = _pt.mark.skipif(_ilu.find_spec("engines.calc_lots.re2020") is None, reason="motor RE2020 só existe no .fr")
_NO_PLANSRC = _pt.mark.skipif(_ilu.find_spec("engines.plan_sources") is None, reason="módulo Plans (plan_sources) só existe no .fr")


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


def _llm(responses):
    calls = []

    async def llm(system, text, images=None, model=None, max_tokens=0):
        calls.append({"text": text, "n_images": len(images or [])})
        return responses[min(len(calls) - 1, len(responses) - 1)]
    return llm, calls


async def _stub(system, text, images=None, model=None, max_tokens=0):
    return "{}"


# ------------------------------------------------------------------ détection d'intention (FR + PT)
def test_detection_true_fr_pt():
    phrases = [
        "je n'ai que ces plans, faites la meilleure solution",
        "faites au mieux avec ce que vous avez",
        "prenez la meilleure hypothèse, décidez vous-même",
        "faites à votre façon",
        "c'est tout ce que j'ai, débrouillez-vous",
        "ne me posez pas de questions, faites le dossier",
        "só tenho estes desenhos, faça o melhor",
        "faça com o que tem, decida sozinho",
        "não faça perguntas, faça à sua maneira",
    ]
    for p in phrases:
        assert asyncio.run(reader.intends_decide_alone(p, llm=_stub)) is True, p


def test_detection_false_when_precisions_or_question():
    phrases = [
        "",
        "les murs extérieurs sont en parpaing 20, planchers poutrelles-hourdis",
        "quelle est la meilleure solution pour les fondations ?",
        "le sous-sol fait 148 m², HSP 2,50 m",
        "qual a melhor solução para as fundações?",
    ]
    for p in phrases:
        assert asyncio.run(reader.intends_decide_alone(p, llm=_stub)) is False, p


# ------------------------------------------------------------------ lecture : décide seul = pas de questions, des décisions
def test_reader_decide_alone_suppresses_questions_and_lists_decisions():
    model = copy.deepcopy(CASE)
    model["_questions"] = ["La cote -2,80 est-elle le sol fini ou le fond de fouille ?"]
    model["_decisions"] = ["Cote sous-sol -2,80 = sol fini", "Escalier : quart tournant, emmarchement 0,90 m"]
    pdf = _pdf(["PLAN DU SOUS-SOL", "PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"])
    llm, _ = _llm([json.dumps(model)])
    res = asyncio.run(reader.read_building([("PC.pdf", pdf)], "je n'ai que ces plans", "FR", llm=llm, decide_alone=True))
    assert res["ok"] and res["questions"] == []
    assert res["decisions"] == model["_decisions"] and res["decide_alone"] is True


def test_reader_normal_mode_still_asks_questions():
    model = copy.deepcopy(CASE)
    model["_questions"] = ["La cote -2,80 est-elle le sol fini ou le fond de fouille ?"]
    pdf = _pdf(["PLAN DU SOUS-SOL", "PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"])
    llm, _ = _llm([json.dumps(model)])
    res = asyncio.run(reader.read_building([("PC.pdf", pdf)], "", "FR", llm=llm, decide_alone=False))
    assert res["ok"] and res["questions"] == model["_questions"]


def test_reader_decide_alone_never_returns_questions_even_if_unfixable():
    bad = copy.deepcopy(CASE)
    del bad["levels"]                        # relevé incomplet : bloquant, non réparable (le stub renvoie toujours le même)
    llm, _ = _llm([json.dumps(bad)])
    res = asyncio.run(reader.read_building([("PC.pdf", _pdf(["PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"]))], "faites au mieux", "FR", llm=llm, decide_alone=True))
    assert res["ok"] is False and res["questions"] == []


# ------------------------------------------------------------------ bout en bout : détection → étude complète → décisions
def _db():
    from tests.bet_core.test_assistant_tool import DB
    return DB()


@_NO_RE2020
def test_end_to_end_decide_alone_completes_with_decisions():
    db = _db()
    pdf = _pdf(["PLAN DU SOUS-SOL", "PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"])
    db.assistant_docs.docs.append({"doc_id": "doc_1", "user_id": "u1", "filename": "PC.pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(pdf).decode()})
    model = copy.deepcopy(CASE)
    model["_decisions"] = ["Cote sous-sol -2,80 = sol fini", "HSP RDC 2,50 m (non cotée, valeur courante)"]
    llm, _ = _llm([json.dumps(model)])
    user, conv = {"user_id": "u1"}, {"conversation_id": "c1", "_quote_request_id": "r1"}
    out = asyncio.run(assistant_tool.execute(
        "generate_full_bet_study",
        {"document_ids": ["doc_1"], "hypotheses": "je n'ai que ces documents, faites la meilleure solution", "country": "FR"},
        user, conv, db, llm=llm, background=False))
    assert out["ok"]
    job = asyncio.run(db.bet_study_jobs.find_one({"job_id": out["job_id"]}))
    assert job["decide_alone"] is True
    st = asyncio.run(assistant_tool.execute("read_full_bet_study", {"job_id": out["job_id"]}, user, conv, db))
    assert st["status"] == "done", st
    assert st["questions"] == [] and st["decisions"][:len(model["_decisions"])] == model["_decisions"]
    assert any("Étude thermique RE2020" in d for d in st["decisions"])          # étude thermique faite d'abord, tracée
    assert len(st["artifacts"]) == 5 and st["thermal"]["classe"]


def test_flag_is_inherited_on_relaunch_without_keyword():
    db = _db()
    pdf = _pdf(["PLAN DU SOUS-SOL", "PLAN DU REZ-DE-CHAUSSEE", "COUPE 1"])
    db.assistant_docs.docs.append({"doc_id": "doc_1", "user_id": "u1", "filename": "PC.pdf", "mime": "application/pdf",
                                   "data_b64": base64.b64encode(pdf).decode()})
    llm, _ = _llm([json.dumps(CASE)])
    user = {"user_id": "u1"}
    # 1er appel : l'utilisateur autorise à décider seul
    asyncio.run(assistant_tool.execute(
        "generate_full_bet_study", {"document_ids": ["doc_1"], "hypotheses": "faites au mieux", "country": "FR"},
        user, {"conversation_id": "c1", "_quote_request_id": "r1"}, db, llm=llm, background=False))
    # 2e appel, même conversation, hypothèse neutre : le drapeau est hérité → toujours décider seul
    out2 = asyncio.run(assistant_tool.execute(
        "generate_full_bet_study", {"document_ids": ["doc_1"], "hypotheses": "ok", "country": "FR"},
        user, {"conversation_id": "c1", "_quote_request_id": "r2"}, db, llm=llm, background=False))
    job2 = asyncio.run(db.bet_study_jobs.find_one({"job_id": out2["job_id"]}))
    assert job2["decide_alone"] is True
