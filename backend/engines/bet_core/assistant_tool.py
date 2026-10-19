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
    "(en les ajoutant aux hypothèses). Quand elle est terminée, les 3 livrables (dossier PDF, plans DXF, devis Excel) s'affichent AUTOMATIQUEMENT "
    "sous forme de boutons de téléchargement sous ta réponse : n'écris JAMAIS de lien, d'URL ni de chemin (/assistant/…, /agents?run=…) "
    "dans le texte — dis seulement « les 3 fichiers sont téléchargeables ci-dessous ». Donne le statut du contrôle et les points à valider ; rappelle que le dossier est un pré-dimensionnement à faire viser par un ingénieur structure. "
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
    except Exception:  # noqa: BLE001 — plateforme sans ce résolveur (.pt) : lecture directe
        b = None
    if not b:
        u = await db.users.find_one({"user_id": uid}, {"_id": 0, "brand_company_name": 1, "brand_contact_line": 1, "brand_logo_b64": 1,
                                                     "brand_company_email": 1, "brand_siret": 1, "brand_vat": 1, "brand_nif": 1,
                                                     "brand_alvara": 1, "brand_address": 1, "brand_city": 1, "brand_postal": 1,
                                                     "brand_accent_color": 1, "brand_footer_text": 1}) or {}
        b = {k[6:]: v for k, v in u.items() if k.startswith("brand_")} if u else None
        if b:
            b["postal_code"] = b.pop("postal", None)
    try:
        from routes.company_page import pdf_customization
        b = {**(b or {}), **{k: v for k, v in ((await pdf_customization(uid)) or {}).items() if v}}
    except Exception:  # noqa: BLE001
        pass
    return b or None


def docs_hash(docs, hypotheses, country) -> str:
    """Empreinte des documents + hypothèses : mêmes pièces → même relevé → mêmes résultats (stabilité d'une étude à l'autre)."""
    h = hashlib.sha256()
    for d in sorted(hashlib.sha256(data).hexdigest() for _, data in docs):
        h.update(d.encode())
    h.update(" ".join((hypotheses or "").lower().split()).encode())
    h.update((country or "").encode())
    return h.hexdigest()


async def _cached_model(db, uid, key):
    try:
        return await db.bet_models.find_one({"user_id": uid, "docs_hash": key}, {"_id": 0})
    except Exception:  # noqa: BLE001 — cache facultatif
        return None


async def _work(db, job_id, uid, cid, request_id, docs, hypotheses, country, llm=None, branding=None):
    async def step(label, **extra):
        await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"step": label, "updated_at": _now(), **extra}})
    try:
        key = docs_hash(docs, hypotheses, country)
        cached = await _cached_model(db, uid, key)
        if cached and cached.get("model"):
            await step("Relevé déjà validé pour ces documents : réutilisé (résultats identiques)")
            rd = {"ok": True, "model": cached["model"], "anomalies": [], "pages": cached.get("pages") or [], "attempts": 0,
                  "questions": [], "cached": True}
        else:
            await step("Lecture des plans par IA et relevé du modèle bâtiment")
            rd = await reader.read_building(docs, hypotheses, country, llm=llm)
            if rd["ok"] and not rd.get("demo"):
                try:
                    await db.bet_models.update_one({"user_id": uid, "docs_hash": key}, {"$set": {
                        "user_id": uid, "docs_hash": key, "model": rd["model"], "pages": rd["pages"], "created_at": _now()}}, upsert=True)
                except Exception:  # noqa: BLE001
                    log.warning("bet model cache write failed", exc_info=True)
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
                   questions=rd["questions"], demo=rd.get("demo"), cached=bool(rd.get("cached")), provider=rd.get("provider"))
    except Exception as exc:  # noqa: BLE001
        log.exception("bet study %s failed", job_id)
        await step("Échec", status="failed", error=f"{type(exc).__name__}: {str(exc)[:500]}")


async def _load_assistant_docs(db, ids, uid):
    """Chargeur par défaut : pièces jointes de l'Assistant dans db.assistant_docs (inline `data_b64`, ou découpées en
    morceaux de 1 Mo dans db.assistant_doc_chunks pour les PDF de plus de 8 Mo — cas des PC et des G2 volumineux)."""
    docs = []
    for did in ids:
        d = await db.assistant_docs.find_one({"doc_id": did, "user_id": uid}, {"_id": 0, "filename": 1, "mime": 1, "data_b64": 1, "chunk_count": 1})
        if not d:
            raise PermissionError(f"Document {did} inaccessible pour ce compte")
        name = d.get("filename") or did
        if (d.get("mime") or "") != "application/pdf" and not name.lower().endswith(".pdf"):
            raise ValueError(f"{name} n'est pas un PDF : seuls les PDF de plans et d'études de sol sont lus.")
        if d.get("data_b64"):
            data = base64.b64decode(d["data_b64"])
        elif d.get("chunk_count"):
            chunks = [c async for c in db.assistant_doc_chunks.find({"doc_id": did, "user_id": uid}, {"_id": 0}).sort("index", 1)]
            if [c.get("index") for c in chunks] != list(range(d["chunk_count"])):
                raise ValueError(f"{name} est incomplet sur le serveur : réimportez le fichier.")
            data = b"".join(base64.b64decode(c["data_b64"]) for c in chunks)
        else:
            raise ValueError(f"{name} est vide sur le serveur : réimportez le fichier.")
        if not data.startswith(b"%PDF"):
            raise ValueError(f"{name} n'est pas un PDF lisible : réimportez-le.")
        docs.append((name, data))
    seen, uniq = set(), []                    # même pièce jointe deux fois (doublons dans la conversation) → une seule
    for name, data in docs:
        h = hashlib.sha256(data).hexdigest()
        if h not in seen:
            seen.add(h)
            uniq.append((name, data))
    return uniq


