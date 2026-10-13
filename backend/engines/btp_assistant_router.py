"""btp_assistant_router — cerveau autonome de l'Assistant BTP Construpilot.

Interprète n'importe quelle demande (texte + pièces jointes image/PDF) et la route
vers l'action concrète : lecture de plan + métré déterministe, estimation/données
structurées (JSON strict), ou conseil technique/réglementaire (Markdown, avec
recherche web Perplexity si disponible). Réutilise l'infra LLM Emergent (Gemini
multimodal) — aucune clé Google requise. Zéro hallucination : toute donnée clé
manquante est signalée et réclamée, jamais devinée.
"""
from __future__ import annotations

import base64
import os
import re

# ──────────────────────────────────────────────────────────────────────────────
# Système « Rôle BTP Tout-Puissant »
# ──────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT_BTP = (
    "Tu es l'Assistant BTP, l'assistant d'œuvres IA de ConstruPilot. Tu as l'autorité et la capacité d'interpréter "
    "n'importe quel document (image, PDF) ou texte pour réaliser des métrés, des estimations "
    "de coûts, des analyses de plans et du conseil réglementaire BTP (normes françaises, DTU, "
    "Eurocodes). Tu dois soit retourner des analyses détaillées en Markdown structuré "
    "(titres, tableaux, puces), soit du JSON de données structurées, selon la demande.\n"
    "RÈGLES STRICTES — ZÉRO HALLUCINATION : n'invente jamais une cote, une quantité, un prix "
    "ou une règle. Si une information clé manque (ex. épaisseur de dalle, hauteur, ratio "
    "d'acier), tu NE calcules PAS : tu le signales clairement et tu demandes la précision à "
    "l'utilisateur. Distingue toujours une obligation réglementaire d'une recommandation."
)

# mots-clés de routage
_PLAN_HINTS = re.compile(
    r"\b(plan|semelle|fondation|m[ée]tr[ée]|poteau|poutre|longrine|cha[îi]nage|voile|"
    r"ferraillage|coffrage|dalle|b[ée]ton|gros\s*œuvre|gros\s*oeuvre)\b", re.IGNORECASE)
_STRUCTURED_HINTS = re.compile(
    r"\b(devis|estimation|liste\s+(de\s+)?mat[ée]riaux|quantit|bordereau|dpgf|json|tableau\s+de)\b",
    re.IGNORECASE)
_REGUL_HINTS = re.compile(
    r"\b(dtu|norme|r[ée]glementation|re\s*2020|rt\s*2012|eurocode|l[ée]gislation|"
    r"obligatoire|garantie|assurance|d[ée]cennale|autoris)\b", re.IGNORECASE)


def classify_intent(prompt: str, has_pdf: bool, has_image: bool, force_json: bool) -> str:
    """plan_analysis | structured_data | regulatory | multimodal_qa | advice."""
    p = prompt or ""
    if (has_pdf or has_image) and _PLAN_HINTS.search(p):
        return "plan_analysis"
    if force_json or _STRUCTURED_HINTS.search(p):
        return "structured_data"
    if _REGUL_HINTS.search(p):
        return "regulatory"
    if has_pdf or has_image:
        return "multimodal_qa"
    return "advice"


# ──────────────────────────────────────────────────────────────────────────────
# Recherche web (Perplexity) — activée seulement si PERPLEXITY_API_KEY présent
# ──────────────────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# Recherche web (Perplexity sonar-pro) — sources officielles cliquables
# ──────────────────────────────────────────────────────────────────────────────

# Domaines officiels privilégiés (via le prompt) pour le conseil réglementaire BTP (France) :
# Legifrance, CSTB (DTU), AFNOR, RE2020/RT, service-public.fr, ANAH.


def web_search_enabled() -> bool:
    return bool(os.environ.get("PERPLEXITY_API_KEY"))


async def web_search(query: str) -> dict:
    """Recherche web réglementaire via Perplexity Agent API (/v1/responses). Renvoie
    réponse + sources officielles cliquables (titre, url, date). Dégrade proprement sans clé."""
    key = os.environ.get("PERPLEXITY_API_KEY")
    if not key:
        return {"enabled": False, "answer": None, "sources": [],
                "error": "Recherche web désactivée (clé Perplexity absente)."}
    from perplexity import AsyncPerplexity
    instructions = (
        "Assistant de recherche réglementaire bâtiment (France). Réponds en français, de façon "
        "concise et factuelle. Privilégie ABSOLUMENT les sources officielles et cite-les : "
        "Legifrance, DTU (CSTB), normes AFNOR, RE2020/RT, service-public.fr, ANAH. Distingue "
        "clairement DTU / norme / réglementation, indique les dates et rappelle quand une "
        "vérification humaine est nécessaire.")
    client = AsyncPerplexity(api_key=key, max_retries=1, timeout=45.0)
    try:
        r = await client.responses.create(
            input=query, instructions=instructions,
            preset=os.environ.get("PERPLEXITY_PRESET", "fast"),
            store=False, max_output_tokens=1600)
    except Exception:  # noqa: BLE001
        return {"enabled": True, "answer": None, "sources": [],
                "error": "Recherche web momentanément indisponible."}
    answer = (r.output_text or "").strip() or None
    sources, seen = [], set()
    try:
        for item in (r.to_dict().get("output") or []):
            if isinstance(item, dict) and item.get("type") == "search_results":
                for res in (item.get("results") or []):
                    url = (res or {}).get("url")
                    if url and url not in seen:
                        seen.add(url)
                        sources.append({"title": res.get("title") or url, "url": url,
                                        "date": res.get("date")})
    except Exception:  # noqa: BLE001
        pass
    return {"enabled": True, "answer": answer, "sources": sources, "error": None}


