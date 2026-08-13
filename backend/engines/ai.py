"""Couche IA modulaire (GPT-5.5 via Emergent LLM key)."""
import os
import json
import uuid

from emergentintegrations.llm.chat import (LlmChat, UserMessage, ImageContent,
                                          TextDelta, StreamDone)

from engines.catalog import PROJECT_TYPES, LOTS, FINISH_LEVELS

KEY = os.environ.get('EMERGENT_LLM_KEY', '')
PROVIDER, MODEL = "openai", "gpt-5.5"

BRAND = (
    "Tu es ConstruPilot, l'expert travaux de l'plateforme ConstruPilot. "
    "Tu réponds toujours en français, de façon professionnelle, concrète et chiffrée. "
    "Tu n'encourages jamais un particulier à intervenir sur le gaz, un tableau électrique, "
    "un mur porteur, la structure, l'amiante, une toiture dangereuse ou l'étanchéité structurelle : "
    "dans ces cas tu recommandes explicitement un professionnel. "
    "Les prix et quantités définitifs viennent du moteur de calcul ConstruPilot, pas de toi : "
    "tu peux donner des ordres de grandeur mais tu invites à utiliser l'estimateur."
)


def _chat(system: str, session_id: str | None = None) -> LlmChat:
    return LlmChat(api_key=KEY, session_id=session_id or str(uuid.uuid4()),
                   system_message=system).with_model(PROVIDER, MODEL)


async def _complete(system: str, text: str, images: list[str] | None = None,
                    session_id: str | None = None) -> str:
    chat = _chat(system, session_id)
    contents = [ImageContent(image_base64=i) for i in (images or [])]
    out = []
    async for ev in chat.stream_message(UserMessage(text=text, file_contents=contents or None)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)


async def stream_chat(history: list[dict], message: str, session_id: str, context: str = ""):
    system = BRAND + (f"\n\nContexte du projet de l'utilisateur :\n{context}" if context else "")
    convo = "\n".join(f"{'Utilisateur' if m['role'] == 'user' else 'ConstruPilot'}: {m['content']}"
                      for m in history[-10:])
    prompt = (f"Historique de la conversation:\n{convo}\n\nNouveau message: {message}"
              if convo else message)
    chat = _chat(system, session_id)
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            yield ev.content
        elif isinstance(ev, StreamDone):
            break


def _json(raw: str, fallback):
    raw = (raw or "").strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    start = raw.find('{')
    end = raw.rfind('}')
    if start >= 0 and end > start:
        try:
            return json.loads(raw[start:end + 1])
        except Exception:
            pass
    return fallback


async def analyse_description(description: str) -> dict:
    types = ", ".join(f"{p['key']}" for p in PROJECT_TYPES)
    lots = ", ".join(l["key"] for l in LOTS)
    finishes = ", ".join(f["key"] for f in FINISH_LEVELS)
    system = BRAND + (
        "\nTu analyses une description de projet et retournes UNIQUEMENT du JSON valide, sans texte autour."
    )
    prompt = f"""Analyse cette description de projet de travaux et retourne ce JSON :
{{
 "project_type": "un de: {types}",
 "surface": nombre en m² (estime si absent),
 "ceiling_height_m": nombre en mètres (hauteur sous plafond ; si mentionnée dans la description utilise-la, sinon 2.5 par défaut pour une maison moderne, 2.7 pour un pavillon années 70+, 3.0 pour Haussmannien),
 "building_type": "maison|appartement|commerce",
 "finish_level": "un de: {finishes}",
 "condition": "neuf|bon|moyen|vetuste|a_renover_totalement",
 "lots": ["clés parmi: {lots}"],
 "summary": "résumé du projet en 2 phrases",
 "questions": ["3 à 5 questions courtes et indispensables pour affiner le chiffrage"],
 "risks": ["risques ou points de vigilance identifiés"],
 "diy_advice": "ce que l'utilisateur peut faire lui-même et ce qu'il doit confier à un pro"
}}

Description : {description}"""
    raw = await _complete(system, prompt)
    data = _json(raw, {})
    data.setdefault("project_type", "renovation_complete")
    data.setdefault("surface", 100)
    data.setdefault("ceiling_height_m", 2.5)
    data.setdefault("building_type", "maison")
    data.setdefault("finish_level", "standard")
    data.setdefault("condition", "moyen")
    data.setdefault("lots", [])
    data.setdefault("questions", [])
    data.setdefault("risks", [])
    data.setdefault("summary", description[:200])
    data.setdefault("diy_advice", "")
    try:
        data["surface"] = float(data["surface"])
    except Exception:
        data["surface"] = 100.0
    try:
        h = float(data["ceiling_height_m"])
        data["ceiling_height_m"] = max(2.0, min(5.0, h))  # bornes réalistes
    except Exception:
        data["ceiling_height_m"] = 2.5
    return data


