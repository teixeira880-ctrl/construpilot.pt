"""Outils Assistant : étude BET complète (structure, plans d'exécution cotés, charpente, électricité, plomberie, devis).

generate_full_bet_study  → lance l'étude en tâche de fond (lecture IA des plans + moteurs déterministes).
read_full_bet_study      → lit l'état, les questions éventuelles et les liens des 4 livrables (dossier PDF, Plans PDF, DXF, XLSX).

Les livrables sont stockés dans db.assistant_artifacts (même format que engines/assistant_files.py) et
téléchargeables par /assistant/artifacts/{artifact_id}/content.
"""
from __future__ import annotations

import re
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
STALE_MIN = 3           # battement toutes les 30 s pendant le calcul : 3 min sans battement = tâche tuée (redémarrage serveur)
HEARTBEAT_S = 30
_TASKS: set = set()     # références fortes : évite qu'asyncio ne ramasse une tâche de fond en cours

TOOLS = [
    {"type": "function", "name": "generate_full_bet_study", "strict": True,
     "description": ("ÉTUDE BET COMPLÈTE d'un bâtiment — maison individuelle OU bâtiment à ossature béton armé (immeuble collectif, bureaux, "
                     "commerce, parking, bâtiment d'activité, équipement public ; type détecté sur les plans) — à partir des plans "
                     "d'architecte (PDF joints) et de l'étude de sol : "
                     "note de calcul Eurocodes, plans d'exécution GROS ŒUVRE entièrement cotés (fondations, niveaux, planchers, coupes, "
                     "façades, détails ferraillés), charpente, électricité, plomberie, devis chiffré Excel et DXF. Lecture des plans par "
                     "IA puis calculs 100 % déterministes et contrôle automatique. Tâche de fond (3 à 8 min) : renvoie un job_id. "
                     "Sans confirmation du périmètre : documents joints, pays du projet (adresse) et précisions de l'utilisateur (dont les matériaux choisis dans les cartes ask_user_choices) dans hypotheses. "
                     "Ne l'utilise pas pour un simple métré ou un devis de rénovation."),
     "parameters": {"type": "object", "properties": {
         "document_ids": {"type": "array", "items": {"type": "string"}, "description": "doc_… des PDF joints à la conversation (PC, plans, coupes, façades, étude de sol)"},
         "hypotheses": {"type": "string", "description": "Hypothèses du client (ex. « planchers poutrelles-hourdis, murs brique 20 »), vide sinon"},
         "country": {"type": "string", "enum": ["FR", "PT", "UA"]}},
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
TOOLS.extend([
    {"type": "function", "name": "get_clt_ua_schema", "strict": True,
     "description": "Returns the explicit-input Ukraine CLT schema. Use before calculate_clt_ua. No default product or climatic values.",
     "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False}},
    {"type": "function", "name": "calculate_clt_ua", "strict": True,
     "description": "Ukraine CLT LIMITED preliminary panel and opaque-envelope calculations from documented engineering inputs. NOT a whole-building certification or automatic design. Never invent properties, location, source references or confirmation.",
     "parameters": {"type": "object", "properties": {"model_json": {"type": "string", "description": "JSON conforming to get_clt_ua_schema; explicit supplied data only"}}, "required": ["model_json"], "additionalProperties": False}}
])
TOOL_NAMES = {t["name"] for t in TOOLS}

INSTRUCTIONS = (
    "\n\nÉTUDE BET COMPLÈTE (generate_full_bet_study / read_full_bet_study) : quand l'utilisateur demande un dossier de bureau d'études "
    "(plans d'exécution, coupes, ferraillage, charpente, électricité, plomberie, thermique, devis) à partir de plans, LANCE "
    "generate_full_bet_study avec les documents joints et ses précisions dans `hypotheses`, sans demander de confirmation du "
    "périmètre. MATÉRIAUX MANQUANTS (étude complète, gros œuvre / estrutura, devis) : si les plans n'indiquent pas les matériaux (murs, planchers, toiture, isolation, menuiseries, "
    "revêtements…), affiche D'ABORD les cartes ask_user_choices (un seul appel, recommandé présélectionné, multi=true si plusieurs "
    "matériaux possibles), puis lance l'étude avec les réponses dans `hypotheses` — sauf MODE SANS QUESTIONS. Suis l'avancement avec "
    "read_full_bet_study jusqu'au dossier terminé. "
    "MODE SANS QUESTIONS (« fais », « c'est un test », « sans questions », « automatique », « décide ») : l'étude va jusqu'au bout "
    "seule ; tout ce que les plans ne précisent pas est tranché avec la meilleure option (recommandée, la plus sûre / la plus "
    "courante) et renvoyé dans le champ `decisions`. Une fois l'étude lancée, NE REPOSE AUCUNE question : "
    "présente le dossier terminé, puis liste brièvement les décisions prises, UNE LIGNE chacune telle quelle, sous le titre "
    "« Décisions prises (modifiables) », et invite l'utilisateur à corriger un point s'il le souhaite. Quand l'utilisateur corrige "
    "ensuite une décision (ou que tu relances un calcul), ajoute sa correction aux hypothèses, relance l'étude et n'affiche QUE ce "
    "qui change, au format « Modifié : X → Y ; impacts : … » — sans reposer les questions ni réafficher tout le dossier. "
    "SI L'ÉTUDE BET ÉCHOUE quand même (documents illisibles…), fais QUAND MÊME le devis avec create_quote_draft à partir des "
    "documents (comme avant) : l'utilisateur doit toujours recevoir un devis. "
    "DEVIS OFFICIEL : quand une étude BET est terminée, son devis (quote_doc_id, calculé sur le métré de l'étude) EST le devis : "
    "ne crée JAMAIS un autre devis avec create_quote_draft pour le même projet (les chiffres divergeraient) ; pour changer un "
    "prix ou une ligne, utilise update_quote_draft sur ce quote_doc_id. "
    "ÉTUDE COMPLÈTE / ESTUDO COMPLETO (« estudo completo », « étude complète », « orçamentação completa », margens, benefícios, "
    "métrés, estudo térmico, plantas de execução…) : fais TOUT (après les cartes de matériaux manquants, sauf mode sans questions) : (1) generate_full_bet_study "
    "(plans d'exécution cotés, note de calcul, métré, devis Excel, étude thermique — RE2020 en France, pré-certificat REH au "
    "Portugal) puis read_full_bet_study jusqu'au dossier terminé ; (2) le devis officiel est créé AUTOMATIQUEMENT par l'étude à partir de son métré "
    "(devis PDF/Excel, métré PDF/Excel et dossier économique coût / vente / marge / bénéfice joints) : ne crée pas d'autre devis. Termine par la liste de CHAQUE livrable demandé avec son fichier ; si un livrable manque, dis lequel et "
    "pourquoi — ne dis jamais « fait » pour un livrable absent. "
    "ÉTUDE THERMIQUE D'ABORD : au Portugal, l'étude BET joint automatiquement le pré-certificat REH (Estudo térmico) calculé "
    "sur la géométrie lue ; en France, si l'utilisateur ne joint pas d'étude thermique, l'étude BET exécute AUTOMATIQUEMENT la "
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
INSTRUCTIONS += (
    " UKRAINE / CLT OVERRIDE: target country UA takes precedence over a reference drawing address. "
    "generate_full_bet_study country=UA reads all pages into an evidence dossier; it does NOT generate execution drawings, "
    "a cost estimate or regulatory approval. CLT in FR / PT keeps the existing engines (never silently changed to masonry: warning CLT-SCOPE). "
    "For UA calculations (climate, ДБН thermal Rq,min, heat loss, snow / wind, structure with dimensioned drawings GO-01…GO-05, CLT panels) "
    "use calcul_ucrania; for a CLT panel / assembly check from manufacturer data use get_clt_ua_schema then calculate_clt_ua "
    "(empty site / requirement fields are pre-filled from ConstruPilot UA norms, never marked confirmed). "
    "Never invent confirmation, source documents, CLT stiffness/resistance, soil or climate. Deciding alone does not lift these limits. "
    "Source facts and proposed CLT redesign remain distinct. A soil report from another site is NOT confirmation of target-site soil. "
    "All-Ukraine support means local inputs are mandatory per project, not a single nationwide climate. "
    "A successful limited check is not structural approval. Explain missing and not_checked fields. "
)
from engines.bet_frame.hook import INSTRUCTIONS_EXTRA as _FRAME_INSTRUCTIONS  # bet_frame
INSTRUCTIONS += _FRAME_INSTRUCTIONS


MIME = {"pdf": "application/pdf", "zip": "application/zip", "png": "image/png", "jpg": "image/jpeg",
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


def _vat_pct(v, country) -> float:
    """IVA do estudo em fração (0,23) ou em % (23) → percentagem."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return 23.0 if country == "PT" else 20.0
    return round(x * 100, 2) if 0 < x <= 1 else x


async def study_quote(db, uid, cid, job_id, res, country, raw) -> tuple[str | None, list]:
    """Cria (ou reutiliza) o orçamento oficial a partir das linhas DETERMINÍSTICAS do estudo: mesmos documentos →
    mesmo métré → mesmo orçamento. Junta os 5 ficheiros (orçamento PDF/Excel, medição PDF/Excel, dossier económico)."""
    from engines.assistant_quote_exports import attach_quote_exports
    from engines.assistant_quote_service import save_quote
    from engines.bet_core.i18n import tr
    lines = res.get("lines") or []
    if not lines:
        return None, []
    lang = res.get("lang") or ("pt" if country == "PT" else "fr")
    user = await db.users.find_one({"user_id": uid}, {"_id": 0}) or {"user_id": uid}
    conv = {"user_id": uid, "conversation_id": cid, "_quote_request_id": "bet_" + job_id, "_quote_create_slot": "bet_study"}
    out = []
    for ln in lines:
        lot = str(tr(ln.get("lot") or "", lang))[:80]
        pu = float(ln.get("pu") or 0)
        out.append({"designation": str(tr(ln.get("label") or "", lang))[:500] or "—", "line_id": None,
                    "description": str(tr(ln.get("note") or "", lang))[:2000], "quantity": float(round(float(ln.get("qty") or 0), 2)),
                    "unit": str(tr(ln.get("unit") or "u", lang))[:12] or "u", "unit_price": round(pu, 2),
                    "price_origin": "estimate", "vat_rate": _vat_pct(ln.get("vat"), country), "lot": lot})
    if len(out) > 150:                    # limite do rascunho: as linhas excedentes agregadas por lote
        head, tail = out[:149], out[149:]
        tot = sum((x["quantity"] or 0) * (x["unit_price"] or 0) for x in tail)
        head.append({**tail[0], "designation": "Restantes artigos do estudo (ver medição Excel)", "description": "", "quantity": 1.0,
                     "unit": "vg", "unit_price": round(tot, 2)})
        out = head
    name = ((raw or {}).get("project") or {}).get("name") or "Moradia"
    client = ((raw or {}).get("project") or {}).get("client") or ""
    title = (("Orçamento — " if lang == "pt" else "Devis — ") + str(name))[:160]
    r = await save_quote({"title": title, "client_name": "" if client in ("—", "-") else str(client)[:200],
                          "vat_rate": out[0]["vat_rate"], "lines": out, "notes": ""}, user, conv)
    doc_id = (r or {}).get("doc_id") or ((r or {}).get("draft") or {}).get("doc_id")
    if not doc_id:
        return None, []
    await db.pro_documents.update_one({"doc_id": doc_id, "user_id": uid},
                                      {"$set": {"assistant_conversation_id": cid, "bet_study_job_id": job_id, "source": "bet_study"}})
    files = await attach_quote_exports(doc_id, user, conv)
    return doc_id, files


async def _store(db, uid, cid, request_id, kind, path: Path, title):
    fmt = ("pdf" if kind in ("plans_pdf", "re2020_pdf", "estimate_pdf") else "xlsx" if kind == "estimate_xlsx"
           else ("jpg" if path.suffix.lower() in (".jpg", ".jpeg") else "png") if kind == "render_png" else kind)
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


_ASK_RX = re.compile(r"(pose[- ]?moi|posez[- ]?moi|demande[- ]?moi|demandez[- ]?moi|pergunta[- ]?me|pergunte[- ]?me|faz[- ]?me|ask me)"
                     r"[^.\n]{0,30}(questions?|perguntas?|choix|op[cç][oõ]es)|avec (des |mes )?questions|valider (chaque|les) (choix|options)", re.I)


def wants_questions(text: str) -> bool:
    """L'utilisateur demande expressément à valider les choix un par un (sinon l'étude décide seule)."""
    return bool(_ASK_RX.search(text or ""))


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
        from engines import calc_live                    # acompanhamento ao vivo (conta CLT Rezult; no-op nas outras)
        await calc_live.ev("erro" if extra.get("status") == "failed" else "etapa", label, motor="generate_full_bet_study",
                           resultado=extra.get("error"), valores={k: str(v)[:200] for k, v in extra.items()
                                                                   if k in ("status", "provider", "building_kind", "review_status")})
    if str(country).upper() == "UA":                     # bet_clt_ua : Ucrânia (CLT), nunca os motores FR / PT
        try:
            from engines.bet_clt_ua.hook import handle
            await handle(docs, hypotheses, step=step, store=_store, db=db, uid=uid, cid=cid, request_id=request_id, llm=llm)
        except Exception as exc:  # noqa: BLE001
            log.exception("bet study UA %s failed", job_id)
            await step("Échec", status="failed", error=f"{type(exc).__name__}: {exc}"[:1200], trace=traceback.format_exc()[-3000:])
        return
    try:
        from engines.bet_frame import hook as _frame_hook       # bet_frame : immeubles, bureaux, parkings, ERP (ossature BA)
        if await _frame_hook.maybe_handle(db, job_id, uid, cid, request_id, docs, hypotheses, country, step=step, store=_store,
                                          llm=llm, branding=branding, decide_alone=decide_alone):
            return
        key = docs_hash(docs, hypotheses, country, decide_alone)
        cached = await _cached_model(db, uid, key)
        if cached and cached.get("model"):
            await step("Relevé déjà validé pour ces documents : réutilisé (résultats identiques)")
            rd = {"ok": True, "model": cached["model"], "anomalies": [], "pages": cached.get("pages") or [], "attempts": 0,
                  "questions": [], "decisions": [str(d) for d in (cached["model"].get("_decisions") or [])], "cached": True}
        else:
            await step("Lecture des plans par IA et relevé du modèle bâtiment")
            rd = await reader.read_building(docs, hypotheses, country, llm=llm, decide_alone=decide_alone, on_progress=step)
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
        if not rd["ok"] and (decide_alone or not rd.get("questions")):
            # Sem desenhos utilizáveis (só memórias / fichas / especialidades): «faz o melhor possível» — modelo-tipo com o que os
            # textos dizem, tudo em hipótese, dossier ESTUDO INDICATIVO. Nunca parar sem resultado (pedido do Martinho, 12/11).
            try:
                from . import typical
                traw, tdec = typical.model(docs, hypotheses, country)
                rd = {**rd, "ok": True, "model": traw, "typical": True,
                      "decisions": list(rd.get("decisions") or []) + tdec, "anomalies": []}
                decisions = [str(d) for d in rd["decisions"]]
                await step("Sem desenhos cotados: estudo INDICATIVO sobre um modelo-tipo (área, tipologia e pisos lidos nos documentos)")
            except Exception:  # noqa: BLE001
                log.warning("typical model fallback failed", exc_info=True)
        if not rd["ok"] and decide_alone and not rd.get("questions"):     # « décide seul » sans question possible : échec explicite, pas de boucle
            blocking = [a for a in rd.get("anomalies") or [] if a.get("level") == "bloquant"]
            msg = (("Levantamento impossível de completar, mesmo decidindo sozinho: " if country == "PT"
                    else "Relevé impossible à compléter, même en tranchant seul : ")
                   + " ; ".join(f"{a['message']} ({a.get('fix') or '?'})" for a in blocking[:3])
                   + (". Não relance o estudo igual: é preciso mais um documento ou dado (ex.: planta com a escada cotada)."
                      if country == "PT" else ". Ne relance pas l'étude à l'identique : il faut un document ou une donnée en plus."))
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
            if decide_alone:
                # « decidir sozinho »: corrigir ANTES dos cálculos o que se sabe corrigir (escada) e aceitar as incoerências
                # restantes como avisos — o estudo e o orçamento vão sempre até ao fim
                try:
                    _m, _an = pipeline.validate(copy.deepcopy(raw))
                    if any(a.get("code") in ("GEO-30", "GEO-31") and a.get("level") == "bloquant" for a in _an):
                        reader.autofix_stair(raw, country)
                        _m, _an = pipeline.validate(copy.deepcopy(raw))
                    if pipeline.forceable(_an):
                        raw["_force"] = {"lang": "pt" if country == "PT" else "fr"}
                    decisions = list(dict.fromkeys(decisions + [str(d) for d in raw.get("_decisions") or []]))
                except Exception:  # noqa: BLE001
                    log.warning("bet pre-fix failed", exc_info=True)
            await step("Preços do orçamento: biblioteca da empresa, depois preços de mercado online" if country == "PT"
                       else "Prix du devis : bibliothèque de l'entreprise, puis prix de marché en ligne")
            try:
                from . import price_resolver
                psum = await price_resolver.resolve(raw, db, uid, country)
                if psum:
                    decisions = list(dict.fromkeys(decisions + [
                        (f"Preços do orçamento: {psum['library']} da biblioteca da empresa, {psum['market_web']} preços de mercado "
                         f"pesquisados online, {psum['reference']} preços de referência — analisar antes de enviar ao cliente.")
                        if country == "PT" else
                        (f"Prix du devis : {psum['library']} de la bibliothèque de l'entreprise, {psum['market_web']} prix de marché "
                         f"trouvés en ligne, {psum['reference']} prix de référence — à analyser avant envoi au client.")]))
            except Exception:  # noqa: BLE001 — les prix ne bloquent jamais l'étude
                log.warning("bet price resolve failed", exc_info=True)
            res = await asyncio.to_thread(pipeline.run, raw, tmp, None, "pt" if country == "PT" else "fr", None, branding)
            if res["status"] == "MODELE_INVALIDE" and decide_alone and pipeline.forceable(res["anomalies"]):
                # « decidir sozinho »: o estudo vai SEMPRE até ao fim — incoerências restantes passam a avisos visíveis
                raw["_force"] = {"lang": "pt" if country == "PT" else "fr"}
                res = await asyncio.to_thread(pipeline.run, raw, tmp, None, "pt" if country == "PT" else "fr", None, branding)
                decisions = list(dict.fromkeys(decisions + [str(d) for d in raw.get("_decisions") or []]))
            if res["status"] == "MODELE_INVALIDE":
                try:                                    # relevé en cache qui ne passe pas les calculs : on l'oublie, sinon chaque relance rejoue l'échec
                    await db.bet_models.delete_one({"user_id": uid, "docs_hash": key})
                except Exception:  # noqa: BLE001
                    log.warning("bet model cache delete failed", exc_info=True)
                blocking = [a for a in res["anomalies"] if a.get("level") == "bloquant"]
                if decide_alone:                        # « décide seul » : pas de question possible → échec explicite, pas de relance en boucle
                    msg = (("Estudo impossível com estes documentos, mesmo decidindo sozinho: " if country == "PT"
                            else "Étude impossible sur ces documents, même en tranchant seul : ")
                           + " ; ".join(f"{a['message']} ({a.get('fix') or '?'})" for a in blocking[:3])
                           + (". Não relance o estudo igual: é preciso mais um documento ou dado."
                              if country == "PT" else ". Ne relance pas l'étude à l'identique : il faut un document ou une donnée en plus."))
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
            renders = []
            try:                              # pelo menos 3 perspetivas 3D reais no dossier (render físico, sem IA)
                from engines import house_pbr
                if res["files"].get("pdf"):
                    renders = await asyncio.to_thread(house_pbr.add_to_dossier, raw, res["files"]["pdf"], "pt" if country == "PT" else "fr")
            except Exception:  # noqa: BLE001 — as perspetivas nunca bloqueiam o dossier
                log.warning("bet study renders failed", exc_info=True)
            for kind in ("pdf", "plans_pdf", "xlsx", "zip", "re2020_pdf"):
                if res["files"].get(kind):
                    arts.append(await _store(db, uid, cid, request_id, kind, Path(res["files"][kind]), labels[kind]))
            for rp, pt, frl in renders:
                arts.append(await _store(db, uid, cid, request_id, "render_png", Path(rp), pt if country == "PT" else frl))
        quote_doc_id = None
        try:                              # devis OFFICIEL = métré déterministe de l'étude (mêmes documents → même devis)
            quote_doc_id, qarts = await study_quote(db, uid, cid, job_id, res, country, raw)
            arts += qarts
        except Exception:  # noqa: BLE001 — le devis officiel ne bloque jamais le dossier d'étude
            log.warning("bet study quote failed", exc_info=True)
        await step("Terminé", status="done", artifacts=arts, review_status=res["status"], blocking=res["blocking"], quote_doc_id=quote_doc_id,
                   sheets=res["sheets"], devis_ht=res["devis_ht"], devis_ttc=res["devis_ttc"], decisions=decisions, decide_alone=decide_alone,
                   extraction=extraction,
                   points=[a["message"] for a in res["anomalies"]][:30] + [i["message"] for i in res["review"]][:30],
                   questions=rd["questions"], demo=rd.get("demo"), cached=bool(rd.get("cached")), provider=rd.get("provider"),
                   thermal={k: v for k, v in (res.get("thermal") or {}).items() if k not in ("tried", "systems")} or None)
    except Exception as exc:  # noqa: BLE001
        log.exception("bet study %s failed", job_id)
        txt = str(exc).lower()
        from engines.bet_core.reader import providers_message
        pm = providers_message(exc, "pt")
        if pm:
            msg = pm
        elif any(s in txt for s in ("credit balance", "insufficient_quota", "quota", "rate limit", "overloaded", "authentication", "invalid x-api-key", "401", "403")):
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
        msg = ("interrompido (reinício do servidor): volta a lançar IMEDIATAMENTE generate_full_bet_study com os mesmos "
               "argumentos (o levantamento já validado é reutilizado), sem perguntar ao utilizador")
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
    if raw.get("kind") == "clt_ua_evidence" or job.get("country") == "UA":
        return {"status": "input_required", "error": "CLT Ukraine evidence is not an execution model. Lot drawings are not available from this preliminary module."}
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


async def _with_heartbeat(db, job_id, coro):
    """Exécute l'étude en signalant qu'elle est vivante (updated_at) toutes les 30 s, même pendant les
    longues lectures IA : une étude tuée par un redémarrage est ainsi détectée en 3 min, pas 25."""
    async def beat():
        while True:
            await asyncio.sleep(HEARTBEAT_S)
            try:
                await db.bet_study_jobs.update_one({"job_id": job_id, "status": "running"}, {"$set": {"heartbeat_at": _now(), "updated_at": _now()}})
            except Exception:  # noqa: BLE001
                log.warning("bet heartbeat failed", exc_info=True)
    hb = asyncio.create_task(beat())
    try:
        return await coro
    finally:
        hb.cancel()


async def execute(name: str, args: dict, user: dict, conv: dict, db, llm=None, background: bool = True, doc_loader=None,
                  branding_loader=None) -> dict:
    """doc_loader(db, ids, user_id) -> [(nom, pdf_bytes)] : à fournir si les pièces jointes ne sont pas dans db.assistant_docs (ex. .pt).
    branding_loader(db, user_id) -> dict : identité de l'entreprise (défaut : résolveurs de la plateforme)."""
    uid, cid = user["user_id"], conv.get("conversation_id")
    if name == "get_clt_ua_schema":
        from engines.bet_clt_ua.schema import Study
        return {"schema": Study.model_json_schema(), "scope": "preliminary_explicit_inputs_only"}
    if name == "calculate_clt_ua":
        import json
        from engines.bet_clt_ua.engine import run as run_clt
        try:
            text = args.get("model_json") or ""
            if len(text) > 1000000:
                raise ValueError("Input exceeds 1 MB")
            from engines.calc_lots.ucrania import preencher_clt_ua
            raw, filled = preencher_clt_ua(json.loads(text))       # normas UA ConstruPilot só nos campos vazios, nunca "confirmed"
            out = run_clt(raw)
            out["auto_filled_from_constru_pilot_norms"] = filled
            return out
        except (ValueError, TypeError, OverflowError) as exc:
            return {"status": "INVALID_INPUT", "execution_ready": False, "error": str(exc)[:3000]}
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
    # 09/11/2026 (Martinho) : l'étude va TOUJOURS jusqu'au bout, seule, avec les meilleures options (décisions listées et
    # modifiables ensuite). Les questions ne reviennent que si l'utilisateur les demande expressément (« pose-moi les questions »).
    decide_alone = not wants_questions(args.get("hypotheses") or "")
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
        task = asyncio.create_task(_with_heartbeat(db, job_id, coro))
        _TASKS.add(task)
        task.add_done_callback(_TASKS.discard)
    else:
        await coro
    return {"ok": True, "job_id": job_id, "status": "running",
            "note": "Étude lancée en tâche de fond (3 à 8 min). Suis l'avancement avec read_full_bet_study ; aucun résultat n'est encore disponible."}
