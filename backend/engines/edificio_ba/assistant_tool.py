"""Ferramentas do Assistente : estudo completo de um EDIFÍCIO MULTIFAMILIAR em betão armado (estrutura + 3D, desenhos, medições,
orçamento, quantidades, Excel e — em Portugal — térmica REH, pichelaria e eletricidade).

generate_multifamily_building_study → lança o estudo em tarefa de fundo (leitura IA das plantas + motores determinísticos).
read_multifamily_building_study     → estado, perguntas, decisões e livrables (descarregáveis por /assistant/artifacts/{id}/content).
Modo demo (demo = true) : caso de exemplo incluído, sem IA nem internet.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import json
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import leitura, pipeline

log = logging.getLogger(__name__)
MAX_ARTIFACT = 15 * 1024 * 1024
STALE_MIN = 30
_TASKS: set = set()
EXAMPLE = Path(__file__).with_name("casos") / "exemplo_pt.json"
MIME = {"pdf": "application/pdf", "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _lang() -> str:
    try:
        from engines.calc_lots import rendu
        return "pt" if rendu.LANG.get("note", "").startswith("Nota") else "fr"
    except Exception:  # noqa: BLE001
        return "pt"


LANG = _lang()


def _t(pt, fr):
    return pt if LANG == "pt" else fr


TOOLS = [
    {"type": "function", "name": "generate_multifamily_building_study", "strict": True,
     "description": _t(
         "ESTUDO COMPLETO DE UM EDIFÍCIO MULTIFAMILIAR em betão armado (cave opcional + pisos, núcleos de escada/elevador) a partir das plantas de "
         "arquitetura em PDF : estrutura (lajes, vigas e pilares gerados, sismo com proposta de paredes, modelo 3D OpenSees quando disponível, muros de "
         "cave, sapatas e ensoleiramentos), 6 desenhos A3, memória de cálculo, mapa de medições, orçamento, quadro de quantidades (paredes, sapatas, lajes, "
         "janelas), Excel com fórmulas e estudos de térmica (REH), pichelaria e eletricidade. Leitura das plantas por IA e cálculos determinísticos. "
         "Tarefa de fundo (3 a 10 min) : devolve um job_id. demo = true corre o caso de exemplo sem documentos (funciona sem internet). "
         "Para moradias usa generate_full_bet_study.",
         "ÉTUDE COMPLÈTE D'UN IMMEUBLE DE LOGEMENTS en béton armé (sous-sol optionnel + niveaux, noyaux d'escalier/ascenseur) à partir des plans "
         "d'architecte en PDF : structure (dalles, poutres et poteaux générés, séisme avec proposition de voiles, modèle 3D OpenSees si disponible, voiles "
         "enterrés, semelles et radiers), 6 plans A3, note de calcul, métré, estimation, quantitatifs (murs, semelles, dalles, fenêtres) et Excel à "
         "formules. Lecture des plans par IA, calculs déterministes. Tâche de fond (3 à 10 min) : renvoie un job_id. demo = true lance le cas exemple "
         "sans documents (fonctionne hors ligne). Pour une maison individuelle, utiliser generate_full_bet_study."),
     "parameters": {"type": "object", "properties": {
         "document_ids": {"type": "array", "items": {"type": "string"}, "description": _t("doc_… das plantas PDF anexadas (vazio se demo)",
                                                                                         "doc_… des plans PDF joints (vide si demo)")},
         "hypotheses": {"type": "string", "description": _t("Hipóteses do cliente, vazio se nenhuma", "Hypothèses du client, vide sinon")},
         "country": {"type": "string", "enum": ["PT", "FR"]},
         "demo": {"type": "boolean", "description": _t("true = caso de exemplo incluído (sem IA)", "true = cas exemple intégré (sans IA)")}},
         "required": ["document_ids", "hypotheses", "country", "demo"], "additionalProperties": False}},
    {"type": "function", "name": "read_multifamily_building_study", "strict": False,
     "description": _t("Lê o estado de um estudo lançado por generate_multifamily_building_study : avanço, perguntas, decisões, resumo e livrables.",
                       "Lit l'état d'une étude lancée par generate_multifamily_building_study : avancement, questions, décisions, synthèse et livrables."),
     "parameters": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": [], "additionalProperties": False}},
]
TOOL_NAMES = {t["name"] for t in TOOLS}
TOOL_STATUS = {"generate_multifamily_building_study": _t("A lançar o estudo do edifício multifamiliar…", "Lancement de l'étude de l'immeuble…"),
               "read_multifamily_building_study": _t("A ler o avanço do estudo do edifício…", "Lecture de l'avancement de l'étude de l'immeuble…")}
INSTRUCTIONS = _t(
    "\n\nEDIFÍCIO MULTIFAMILIAR (generate_multifamily_building_study / read_multifamily_building_study) : para um prédio de apartamentos "
    "(cave + vários pisos, núcleos de escada/elevador) a partir das plantas de arquitetura, confirma os documentos e as hipóteses e lança o estudo ; "
    "segue-o com read_multifamily_building_study. Se o estudo devolver PERGUNTAS, coloca-as tal como estão e relança com as respostas nas hipóteses. "
    "No fim, os livrables aparecem como botões de descarga : não escrevas links. Apresenta o resumo (betão, aço, custo, classes energéticas), as "
    "paredes PROPOSTAS (a compatibilizar com a arquitetura) e as decisões. Não recalcules nada. É um estudo prévio a validar pelo projetista.",
    "\n\nIMMEUBLE DE LOGEMENTS (generate_multifamily_building_study / read_multifamily_building_study) : pour un immeuble (sous-sol + plusieurs niveaux, "
    "noyaux d'escalier/ascenseur) à partir des plans d'architecte, confirme les documents et les hypothèses puis lance l'étude ; suis-la avec "
    "read_multifamily_building_study. Si l'étude renvoie des QUESTIONS, pose-les telles quelles et relance avec les réponses dans les hypothèses. "
    "À la fin, les livrables s'affichent en boutons de téléchargement : n'écris aucun lien. Présente la synthèse (béton, acier, coût), les voiles "
    "PROPOSÉS (à coordonner avec l'architecte) et les décisions. Ne recalcule rien. Étude préalable à faire viser par un BET structure.")

LABELS = {"memoria": _t("Memória de cálculo da estrutura", "Note de calcul structure"), "desenhos": _t("Desenhos de estrutura (A3)", "Plans de structure (A3)"),
          "medicoes": _t("Mapa de medições", "Métré"), "orcamento": _t("Orçamento estimativo", "Estimation"),
          "quantidades": _t("Quadro de quantidades", "Quantitatifs"), "xlsx": _t("Medições e orçamento (Excel)", "Métré et estimation (Excel)"),
          "termico": _t("Estudo térmico (REH)", "Étude thermique"), "pichelaria": _t("Estudo de pichelaria", "Étude plomberie"),
          "eletricidade": _t("Estudo de eletricidade", "Étude électricité")}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _age_s(ts) -> float:
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if not isinstance(ts, datetime):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def _jsonable(v):
    import math
    if isinstance(v, dict):
        return {str(k): _jsonable(x) for k, x in v.items() if k != "_id"}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, bool) or v is None or isinstance(v, (int, str)):
        return v
    try:
        fv = float(v)
        return fv if math.isfinite(fv) else None
    except (TypeError, ValueError):
        return str(v)


async def _store(db, uid, cid, request_id, kind, path: Path, title):
    fmt = "xlsx" if path.suffix == ".xlsx" else "pdf"
    data = path.read_bytes()
    if len(data) > MAX_ARTIFACT:
        raise ValueError(f"{path.name} : {len(data)} octets")
    aid = "file_" + hashlib.sha256((request_id + kind + path.name).encode()).hexdigest()[:28]
    doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": request_id, "title": title, "body": "",
           "filename": f"ConstruPilot_{path.name}", "format": fmt, "kind": kind, "mime": MIME[fmt], "size": len(data),
           "data_b64": base64.b64encode(data).decode(), "source_artifact_ids": [], "created_at": _now(), "illustrative": False,
           "bet_study": True, "download": f"/assistant/artifacts/{aid}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {k: doc[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")}


def run_demo(out_dir) -> dict:
    """Caso de exemplo (offline) : mesmo pipeline, sem IA."""
    raw = json.loads(EXAMPLE.read_text())
    return pipeline.run(raw, out_dir)


async def _work(db, job_id, uid, cid, request_id, docs, hypotheses, country, demo, llm=None, decide_alone=False):
    async def step(label, **extra):
        await db.edificio_jobs.update_one({"job_id": job_id}, {"$set": {"step": label, "updated_at": _now(), **extra}})
    try:
        if demo:
            raw = json.loads(EXAMPLE.read_text())
            rd = {"ok": True, "model": raw, "decisions": [_t("Caso de exemplo incluído (modo demo, sem leitura IA).", "Cas exemple intégré (mode démo, sans lecture IA).")],
                  "questions": [], "anomalies": [], "pages": []}
        else:
            await step(_t("Leitura das plantas por IA e levantamento do modelo", "Lecture des plans par IA et relevé du modèle"))
            rd = await leitura.read_building(docs, hypotheses, country, llm=llm, decide_alone=decide_alone)
        if not rd["ok"]:
            await step(_t("Perguntas ao utilizador", "Questions à l'utilisateur"), status="questions", questions=rd["questions"],
                       anomalies=_jsonable(rd["anomalies"]), decisions=rd.get("decisions"), model=rd.get("model"))
            return
        await step(_t("Cálculos, modelo 3D, desenhos, medições e orçamento", "Calculs, modèle 3D, plans, métré et estimation"), model=rd["model"])
        with tempfile.TemporaryDirectory() as tmp:
            res = await asyncio.to_thread(pipeline.run, copy.deepcopy(rd["model"]), tmp)
            if res["status"] == "MODELO_INVALIDO":
                await step(_t("Perguntas ao utilizador", "Questions à l'utilisateur"), status="questions", anomalies=_jsonable(res["anomalies"]),
                           questions=[f"{a['message']} — {a.get('fix') or ''}" for a in res["anomalies"] if a["level"] == "bloqueante"])
                return
            arts = []
            for kind, p in res["files"].items():
                arts.append(await _store(db, uid, cid, request_id, kind, Path(p), LABELS.get(kind, kind)))
        await step(_t("Concluído", "Terminé"), status="done", artifacts=arts, review_status=res["status"], summary=_jsonable(res["summary"]),
                   decisions=list(dict.fromkeys((rd.get("decisions") or []) + res["decisions"])),
                   points=[a["message"] for a in res["anomalies"]][:30], demo=bool(demo))
    except Exception as exc:  # noqa: BLE001
        log.exception("edificio study %s failed", job_id)
        await step(_t("Falhou", "Échec"), status="failed", error=f"{type(exc).__name__}: {str(exc)[:300]} — {pipeline.where(exc)}")


async def _read_job(db, uid, job_id, cid=None):
    q = {"user_id": uid}
    proj = {"_id": 0, "model": 0}
    job = await db.edificio_jobs.find_one({**q, "job_id": job_id}, proj) if job_id else None
    if not job and cid:
        job = await db.edificio_jobs.find_one({**q, "conversation_id": cid}, proj, sort=[("created_at", -1)])
    if not job:
        job = await db.edificio_jobs.find_one(q, proj, sort=[("created_at", -1)])
    if not job:
        return {"error": _t("Nenhum estudo encontrado : lança generate_multifamily_building_study.", "Aucune étude : lance generate_multifamily_building_study."),
                "status": "failed"}
    if job.get("status") == "running" and _age_s(job.get("updated_at") or job.get("created_at")) > STALE_MIN * 60:
        await db.edificio_jobs.update_one({"job_id": job["job_id"]}, {"$set": {"status": "failed", "error": "interrupted"}})
        job.update(status="failed", error=_t("interrompido (reinício do servidor) : relança o estudo", "interrompue (redémarrage) : relance l'étude"))
    return {"ok": True, **_jsonable(job), "note": _t("Estudo prévio a validar pelo projetista de estruturas.", "Étude préalable à faire viser par un BET structure.")}


async def execute(name: str, args: dict, user: dict, conv: dict, db, llm=None, background: bool = True, doc_loader=None) -> dict:
    uid, cid = user["user_id"], conv.get("conversation_id")
    if name == "read_multifamily_building_study":
        try:
            return await _read_job(db, uid, str(args.get("job_id") or ""), cid)
        except Exception as exc:  # noqa: BLE001
            log.exception("edificio read failed")
            return {"error": f"{type(exc).__name__}", "status": "failed"}
    demo = bool(args.get("demo"))
    ids = [d for d in args.get("document_ids") or [] if d]
    docs = []
    if not demo:
        if not ids:
            return {"error": _t("Junte as plantas de arquitetura (PDF) ou use demo = true.", "Joignez les plans d'architecte (PDF) ou utilisez demo = true."), "status": "failed"}
        try:
            if doc_loader is None:
                from engines.bet_core.assistant_tool import _load_assistant_docs as doc_loader
            docs = await doc_loader(db, ids, uid)
        except (PermissionError, ValueError) as exc:
            return {"error": str(exc), "status": "failed"}
    country = args.get("country") or ("PT" if LANG == "pt" else "FR")
    request_id = hashlib.sha256(("".join(ids) + (args.get("hypotheses") or "") + country + str(demo) + _now()).encode()).hexdigest()[:16]
    job_id = "edif_" + hashlib.sha256((uid + request_id).encode()).hexdigest()[:20]
    decide_alone = False
    try:
        from engines.bet_core import reader as BR
        if hasattr(BR, "intends_decide_alone"):
            decide_alone = await BR.intends_decide_alone(args.get("hypotheses") or "", llm=llm)
    except Exception:  # noqa: BLE001
        decide_alone = False
    await db.edificio_jobs.update_one({"job_id": job_id}, {"$set": {
        "job_id": job_id, "user_id": uid, "conversation_id": cid, "document_ids": ids, "country": country, "hypotheses": args.get("hypotheses", ""),
        "demo": demo, "status": "running", "step": _t("Em fila", "En file d'attente"), "created_at": _now(), "updated_at": _now()}}, upsert=True)
    coro = _work(db, job_id, uid, cid, request_id, docs, args.get("hypotheses", ""), country, demo, llm=llm, decide_alone=decide_alone)
    if background:
        task = asyncio.create_task(coro)
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)
    else:
        await coro
    return {"ok": True, "job_id": job_id, "status": "running",
            "note": _t("Estudo lançado em tarefa de fundo (3 a 10 min) : segue com read_multifamily_building_study.",
                       "Étude lancée en tâche de fond (3 à 10 min) : suis-la avec read_multifamily_building_study.")}
