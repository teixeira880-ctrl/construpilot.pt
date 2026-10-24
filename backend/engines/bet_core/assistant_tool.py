"""Outils Assistant : étude BET complète (structure, plans d'exécution cotés, charpente, électricité, plomberie, devis).

generate_full_bet_study  → lance l'étude en tâche de fond (lecture IA des plans + moteurs déterministes).
read_full_bet_study      → lit l'état, les questions éventuelles et les liens des 4 livrables (dossier PDF, Plans PDF, DXF, XLSX).

Les livrables sont stockés dans db.assistant_artifacts (même format que engines/assistant_files.py) et
téléchargeables par /assistant/artifacts/{artifact_id}/content.
"""
from __future__ import annotations

import asyncio
import base64
import copy
import hashlib
import logging
import math
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
    {"type": "function", "name": "read_full_bet_study", "strict": False,
     "description": "Lit l'état d'une étude BET lancée par generate_full_bet_study : avancement, questions bloquantes, statut du contrôle, liens des livrables. Passe le job_id renvoyé par generate_full_bet_study ; à défaut, lit la dernière étude de la conversation.",
     "parameters": {"type": "object", "properties": {"job_id": {"type": "string", "description": "Identifiant renvoyé par generate_full_bet_study"}, "plan_id": {"type": "string", "description": "Ignoré : utilise job_id. Toléré pour compatibilité."}}, "required": [], "additionalProperties": False}},
]
TOOLS.append(
    {"type": "function", "name": "generate_bet_lot_plans", "strict": True,
     "description": ("PLANS ET SCHÉMAS D'EXÉCUTION D'UN LOT, au format bureau d'études (PDF A3 cotés, cartouche), depuis le modèle bâtiment de "
                     "la dernière étude BET de la conversation : électricité (circuits numérotés tirés depuis la GTL, points cotés, schéma "
                     "unifilaire), plomberie (appareils et attentes cotés, EF/ECS, évacuations avec pentes, chutes, réservations), ventilation "
                     "(VMC simple/double flux : bouches, débits, conduits, caisson, schéma), chauffage (plancher chauffant/rafraîchissant : "
                     "boucles au pas, collecteurs cotés, schéma hydraulique PAC, coupe-type, déperditions), coupes, gros œuvre, schémas de principe. "
                     "Quelques secondes. À utiliser pour TOUTE demande de plan, schéma ou passage de gaines de ces lots quand une étude BET existe : "
                     "ne rédige pas de document texte et n'utilise pas draw_section_schema à la place."),
     "parameters": {"type": "object", "properties": {
         "lots": {"type": "array", "minItems": 1, "items": {"type": "string", "enum": ["electricite", "plomberie", "ventilation", "chauffage",
                                                                                    "coupes", "gros_oeuvre", "schemas"]}},
         "hypotheses": {"type": "string", "description": "Précisions du client pour ces lots (ex. « PAC réversible, plancher chauffant, VMC double flux, isolation 160 mm »), vide sinon"},
         "job_id": {"type": "string", "description": "Étude à utiliser ; vide = dernière étude de la conversation"}},
         "required": ["lots", "hypotheses", "job_id"], "additionalProperties": False}})
TOOL_NAMES = {t["name"] for t in TOOLS}