# ──────────────────────────────────────────────────────────────────────────────
# Préparation des pièces jointes
# ──────────────────────────────────────────────────────────────────────────────


def _prepare_attachments(attachments: list[dict]) -> tuple[list[str], bytes | None]:
    """attachments: [{filename, data(bytes)}]. Retourne (images_b64, premier_pdf_bytes)."""
    from engines.plan_structure_reader import render_pages_png
    images: list[str] = []
    first_pdf: bytes | None = None
    for att in attachments or []:
        name = (att.get("filename") or "").lower()
        data = att.get("data")
        if not data:
            continue
        if name.endswith(".pdf"):
            if first_pdf is None:
                first_pdf = data
            try:
                images.extend(render_pages_png(data, dpi=150, max_pages=2))
            except Exception:  # noqa: BLE001
                pass
        elif name.split(".")[-1] in ("png", "jpg", "jpeg", "webp", "heic"):
            images.append(base64.b64encode(data).decode())
    return images[:4], first_pdf


# ──────────────────────────────────────────────────────────────────────────────
# Routeur central
# ──────────────────────────────────────────────────────────────────────────────


async def route_user_request(user_prompt: str, attachments: list[dict] | None = None,
                             force_json: bool = False, steel_ratios: dict | None = None) -> dict:
    """Point d'entrée autonome. Retourne un dict :
    { intent, mode('markdown'|'json'|'metre'), markdown?, data?, metre?, sources?,
      missing_data?, warnings? }."""
    attachments = attachments or []
    images, first_pdf = _prepare_attachments(attachments)
    has_pdf = first_pdf is not None
    has_image = bool(images) and not has_pdf
    intent = classify_intent(user_prompt, has_pdf, has_image, force_json)

    # 1) ANALYSE DE PLAN → moteur de métré déterministe (zéro hallucination)
    if intent == "plan_analysis" and first_pdf is not None:
        from engines.plan_structure_reader import read_plan, PlanVisionError
        try:
            result = await read_plan(first_pdf, steel_ratios=steel_ratios)
        except PlanVisionError:
            return {"intent": intent, "mode": "markdown",
                    "markdown": "⚠️ Service de lecture IA momentanément indisponible, réessayez.",
                    "warnings": ["vision_unavailable"]}
        warn = [] if result.get("complete") else ["Cotes/ratios manquants — voir missing_data."]
        return {"intent": intent, "mode": "metre", "metre": result,
                "missing_data": result.get("missing_data", []), "warnings": warn}

    # 2) CONSEIL RÉGLEMENTAIRE → recherche web (si dispo) + synthèse
    sources: list[dict] = []
    web_note = ""
    if intent == "regulatory":
        ws = await web_search(user_prompt)
        if ws.get("answer"):
            sources = ws.get("sources", [])
            web_note = ("\n\nÉléments de recherche web (à vérifier) :\n" + ws["answer"])
        elif ws.get("enabled"):
            web_note = "\n\n(Recherche web indisponible à l'instant.)"

    # 3) DONNÉES STRUCTURÉES → Gemini en mode JSON strict
    if intent == "structured_data":
        from engines.ai import _complete, _complete_vision, _json, GEMINI_PRO
        instr = (user_prompt + web_note +
                 "\n\nRéponds UNIQUEMENT par un objet JSON valide et structuré (aucun texte "
                 "autour). Si une donnée indispensable manque, mets-la dans un tableau "
                 '"missing_data":[{"champ","question","unite"}] au lieu de l\'inventer.')
        raw = (await _complete_vision(SYSTEM_PROMPT_BTP, instr, images, *GEMINI_PRO,
                                      feature="btp_router")
               if images else await _complete(SYSTEM_PROMPT_BTP, instr, feature="btp_router"))
        data = _json(raw, None)
        if data is None:
            return {"intent": intent, "mode": "markdown", "markdown": raw, "sources": sources,
                    "warnings": ["json_parse_failed"]}
        md = data.get("missing_data") if isinstance(data, dict) else None
        return {"intent": intent, "mode": "json", "data": data, "sources": sources,
                "missing_data": md or []}

    # 4) Q&A multimodal / conseil → Markdown structuré
    from engines.ai import _complete, _complete_vision, GEMINI_PRO
    instr = (user_prompt + web_note +
             "\n\nRéponds en Markdown clair et structuré (titres, tableaux, puces). Signale "
             "explicitement toute donnée manquante nécessaire à un calcul au lieu de la deviner.")
    answer = (await _complete_vision(SYSTEM_PROMPT_BTP, instr, images, *GEMINI_PRO,
                                     feature="btp_router")
              if images else await _complete(SYSTEM_PROMPT_BTP, instr, feature="btp_router"))
    return {"intent": intent, "mode": "markdown", "markdown": answer, "sources": sources}
