"""Outils Assistant : étude BET complète (structure, plans d'exécution cotés, charpente, électricité, plomberie, devis).

generate_full_bet_study  → lance l'étude en tâche de fond (lecture IA des plans + moteurs déterministes).
read_full_bet_study      → lit l'état, les questions éventuelles et les liens des 3 livrables (PDF, DXF, XLSX).

Les livrables sont stockés dans db.assistant_artifacts (même format que engines/assistant_files.py) et
téléchargeables par /assistant/artifacts/{artifact_id}/content.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import pipeline, reader

log = logging.getLogger(__name__)
MAX_ARTIFACT = 15 * 1024 * 1024
STALE_MIN = 25          # un job « running » sans mise à jour depuis 25 min (redémarrage serveur) est déclaré échoué
_TASKS: set = set()     # références fortes : évite qu'asyncio ne ramasse une tâche de fond en cours

TOOLS = [
    {"type": "function", "name": "generate_full_bet_study", "strict": True,
     "description": ("ÉTUDE BET COMPLÈTE d'une maison individuelle à partir du PC / plans d'architecte (PDF joints) et de l'étude de sol : "
                     "note de calcul Eurocodes, plans d'exécution GROS ŒUVRE entièrement cotés (fondations, niveaux, planchers, coupes, "
                     "façades, détails ferraillés), charpente, électricité, plomberie, devis chiffré Excel et DXF. Lecture des plans par "
                     "IA puis calculs 100 % déterministes et contrôle automatique. Tâche de fond (3 à 8 min) : renvoie un job_id. "
                     "AVANT d'appeler : confirme avec l'utilisateur les documents à utiliser, le pays et ses hypothèses (planchers, murs). "
                     "Ne l'utilise pas pour un simple métré ou un devis de rénovation."),
     "parameters": {"type": "object", "properties": {
         "document_ids": {"type": "array", "items": {"type": "string"}, "description": "doc_… des PDF joints à la conversation (PC, plans, coupes, façades, étude de sol)"},
         "hypotheses": {"type": "string", "description": "Hypothèses du client (ex. « planchers poutrelles-hourdis, murs brique 20 »), vide sinon"},
         "country": {"type": "string", "enum": ["FR", "PT"]}},
         "required": ["document_ids", "hypotheses", "country"], "additionalProperties": False}},
    {"type": "function", "name": "read_full_bet_study", "strict": True,
     "description": "Lit l'état d'une étude BET lancée par generate_full_bet_study : avancement, questions bloquantes, statut du contrôle, liens des livrables.",
     "parameters": {"type": "object", "properties": {"job_id": {"type": "string"}}, "required": ["job_id"], "additionalProperties": False}},
]
TOOL_NAMES = {t["name"] for t in TOOLS}

INSTRUCTIONS = (
    "\n\nÉTUDE BET COMPLÈTE (generate_full_bet_study / read_full_bet_study) : quand l'utilisateur demande un dossier de bureau d'études "
    "(plans d'exécution, coupes, ferraillage, charpente, électricité, plomberie, devis) à partir d'un PC, propose le périmètre "
    "(documents, pays, hypothèses) et attends sa confirmation, puis lance generate_full_bet_study. Suis l'avancement avec "
    "read_full_bet_study. Si l'étude renvoie des QUESTIONS, pose-les telles quelles à l'utilisateur et relance après ses réponses "
    "(en les ajoutant aux hypothèses). Quand elle est terminée, donne les 3 liens (dossier PDF, plans DXF, devis Excel), le statut "
    "du contrôle et les points à valider ; rappelle que le dossier est un pré-dimensionnement à faire viser par un ingénieur structure. "
    "Ne recalcule et n'invente aucun chiffre : reprends ceux de l'outil."
)

MIME = {"pdf": "application/pdf", "zip": "application/zip",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _now():
    return datetime.now(timezone.utc).isoformat()


async def _store(db, uid, cid, request_id, kind, path: Path, title):
    data = path.read_bytes()
    if len(data) > MAX_ARTIFACT:
        raise ValueError(f"{path.name} trop volumineux ({len(data)} o)")
    aid = "file_" + hashlib.sha256((request_id + kind + path.name).encode()).hexdigest()[:28]
    doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": request_id, "title": title, "body": "",
           "filename": path.name, "format": kind, "mime": MIME[kind], "size": len(data), "data_b64": base64.b64encode(data).decode(),
           "source_artifact_ids": [], "created_at": _now(), "illustrative": False, "bet_study": True,
           "download": f"/assistant/artifacts/{aid}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {k: doc[k] for k in ("artifact_id", "title", "filename", "format", "mime", "size", "download")}


BRANDED_LEVELS = {"pro", "business"}      # offres Pro et Pro Business : dossier au logo ORIGINAL de l'entreprise


async def _plan_level(user: dict) -> str:
    try:
        from engines.access import compute_level
        return await compute_level(user)
    except Exception:  # noqa: BLE001 — plateforme sans engines.access (.pt) : type de compte
        at = user.get("account_type")
        return "business" if at in ("pro_business", "business") else "pro" if at == "pro" else "particulier_gratuit"


async def _default_branding(db, uid, user=None):
    """Identité de l'entreprise (logo original téléversé, nom, coordonnées, couleur) — réservée aux offres Pro / Pro Business.
    Pro Business : identité de l'organisation (partagée par l'équipe) ; Pro : identité du compte."""
    if user is not None and await _plan_level(user) not in BRANDED_LEVELS:
        return None
    b = None
    try:
        from routes.plans_common import _resolve_branding
        b = await _resolve_branding(uid)
    except Exception:  # noqa: BLE001 — plateforme sans ce résolveur : lecture directe plus bas
        b = None
    # Fallback brand_* sur le user doc si _resolve_branding est absent, échoue ou ne trouve rien
    # (cas .pt sans org, ou user absent de la plateforme principale mais présent dans la collection locale).
    if not b:
        try:
            u = await db.users.find_one({"user_id": uid}, {"_id": 0, "brand_company_name": 1, "brand_contact_line": 1, "brand_logo_b64": 1,
                                                         "brand_company_email": 1, "brand_siret": 1, "brand_vat": 1, "brand_nif": 1,
                                                         "brand_alvara": 1, "brand_address": 1, "brand_city": 1, "brand_postal": 1,
                                                         "brand_accent_color": 1, "brand_footer_text": 1}) or {}
            if u:
                b = {k[6:]: v for k, v in u.items() if k.startswith("brand_") and v is not None} or None
                if b and "postal" in b:
                    b["postal_code"] = b.pop("postal")
        except Exception:  # noqa: BLE001
            b = None
    try:
        from routes.company_page import pdf_customization
        extra = {k: v for k, v in (await pdf_customization(uid)).items() if v}
        if extra:
            b = {**(b or {}), **extra}
    except Exception:  # noqa: BLE001
        pass
    return b or None


async def _work(db, job_id, uid, cid, request_id, docs, hypotheses, country, llm=None, branding=None):
    async def step(label, **extra):
        await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"step": label, "updated_at": _now(), **extra}})
    try:
        await step("Lecture des plans par IA et relevé du modèle bâtiment")
        rd = await reader.read_building(docs, hypotheses, country, llm=llm)
        if not rd["ok"]:
            await step("Questions à l'utilisateur", status="questions", questions=rd["questions"], anomalies=rd["anomalies"],
                       model=rd["model"], pages=rd["pages"])
            return
        await step("Calculs, plans, devis et contrôle", model=rd["model"], pages=rd["pages"])
        with tempfile.TemporaryDirectory() as tmp:
            res = await asyncio.to_thread(pipeline.run, rd["model"], tmp, None, "pt" if country == "PT" else "fr", None, branding)
            if res["status"] == "MODELE_INVALIDE":
                await step("Questions à l'utilisateur", status="questions", anomalies=res["anomalies"],
                           questions=rd["questions"] + [f"{a['message']} — {a.get('fix') or 'à préciser'}"
                                                        for a in res["anomalies"] if a.get("level") == "bloquant"])
                return
            arts = []
            labels = {"pdf": "Dossier d'étude BET (note de calcul + plans)", "zip": "Plans DXF", "xlsx": "Devis et métré (Excel)"}
            if country == "PT":
                labels = {"pdf": "Processo de estudo (memória de cálculo + desenhos)", "zip": "Desenhos DXF", "xlsx": "Medições e orçamento (Excel)"}
            for kind in ("pdf", "zip", "xlsx"):
                arts.append(await _store(db, uid, cid, request_id, kind, Path(res["files"][kind]), labels[kind]))
        await step("Terminé", status="done", artifacts=arts, review_status=res["status"], blocking=res["blocking"],
                   sheets=res["sheets"], devis_ht=res["devis_ht"], devis_ttc=res["devis_ttc"],
                   points=[a["message"] for a in res["anomalies"]][:30] + [i["message"] for i in res["review"]][:30],
                   questions=rd["questions"])
    except Exception as exc:  # noqa: BLE001
        log.exception("bet study %s failed", job_id)
        await step("Échec", status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")


async def _load_assistant_docs(db, ids, uid):
    """Chargeur par défaut (construpilot.fr) : pièces jointes de l'Assistant dans db.assistant_docs."""
    docs = []
    for did in ids:
        d = await db.assistant_docs.find_one({"doc_id": did, "user_id": uid}, {"_id": 0, "filename": 1, "mime": 1, "data_b64": 1})
        if not d:
            raise PermissionError(f"Document {did} inaccessible pour ce compte")
        if (d.get("mime") or "") != "application/pdf":
            raise ValueError(f"{d.get('filename', did)} n'est pas un PDF : seuls les PDF de plans sont lus.")
        docs.append((d.get("filename") or did, base64.b64decode(d["data_b64"])))
    return docs