INSTRUCTIONS = (
    "\n\nÉTUDE BET COMPLÈTE (generate_full_bet_study / read_full_bet_study) : quand l'utilisateur demande un dossier de bureau d'études "
    "(plans d'exécution, coupes, ferraillage, charpente, électricité, plomberie, devis) à partir d'un PC, propose le périmètre "
    "(documents, pays, hypothèses) et attends sa confirmation, puis lance generate_full_bet_study. Suis l'avancement avec "
    "read_full_bet_study. Si l'étude renvoie des QUESTIONS, pose-les telles quelles à l'utilisateur et relance après ses réponses "
    "(en les ajoutant aux hypothèses). "
    "MODE « DÉCIDER SEUL » : si l'utilisateur demande de faire avec les documents fournis, de prendre la meilleure solution, de "
    "décider à ta place ou à ta façon (« je n'ai que ces plans », « faites au mieux », « prenez la meilleure solution »…), l'étude "
    "ne pose PLUS de questions : elle tranche seule et renvoie un champ `decisions`. Dans ce cas, NE REPOSE AUCUNE question : "
    "présente le dossier terminé, puis liste brièvement les décisions prises, UNE LIGNE chacune telle quelle, sous le titre "
    "« Décisions prises (modifiables) », et invite l'utilisateur à corriger un point s'il le souhaite. Quand l'utilisateur corrige "
    "ensuite une décision (ou que tu relances un calcul), ajoute sa correction aux hypothèses, relance l'étude et n'affiche QUE ce "
    "qui change, au format « Modifié : X → Y ; impacts : … » — sans reposer les questions ni réafficher tout le dossier. "
    "ÉTUDE THERMIQUE D'ABORD : en France, si l'utilisateur ne joint pas d'étude thermique, l'étude BET exécute AUTOMATIQUEMENT la "
    "pré-étude RE2020 avant les plans (isolant au plus juste qui passe Bbio / Cep / Cep,nr / Ic énergie / DH, puis épaisseur des "
    "murs reportée dans les plans et le devis) ; ne lance donc PAS etude_re2020 séparément avant generate_full_bet_study, et ne "
    "demande pas l'épaisseur des murs ni l'isolant : présente ensuite le champ `thermal` (classe, Bbio, Cep,nr, épaisseur des murs, "
    "isolants) et la note RE2020 livrée avec le dossier. Une étude de sol d'un autre terrain donnée « comme exemple » s'utilise "
    "telle quelle (décision tracée). "
    "Quand l'étude est terminée, les livrables (dossier PDF, Plans PDF, plans DXF, devis Excel et, en France, l'étude thermique RE2020) s'affichent "
    "AUTOMATIQUEMENT sous forme de boutons de téléchargement sous ta réponse : n'écris JAMAIS de lien, d'URL ni de chemin "
    "(/assistant/…, /agents?run=…) dans le texte — dis seulement « les 3 fichiers sont téléchargeables ci-dessous ». Donne le statut "
    "du contrôle et les points à valider ; rappelle que le dossier est un pré-dimensionnement à faire viser par un ingénieur structure. "
    "Ne recalcule et n'invente aucun chiffre : reprends ceux de l'outil. "
    "PLANS DE LOTS (generate_bet_lot_plans) : dès qu'une étude BET existe dans la conversation et que l'utilisateur demande un plan, "
    "un schéma ou les passages de gaines en électricité, plomberie, VMC, chauffage / plancher chauffant / PAC, des coupes ou des "
    "schémas de principe, appelle generate_bet_lot_plans avec les lots demandés (schemas = schémas de principe) et ses précisions "
    "dans `hypotheses` : le PDF s'affiche en bouton de téléchargement. Ne produis PAS de document texte ou de dessin approximatif "
    "à la place. Sans étude BET, propose d'abord generate_full_bet_study (le PC est nécessaire)."
)