def _age_s(ts) -> float:
    """Âge en secondes d'un horodatage (chaîne ISO ou datetime, avec ou sans fuseau)."""
    if isinstance(ts, str):
        ts = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    if not isinstance(ts, datetime):
        return 0.0
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - ts).total_seconds()


def _jsonable(v):
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items() if k != "_id"}
    if isinstance(v, (list, tuple)):
        return [_jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)) or v is None:
        return v
    return str(v)                          # datetime, ObjectId… → texte


async def _read_job(db, uid, job_id):
    if not job_id:
        return {"error": "job_id manquant : relancez generate_full_bet_study.", "status": "échoué"}
    job = await db.bet_study_jobs.find_one({"job_id": job_id, "user_id": uid}, {"_id": 0, "model": 0, "pages": 0})
    if not job:
        return {"error": "Étude introuvable pour ce compte (identifiant inconnu ou étude d'un autre compte)", "status": "échoué"}
    if job.get("status") == "running" and _age_s(job.get("updated_at") or job.get("created_at")) > STALE_MIN * 60:
        msg = "interrompue (redémarrage du serveur) : relancez l'étude"
        await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"status": "failed", "error": msg}})
        job.update(status="failed", error=msg)
    out = _jsonable(job)
    for k in ("points", "questions", "sheets"):
        if isinstance(out.get(k), list):
            out[k] = out[k][:40]
    out.pop("anomalies", None) if out.get("status") == "done" else None
    return {"ok": True, **out, "note": "Pré-dimensionnement à faire viser par un ingénieur structure avant exécution."}


async def execute(name: str, args: dict, user: dict, conv: dict, db, llm=None, background: bool = True, doc_loader=None,
                  branding_loader=None) -> dict:
    """doc_loader(db, ids, user_id) -> [(nom, pdf_bytes)] : à fournir si les pièces jointes ne sont pas dans db.assistant_docs (ex. .pt).
    branding_loader(db, user_id) -> dict : identité de l'entreprise (défaut : résolveurs de la plateforme)."""
    uid, cid = user["user_id"], conv.get("conversation_id")
    if name == "read_full_bet_study":
        try:
            return await _read_job(db, uid, str(args.get("job_id") or ""))
        except Exception as exc:  # noqa: BLE001 — jamais d'erreur muette
            log.exception("bet study read failed")
            return {"error": f"Lecture de l'étude impossible ({type(exc).__name__}) : relancez generate_full_bet_study.", "status": "échoué"}
    ids = [d for d in args.get("document_ids") or [] if d]
    if not ids:
        return {"error": "Joignez le PC (PDF) et précisez les documents à utiliser.", "status": "échoué"}
    try:
        docs = await (doc_loader or _load_assistant_docs)(db, ids, uid)
    except (PermissionError, ValueError) as exc:
        return {"error": str(exc), "status": "échoué"}
    except Exception as exc:  # noqa: BLE001 — jamais d'erreur muette : on dit quoi faire
        log.exception("bet study: lecture des pièces jointes impossible")
        return {"error": f"Lecture des pièces jointes impossible ({type(exc).__name__}) : réimportez le PC et la G2 en PDF.", "status": "échoué"}
    request_id = conv.get("_quote_request_id") or hashlib.sha256(("".join(ids) + _now()).encode()).hexdigest()[:16]
    hyp = " ".join((args.get("hypotheses") or "").lower().split())
    job_id = "bet_" + hashlib.sha256((uid + request_id + "".join(sorted(set(ids))) + hyp + args["country"]).encode()).hexdigest()[:20]
    old = await db.bet_study_jobs.find_one({"job_id": job_id, "user_id": uid}, {"_id": 0, "status": 1, "updated_at": 1})
    if old and old.get("status") == "running" and _age_s(old.get("updated_at")) > STALE_MIN * 60:
        old = None                                          # tâche tuée par un redémarrage : on relance
    if old and old.get("status") in {"running", "done"}:     # après des QUESTIONS, une relance (hypothèses complétées) repart
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