async def analyse_photo(image_b64: str, note: str = "") -> dict:
    system = BRAND + "\nTu analyses une photo de pièce et retournes UNIQUEMENT du JSON valide."
    prompt = f"""Analyse cette photo de pièce/chantier. Les mesures sont approximatives et doivent être confirmées.
Retourne ce JSON :
{{
 "room_type": "type de pièce identifié",
 "estimated_dimensions": {{"length_m": nombre, "width_m": nombre, "height_m": nombre, "floor_area_m2": nombre}},
 "elements": {{"walls": "état", "floor": "état", "ceiling": "état", "windows": nombre, "doors": nombre, "sanitary": "description"}},
 "general_condition": "neuf|bon|moyen|vetuste|a_renover_totalement",
 "recommended_works": [{{"lot": "clé du lot", "name": "nom", "reason": "pourquoi"}}],
 "risks": ["risques visibles"],
 "confidence": "low|medium|high",
 "notes": "commentaire professionnel"
}}
Précision utilisateur : {note or 'aucune'}"""
    raw = await _complete(system, prompt, images=[image_b64])
    data = _json(raw, {})
    data.setdefault("room_type", "Pièce")
    data.setdefault("estimated_dimensions", {"length_m": 3, "width_m": 3, "height_m": 2.5, "floor_area_m2": 9})
    data.setdefault("recommended_works", [])
    data.setdefault("risks", [])
    data.setdefault("confidence", "low")
    data["disclaimer"] = ("Les dimensions issues de l'analyse photo sont approximatives. "
                          "Confirmez-les avant tout calcul définitif.")
    return data


async def analyse_quote(text: str = "", image_b64: str | None = None,
                       reference: dict | None = None) -> dict:
    system = BRAND + "\nTu analyses un devis ou une facture de travaux et retournes UNIQUEMENT du JSON valide."
    ref = json.dumps(reference or {}, ensure_ascii=False)[:2000]
    prompt = f"""Analyse ce devis / facture de travaux.
Prix de référence ConstruPilot pour comparaison : {ref}
Retourne ce JSON :
{{
 "company": "nom de l'entreprise si visible",
 "total_ht": nombre ou null,
 "total_ttc": nombre ou null,
 "lines": [{{"label": "prestation", "quantity": nombre, "unit": "unité", "unit_price": nombre, "total": nombre}}],
 "verdict": "bas|correct|eleve|tres_eleve",
 "verdict_label": "explication courte du verdict",
 "delta_vs_reference_pct": nombre (écart estimé en % vs prix de référence),
 "missing_items": ["prestations potentiellement oubliées"],
 "exclusions": ["exclusions détectées"],
 "warranties": ["garanties mentionnées"],
 "negotiation_tips": ["conseils de négociation"]
}}
Texte du devis : {text[:6000] or 'voir image'}"""
    raw = await _complete(system, prompt, images=[image_b64] if image_b64 else None)
    data = _json(raw, {})
    data.setdefault("verdict", "correct")
    data.setdefault("lines", [])
    data.setdefault("missing_items", [])
    data.setdefault("exclusions", [])
    data.setdefault("warranties", [])
    data.setdefault("negotiation_tips", [])
    return data


async def compare_quotes(quotes: list[dict]) -> dict:
    system = BRAND + "\nTu compares plusieurs devis et retournes UNIQUEMENT du JSON valide."
    prompt = f"""Compare ces devis de travaux et retourne ce JSON :
{{
 "ranking": [{{"company": "nom", "total": nombre, "score": 0-100, "comment": "analyse"}}],
 "best_value": "nom de l'entreprise offrant le meilleur rapport qualité/prix",
 "differences": ["différences importantes de prestations, quantités ou matériaux"],
 "missing_items": ["éléments oubliés par certains devis"],
 "recommendation": "recommandation finale ConstruPilot"
}}
Devis : {json.dumps(quotes, ensure_ascii=False)[:8000]}"""
    raw = await _complete(system, prompt)
    data = _json(raw, {})
    data.setdefault("ranking", [])
    data.setdefault("differences", [])
    data.setdefault("missing_items", [])
    return data


async def project_advice(estimation: dict) -> str:
    system = BRAND
    slim = {
        "type": estimation.get("project_type_name"), "surface": estimation.get("surface"),
        "finition": estimation.get("finish_level_name"), "total": estimation.get("total_avg"),
        "lots": [{"nom": l["name"], "total": l["total"], "difficulté": l["difficulty_label"]}
                 for l in estimation.get("lots", [])],
    }
    prompt = ("Rédige des recommandations professionnelles ConstruPilot pour ce chantier "
              "(6 à 10 puces courtes : ordre des travaux, points de vigilance, économies possibles, "
              "ce qui est faisable soi-même). Pas de markdown de titre, uniquement des puces '- '.\n"
              + json.dumps(slim, ensure_ascii=False))
    return await _complete(system, prompt)