MIME = {"pdf": "application/pdf", "zip": "application/zip",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"}


def _now():
    return datetime.now(timezone.utc).isoformat()


_BET_PREFIXES = ("Dossier_etude", "Plans_DXF", "Devis_metre", "Plans_PDF",
                 "Processo_estudo", "Desenhos_DXF", "Medicoes_orcamento", "Desenhos_PDF")


def _nom_livrable(path: Path) -> str:
    """« Dossier_etude_Maison-Dupont.pdf » → « ConstruPilot_Dossier-etude_Maison-Dupont_<date>.pdf »."""
    from engines.nom_fichier import nom_document
    stem, ext = path.stem, path.suffix.lstrip(".")
    for prefix in _BET_PREFIXES:
        if stem.startswith(prefix + "_"):
            return nom_document(prefix.replace("_", "-"), stem[len(prefix) + 1:], ext=ext)
    return nom_document("Estudo-engenharia", stem, ext=ext)


async def _store(db, uid, cid, request_id, kind, path: Path, title):
    fmt = "pdf" if kind in ("plans_pdf", "re2020_pdf") else kind
    data = path.read_bytes()
    if len(data) > MAX_ARTIFACT:
        raise ValueError(f"{path.name} trop volumineux ({len(data)} o)")
    aid = "file_" + hashlib.sha256((request_id + kind + path.name).encode()).hexdigest()[:28]
    doc = {"artifact_id": aid, "user_id": uid, "conversation_id": cid, "request_id": request_id, "title": title, "body": "",
           "filename": _nom_livrable(path), "format": fmt, "kind": kind, "mime": MIME[fmt], "size": len(data), "data_b64": base64.b64encode(data).decode(),
           "source_artifact_ids": [], "created_at": _now(), "illustrative": False, "bet_study": True,
           "download": f"/assistant/artifacts/{aid}/content"}
    await db.assistant_artifacts.update_one({"artifact_id": aid, "user_id": uid}, {"$setOnInsert": doc}, upsert=True)
    return {k: doc[k] for k in ("artifact_id", "title", "filename", "format", "kind", "mime", "size", "download")}


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


def docs_hash(docs, hypotheses, country, decide_alone=False) -> str:
    """Empreinte des documents + hypothèses : mêmes pièces → même relevé → mêmes résultats (stabilité d'une étude à l'autre)."""
    h = hashlib.sha256()
    for d in sorted(hashlib.sha256(data).hexdigest() for _, data in docs):
        h.update(d.encode())
    h.update(" ".join((hypotheses or "").lower().split()).encode())
    h.update((country or "").encode())
    h.update(b"decide_alone" if decide_alone else b"ask")
    return h.hexdigest()


async def _cached_model(db, uid, key):
    try:
        return await db.bet_models.find_one({"user_id": uid, "docs_hash": key}, {"_id": 0})
    except Exception:  # noqa: BLE001 — cache facultatif
        return None


async def _work(db, job_id, uid, cid, request_id, docs, hypotheses, country, llm=None, branding=None, decide_alone=False):
    async def step(label, **extra):
        await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"step": label, "updated_at": _now(), **extra}})
    try:
        key = docs_hash(docs, hypotheses, country, decide_alone)
        cached = await _cached_model(db, uid, key)
        if cached and cached.get("model"):
            await step("Relevé déjà validé pour ces documents : réutilisé (résultats identiques)")
            rd = {"ok": True, "model": cached["model"], "anomalies": [], "pages": cached.get("pages") or [], "attempts": 0,
                  "questions": [], "decisions": [str(d) for d in (cached["model"].get("_decisions") or [])], "cached": True}
        else:
            await step("Lecture des plans par IA et relevé du modèle bâtiment")
            rd = await reader.read_building(docs, hypotheses, country, llm=llm, decide_alone=decide_alone)
            if rd["ok"] and not rd.get("demo"):
                try:
                    await db.bet_models.update_one({"user_id": uid, "docs_hash": key}, {"$set": {
                        "user_id": uid, "docs_hash": key, "model": rd["model"], "pages": rd["pages"], "created_at": _now()}}, upsert=True)
                except Exception:  # noqa: BLE001
                    log.warning("bet model cache write failed", exc_info=True)
        decisions = [str(d) for d in (rd.get("decisions") or [])]
        from . import schema as _schema
        extraction = rd.get("extraction") or _schema.extraction_metrics(rd.get("model") or {})
        if extraction.get("hyp_total"):
            log.info("bet extraction quality: job=%s absent=%d/%d (%.0f%%) fields=%s", job_id,
                     extraction["hyp_absent"], extraction["hyp_total"], extraction["absent_rate"] * 100, extraction["absent_fields"])
        await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"extraction": extraction}})
        if not rd["ok"] and decide_alone and not rd.get("questions"):     # « décide seul » sans question possible : échec explicite, pas de boucle
            blocking = [a for a in rd.get("anomalies") or [] if a.get("level") == "bloquant"]
            msg = ("Relevé impossible à compléter, même en tranchant seul : "
                   + " ; ".join(f"{a['message']} ({a.get('fix') or 'à préciser'})" for a in blocking[:3])
                   + ". Ne relance pas l'étude à l'identique : il faut un document ou une donnée en plus.")
            await step("Échec", status="failed", error=msg[:1200], anomalies=rd.get("anomalies"), decisions=decisions,
                       decide_alone=decide_alone, extraction=extraction, provider=rd.get("provider"))
            return
        if not rd["ok"]:
            await step("Questions à l'utilisateur", status="questions", questions=rd["questions"], anomalies=rd["anomalies"],
                       decisions=decisions, decide_alone=decide_alone, extraction=extraction, model=rd["model"], pages=rd["pages"], provider=rd.get("provider"))
            return
        await step("Calculs, plans, devis et contrôle", model=rd["model"], pages=rd["pages"])
        with tempfile.TemporaryDirectory() as tmp:
            raw = copy.deepcopy(rd["model"])
            raw["user_hypotheses"] = dict(raw.get("user_hypotheses") or {}, _text=(hypotheses or "")[:2000])   # choix du client (PAC, plancher chauffant, VMC, isolation…)
            res = await asyncio.to_thread(pipeline.run, raw, tmp, None, "pt" if country == "PT" else "fr", None, branding)
            if res["status"] == "MODELE_INVALIDE":
                try:                                    # relevé en cache qui ne passe pas les calculs : on l'oublie, sinon chaque relance rejoue l'échec
                    await db.bet_models.delete_one({"user_id": uid, "docs_hash": key})
                except Exception:  # noqa: BLE001
                    log.warning("bet model cache delete failed", exc_info=True)
                blocking = [a for a in res["anomalies"] if a.get("level") == "bloquant"]
                if decide_alone:                        # « décide seul » : pas de question possible → échec explicite, pas de relance en boucle
                    msg = ("Étude impossible sur ces documents, même en tranchant seul : "
                           + " ; ".join(f"{a['message']} ({a.get('fix') or 'à préciser'})" for a in blocking[:3])
                           + ". Ne relance pas l'étude à l'identique : il faut un document ou une donnée en plus.")
                    await step("Échec", status="failed", error=msg[:1200], anomalies=res["anomalies"], decisions=decisions,
                               decide_alone=decide_alone, provider=rd.get("provider"))
                    return
                qs = [] if decide_alone else (rd["questions"] + [f"{a['message']} — {a.get('fix') or 'à préciser'}"
                                                                 for a in res["anomalies"] if a.get("level") == "bloquant"])
                await step("Questions à l'utilisateur", status="questions", anomalies=res["anomalies"], provider=rd.get("provider"),
                           decisions=decisions, decide_alone=decide_alone, questions=qs)
                return
            decisions = list(dict.fromkeys(decisions + [str(d) for d in (raw.get("_decisions") or [])]))   # + complétion et étude thermique
            arts = []
            labels = {"pdf": "Dossier d'étude BET (note de calcul + plans)", "plans_pdf": "Plans PDF (pour les entreprises)",
                      "xlsx": "Devis et métré (Excel)", "zip": "Plans DXF (pour logiciel de DAO)"}
            if country == "PT":
                labels = {"pdf": "Processo de estudo (memória de cálculo + desenhos)", "plans_pdf": "Desenhos PDF (para as empresas)",
                          "xlsx": "Medições e orçamento (Excel)", "zip": "Desenhos DXF (para software CAD)"}
            labels["re2020_pdf"] = "Étude thermique RE2020 (pré-étude, faite avant les plans)" if country != "PT" else "Estudo térmico"
            for kind in ("pdf", "plans_pdf", "xlsx", "zip", "re2020_pdf"):
                if res["files"].get(kind):
                    arts.append(await _store(db, uid, cid, request_id, kind, Path(res["files"][kind]), labels[kind]))
        await step("Terminé", status="done", artifacts=arts, review_status=res["status"], blocking=res["blocking"],
                   sheets=res["sheets"], devis_ht=res["devis_ht"], devis_ttc=res["devis_ttc"], decisions=decisions, decide_alone=decide_alone,
                   extraction=extraction,
                   points=[a["message"] for a in res["anomalies"]][:30] + [i["message"] for i in res["review"]][:30],
                   questions=rd["questions"], demo=rd.get("demo"), cached=bool(rd.get("cached")), provider=rd.get("provider"),
                   thermal={k: v for k, v in (res.get("thermal") or {}).items() if k not in ("tried", "systems")} or None)
    except Exception as exc:  # noqa: BLE001
        log.exception("bet study %s failed", job_id)
        txt = str(exc).lower()
        if any(s in txt for s in ("credit balance", "insufficient_quota", "quota", "rate limit", "overloaded", "authentication", "invalid x-api-key", "401", "403")):
            msg = "Leitura das plantas por IA temporariamente indisponível (serviço de cálculo saturado ou indisponível). Tente novamente dentro de alguns minutos."
        else:
            msg = f"{type(exc).__name__}: {str(exc)[:300]} — em {pipeline.where(exc)}"
        import traceback
        await step("Échec", status="failed", error=msg, trace=traceback.format_exc()[-3000:])
        try:
            from engines.reliability import alert_bet_failed
            await alert_bet_failed(db, job_id, msg)
        except Exception:  # noqa: BLE001
            log.warning("bet failure alert skipped", exc_info=True)