async def execute(name: str, args: dict, user: dict, conv: dict, db, llm=None, background: bool = True, doc_loader=None,
                  branding_loader=None) -> dict:
    """doc_loader(db, ids, user_id) -> [(nom, pdf_bytes)] : à fournir si les pièces jointes ne sont pas dans db.assistant_docs (ex. .pt).
    branding_loader(db, user_id) -> dict : identité de l'entreprise (défaut : résolveurs de la plateforme)."""
    uid, cid = user["user_id"], conv.get("conversation_id")
    if name == "read_full_bet_study":
        job = await db.bet_study_jobs.find_one({"job_id": args["job_id"], "user_id": uid}, {"_id": 0, "model": 0})
        if not job:
            return {"error": "Étude introuvable pour ce compte", "status": "échoué"}
        if job.get("status") == "running":
            age = datetime.now(timezone.utc) - datetime.fromisoformat(job["updated_at"])
            if age.total_seconds() > STALE_MIN * 60:
                msg = "interrompue (redémarrage du serveur) : relancez l'étude"
                await db.bet_study_jobs.update_one({"job_id": job["job_id"]}, {"$set": {"status": "failed", "error": msg}})
                job.update(status="failed", error=msg)
        return {"ok": True, **job, "note": "Pré-dimensionnement à faire viser par un ingénieur structure avant exécution."}
    ids = [d for d in args.get("document_ids") or [] if d]
    if not ids:
        return {"error": "Joignez le PC (PDF) et précisez les documents à utiliser.", "status": "échoué"}
    try:
        docs = await (doc_loader or _load_assistant_docs)(db, ids, uid)
    except (PermissionError, ValueError) as exc:
        return {"error": str(exc), "status": "échoué"}
    request_id = conv.get("_quote_request_id") or hashlib.sha256(("".join(ids) + _now()).encode()).hexdigest()[:16]
    job_id = "bet_" + hashlib.sha256((uid + request_id + "".join(ids)).encode()).hexdigest()[:20]
    old = await db.bet_study_jobs.find_one({"job_id": job_id, "user_id": uid}, {"_id": 0, "status": 1})
    if old and old.get("status") in {"running", "done", "questions"}:
        return {"ok": True, "job_id": job_id, "status": old["status"], "note": "Étude déjà lancée pour cette demande : utilise read_full_bet_study."}
    await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {
        "job_id": job_id, "user_id": uid, "conversation_id": cid, "document_ids": ids, "country": args["country"],
        "hypotheses": args.get("hypotheses", ""), "status": "running", "step": "En file d'attente", "created_at": _now(), "updated_at": _now()}}, upsert=True)
    try:
        branding = await branding_loader(db, uid) if branding_loader else await _default_branding(db, uid, user)
    except Exception:  # noqa: BLE001 — l'identité est facultative : dossier aux couleurs ConstruPilot
        branding = None
    coro = _work(db, job_id, uid, cid, request_id, docs, args.get("hypotheses", ""), args["country"], llm=llm, branding=branding)
    if background:
        task = asyncio.create_task(coro)
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)
    else:
        await coro
    return {"ok": True, "job_id": job_id, "status": "running",
            "note": "Étude lancée en tâche de fond (3 à 8 min). Suis l'avancement avec read_full_bet_study ; aucun résultat n'est encore disponible."}
