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
    "És o Assistente Construção, o assistente IA de obras do ConstruPilot. Tens autoridade e capacidade para interpretar qualquer documento (imagem, PDF) ou texto para realizar medições, estimativas de custos, análises de plantas e aconselhamento regulamentar de construção (normas portuguesas NP EN, Eurocódigos com Anexos Nacionais, especificações LNEC, RGEU). Deves devolver análises detalhadas em Markdown estruturado (títulos, tabelas, tópicos) ou JSON de dados estruturados, consoante o pedido. Responde em português europeu.\nREGRAS ESTRITAS — ZERO ALUCINAÇÕES: nunca inventes uma cota, uma quantidade, um preço ou uma regra. Se faltar uma informação essencial (ex.: espessura da laje, altura, rácio de aço), NÃO calculas: assinalas claramente e pedes a precisão ao utilizador. Distingue sempre uma obrigação regulamentar de uma recomendação."
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
                "error": "Pesquisa web desativada (chave Perplexity ausente)."}
    from perplexity import AsyncPerplexity
    instructions = (
        "Assistente de pesquisa regulamentar da construção (Portugal). Responde em português europeu, de forma concisa e factual. Privilegia ABSOLUTAMENTE as fontes oficiais e cita-as: Diário da República, LNEC, IPQ (normas NP EN), RGEU, REH/RECS, ADENE, portal das câmaras municipais. Distingue claramente especificação / norma / regulamentação, indica as datas e lembra quando é necessária uma verificação humana.")
    client = AsyncPerplexity(api_key=key, max_retries=1, timeout=45.0)
    try:
        r = await client.responses.create(
            input=query, instructions=instructions,
            preset=os.environ.get("PERPLEXITY_PRESET", "fast"),
            store=False, max_output_tokens=1600)
    except Exception:  # noqa: BLE001
        return {"enabled": True, "answer": None, "sources": [],
                "error": "Pesquisa web momentaneamente indisponível."}
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
                    "markdown": "⚠️ Serviço de leitura IA momentaneamente indisponível, tente novamente.",
                    "warnings": ["vision_unavailable"]}
        warn = [] if result.get("complete") else ["Cotas/rácios em falta — ver missing_data."]
        return {"intent": intent, "mode": "metre", "metre": result,
                "missing_data": result.get("missing_data", []), "warnings": warn}

    # 2) CONSEIL RÉGLEMENTAIRE → recherche web (si dispo) + synthèse
    sources: list[dict] = []
    web_note = ""
    if intent == "regulatory":
        ws = await web_search(user_prompt)
        if ws.get("answer"):
            sources = ws.get("sources", [])
            web_note = ("\n\nElementos da pesquisa web (a verificar):\n" + ws["answer"])
        elif ws.get("enabled"):
            web_note = "\n\n(Pesquisa web indisponível de momento.)"

    # 3) DONNÉES STRUCTURÉES → Gemini en mode JSON strict
    if intent == "structured_data":
        from engines.ai import _complete, _complete_vision, _json, GEMINI_PRO
        instr = (user_prompt + web_note +
                 "\n\nResponde APENAS com um objeto JSON válido e estruturado (nenhum texto à volta). Se faltar um dado indispensável, coloca-o numa tabela \"missing_data\":[{\"champ\",\"question\",\"unite\"}] em vez de o inventar.")
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
             "\n\nResponde em Markdown claro e estruturado (títulos, tabelas, tópicos), em português europeu. Assinala explicitamente qualquer dado em falta necessário a um cálculo em vez de o adivinhar.")
    answer = (await _complete_vision(SYSTEM_PROMPT_BTP, instr, images, *GEMINI_PRO,
                                     feature="btp_router")
              if images else await _complete(SYSTEM_PROMPT_BTP, instr, feature="btp_router"))
    return {"intent": intent, "mode": "markdown", "markdown": answer, "sources": sources}