async def _plan_as_doc(db, plan_id, uid):
    """Plan du module Plans (db.plans_takeoff + source privée db.plan_sources) présenté comme une pièce jointe PDF."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": uid}, {"_id": 0, "filename": 1, "cad_import": 1})
    if not p:
        return None
    name = (p.get("cad_import") or {}).get("original_filename") or p.get("filename") or plan_id
    try:
        from engines.plan_sources import load_plan_source
    except ImportError:       # plataforma sem módulo Plans (.pt) : o plano tem de ser junto como anexo PDF
        raise ValueError(f"{name} : junte o PDF do plano como anexo da conversa.") from None
    src = await load_plan_source(db, plan_id, uid)
    if not src or not src.get("data_b64"):
        raise ValueError(f"{name} n'a pas de PDF source sur le serveur : réimportez le plan.")
    if not name.lower().endswith(".pdf"):
        name = name.rsplit(".", 1)[0] + ".pdf"
    return {"filename": name, "mime": "application/pdf", "data_b64": src["data_b64"]}


async def _load_assistant_docs(db, ids, uid):
    """Chargeur par défaut : pièces jointes de l'Assistant dans db.assistant_docs (inline `data_b64`, ou découpées en
    morceaux de 1 Mo dans db.assistant_doc_chunks pour les PDF de plus de 8 Mo — cas des PC et des G2 volumineux)."""
    docs = []
    for did in ids:
        d = await db.assistant_docs.find_one({"doc_id": did, "user_id": uid}, {"_id": 0, "filename": 1, "mime": 1, "data_b64": 1, "chunk_count": 1})
        if not d and str(did).startswith("plan_"):     # PDF importé dans le module Plans (plan_…) puis joint à l'Assistant
            d = await _plan_as_doc(db, did, uid)
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
    if isinstance(v, float):
        return v if math.isfinite(v) else None   # NaN/Infinity → None (json.dumps allow_nan=False côté wrapper)
    if isinstance(v, bool) or isinstance(v, int) or isinstance(v, str) or v is None:
        return v
    return str(v)                          # datetime, ObjectId… → texte


async def _read_job(db, uid, job_id, cid=None):
    if job_id:
        job = await db.bet_study_jobs.find_one({"job_id": job_id, "user_id": uid}, {"_id": 0, "model": 0, "pages": 0})
    else:
        job = None
        if cid:
            job = await db.bet_study_jobs.find_one({"user_id": uid, "conversation_id": cid}, {"_id": 0, "model": 0, "pages": 0}, sort=[("created_at", -1)])
        if not job:
            job = await db.bet_study_jobs.find_one({"user_id": uid}, {"_id": 0, "model": 0, "pages": 0}, sort=[("created_at", -1)])
    if not job:
        return {"error": "Nenhum estudo encontrado para esta conta: execute primeiro generate_full_bet_study.", "status": "échoué"}
    job_id = job.get("job_id") or job_id
    if job.get("status") == "running" and _age_s(job.get("updated_at") or job.get("created_at")) > STALE_MIN * 60:
        msg = "interrompido (reinício do servidor): volte a lançar o estudo"
        await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {"status": "failed", "error": msg}})
        job.update(status="failed", error=msg)
    out = _jsonable(job)
    for k in ("points", "questions", "sheets", "decisions"):
        if isinstance(out.get(k), list):
            out[k] = out[k][:40]
    out.pop("anomalies", None) if out.get("status") == "done" else None
    return {"ok": True, **out, "note": "Pré-dimensionnement à faire viser par un ingénieur structure avant exécution."}


LOT_LABEL = {"electricite": "Électricité", "plomberie": "Plomberie", "ventilation": "Ventilation", "chauffage": "Chauffage",
             "coupes": "Coupes", "gros_oeuvre": "Gros œuvre", "schemas": "Schémas de principe"}


async def _lot_plans(db, user: dict, conv: dict, args: dict, branding_loader=None) -> dict:
    uid, cid = user["user_id"], conv.get("conversation_id")
    q = {"user_id": uid, "model": {"$ne": None}}
    job = None
    if args.get("job_id"):
        job = await db.bet_study_jobs.find_one({**q, "job_id": args["job_id"]}, {"_id": 0, "pages": 0})
    if not job and cid:
        job = await db.bet_study_jobs.find_one({**q, "conversation_id": cid}, {"_id": 0, "pages": 0}, sort=[("created_at", -1)])
    if not job:
        job = await db.bet_study_jobs.find_one(q, {"_id": 0, "pages": 0}, sort=[("created_at", -1)])
    if not job or not job.get("model"):
        return {"error": "Aucune étude BET avec un relevé validé : lance d'abord generate_full_bet_study avec le PC (et la G2).", "status": "échoué"}
    lots = [x for x in args.get("lots") or [] if x in LOT_LABEL] or ["electricite", "plomberie", "ventilation", "chauffage"]
    raw = dict(job["model"])
    txt = " ".join(x for x in (job.get("hypotheses") or "", args.get("hypotheses") or "") if x)
    raw["user_hypotheses"] = dict(raw.get("user_hypotheses") or {}, _text=txt[:3000])
    try:
        branding = await branding_loader(db, uid) if branding_loader else await _default_branding(db, uid, user)
    except Exception:  # noqa: BLE001
        branding = None
    stem = pipeline._slug((raw.get("project") or {}).get("name", "Projet"))
    label = "-".join(LOT_LABEL[x].split()[0].replace("É", "E").replace("œ", "oe") for x in lots)
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"Plans_PDF_{label}_{stem}.pdf"
        country = job.get("country") or (raw.get("project") or {}).get("country", "FR")
        res = await asyncio.to_thread(pipeline.render_lots, raw, lots, path, None, "pt" if country == "PT" else "fr", branding)
        if not res.get("ok"):
            return {"error": "Plans impossibles sur ce relevé : " + "; ".join(str(a.get("message")) for a in res.get("anomalies", [])[:3]), "status": "échoué"}
        request_id = hashlib.sha256((job["job_id"] + ",".join(lots) + txt + _now()).encode()).hexdigest()[:16]
        art = await _store(db, uid, cid, request_id, "plans_pdf", path, "Plans " + ", ".join(LOT_LABEL[x] for x in lots))
    return {"ok": True, "artifact": art, "job_id": job["job_id"], "sheets": res["sheets"],
            "note": "PDF A3 au format bureau d'études, affiché en bouton de téléchargement. Pré-dimensionnement à faire viser avant exécution."}


async def execute(name: str, args: dict, user: dict, conv: dict, db, llm=None, background: bool = True, doc_loader=None,
                  branding_loader=None) -> dict:
    """doc_loader(db, ids, user_id) -> [(nom, pdf_bytes)] : à fournir si les pièces jointes ne sont pas dans db.assistant_docs (ex. .pt).
    branding_loader(db, user_id) -> dict : identité de l'entreprise (défaut : résolveurs de la plateforme)."""
    uid, cid = user["user_id"], conv.get("conversation_id")
    if name == "generate_bet_lot_plans":
        try:
            return await _lot_plans(db, user, conv, args)
        except Exception as exc:  # noqa: BLE001 — jamais d'erreur muette
            log.exception("bet lot plans failed")
            return {"error": f"Plans impossibles ({type(exc).__name__}: {str(exc)[:200]} — à {pipeline.where(exc)})", "status": "échoué"}
    if name == "read_full_bet_study":
        try:
            return await _read_job(db, uid, str(args.get("job_id") or ""), cid)
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
    decide_alone = await reader.intends_decide_alone(args.get("hypotheses") or "", llm=llm)
    if not decide_alone and cid:            # drapeau « décider seul » posé une fois : les relances ne reposent plus de questions
        prior = await db.bet_study_jobs.find_one({"user_id": uid, "conversation_id": cid, "decide_alone": True}, {"_id": 0, "job_id": 1})
        decide_alone = bool(prior)
    job_id = "bet_" + hashlib.sha256((uid + request_id + "".join(sorted(set(ids))) + hyp + args["country"]).encode()).hexdigest()[:20]
    old = await db.bet_study_jobs.find_one({"job_id": job_id, "user_id": uid}, {"_id": 0, "status": 1, "updated_at": 1})
    if old and old.get("status") == "running" and _age_s(old.get("updated_at")) > STALE_MIN * 60:
        old = None                                          # tâche tuée par un redémarrage : on relance
    if old and old.get("status") in {"running", "done"}:     # après des QUESTIONS, une relance (hypothèses complétées) repart
        return {"ok": True, "job_id": job_id, "status": old["status"], "note": "Étude déjà lancée pour cette demande : utilise read_full_bet_study."}
    await db.bet_study_jobs.update_one({"job_id": job_id}, {"$set": {
        "job_id": job_id, "user_id": uid, "conversation_id": cid, "document_ids": ids, "country": args["country"],
        "hypotheses": args.get("hypotheses", ""), "decide_alone": decide_alone, "status": "running",
        "step": "En file d'attente", "created_at": _now(), "updated_at": _now()}}, upsert=True)
    try:
        branding = await branding_loader(db, uid) if branding_loader else await _default_branding(db, uid, user)
    except Exception:  # noqa: BLE001 — l'identité est facultative : dossier aux couleurs ConstruPilot
        branding = None
    coro = _work(db, job_id, uid, cid, request_id, docs, args.get("hypotheses", ""), args["country"], llm=llm, branding=branding,
                 decide_alone=decide_alone)
    if background:
        task = asyncio.create_task(coro)
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)
    else:
        await coro
    return {"ok": True, "job_id": job_id, "status": "running",
            "note": "Étude lancée en tâche de fond (3 à 8 min). Suis l'avancement avec read_full_bet_study ; aucun résultat n'est encore disponible."}
