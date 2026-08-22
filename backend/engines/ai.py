"""Couche IA modulaire (GPT-5.5 via Emergent LLM key)."""
import os
import json
import uuid
from datetime import datetime, timezone

from emergentintegrations.llm.chat import (LlmChat, UserMessage, ImageContent,
                                          TextDelta, StreamDone)

from core.db import db
from engines.catalog import PROJECT_TYPES, LOTS, FINISH_LEVELS

KEY = os.environ.get('EMERGENT_LLM_KEY', '')
PROVIDER, MODEL = "anthropic", "claude-sonnet-4-6"
# Fonctions avec images (analyse photo / devis scanné) → modèle vision (Claude via clé
# Emergent = texte uniquement)
VISION_PROVIDER, VISION_MODEL = "openai", "gpt-5.5"
# Coach IA (chat conversationnel) → Claude Sonnet 4.6 via la clé LLM universelle Emergent
CHAT_PROVIDER, CHAT_MODEL = "anthropic", "claude-sonnet-4-6"

# ---- Sélecteur de modèle IA (configurable par l'admin) ----
# Chaque palier expose un compromis qualité / vitesse / coût pour la génération de TEXTE
# (estimation Smart Project, coach IA, analyses). La vision reste sur VISION_MODEL.
AI_TEXT_MODELS = {
    "opus": {"provider": "anthropic", "model": "claude-opus-4-8",
             "label": "Claude Opus 4.8", "desc": "Qualité maximale · plus lent · plus cher",
             "quality": 3, "speed": 1, "cost": 3},
    "sonnet": {"provider": "anthropic", "model": "claude-sonnet-4-6",
               "label": "Claude Sonnet 4.6", "desc": "Équilibré · recommandé",
               "quality": 2, "speed": 2, "cost": 2},
    "haiku": {"provider": "anthropic", "model": "claude-haiku-4-5-20251001",
              "label": "Claude Haiku 4.5", "desc": "Rapide & économique · qualité moindre",
              "quality": 1, "speed": 3, "cost": 1},
}
DEFAULT_TEXT_TIER = "sonnet"
_TEXT_TIER: str | None = None  # cache mémoire, chargé depuis db.app_settings au 1er appel


async def get_text_tier() -> str:
    global _TEXT_TIER
    if _TEXT_TIER is None:
        doc = await db.app_settings.find_one({"_id": "ai"})
        tier = (doc or {}).get("text_tier", DEFAULT_TEXT_TIER)
        _TEXT_TIER = tier if tier in AI_TEXT_MODELS else DEFAULT_TEXT_TIER
    return _TEXT_TIER


async def set_text_tier(tier: str) -> str:
    global _TEXT_TIER
    if tier not in AI_TEXT_MODELS:
        raise ValueError(f"tier inconnu: {tier}")
    await db.app_settings.update_one({"_id": "ai"}, {"$set": {"text_tier": tier}}, upsert=True)
    _TEXT_TIER = tier
    return tier


async def _text_provider_model() -> tuple[str, str]:
    tier = await get_text_tier()
    cfg = AI_TEXT_MODELS[tier]
    return cfg["provider"], cfg["model"]


async def _log_usage(feature: str, provider: str, model: str) -> None:
    """Incrémente le compteur d'appels IA (total par fonctionnalité/modèle + bucket journalier)."""
    try:
        now = datetime.now(timezone.utc)
        await db.ai_usage.update_one(
            {"feature": feature, "provider": provider, "model": model},
            {"$inc": {"calls": 1}, "$set": {"last_used": now.isoformat()}},
            upsert=True)
        day = now.date().isoformat()
        await db.ai_usage_daily.update_one(
            {"_id": day}, {"$inc": {"calls": 1}}, upsert=True)
    except Exception:
        pass


async def check_ai_budget() -> None:
    """Alerte email si le nombre d'appels IA du mois dépasse le seuil défini par l'admin.
    Envoyé une seule fois par mois (tant que le seuil reste dépassé)."""
    try:
        doc = await db.app_settings.find_one({"_id": "ai"}) or {}
        threshold = doc.get("budget_threshold")
        if not threshold or threshold <= 0:
            return
        month = datetime.now(timezone.utc).strftime("%Y-%m")
        rows = await db.ai_usage_daily.find({"_id": {"$regex": f"^{month}"}}).to_list(40)
        total = sum(r.get("calls", 0) for r in rows)
        if total < threshold or doc.get("budget_alert_month") == month:
            return
        email = doc.get("budget_email")
        if not email:
            admin = await db.users.find_one({"role": "admin"}, {"_id": 0, "email": 1})
            email = admin["email"] if admin else None
        if not email:
            return
        from engines.emailer import send_email
        html = (f"<p>Bonjour,</p>"
                f"<p>Le nombre d'appels IA de ConstruPilot pour le mois <b>{month}</b> a atteint "
                f"<b>{total}</b>, dépassant le seuil configuré de <b>{threshold}</b>.</p>"
                f"<p>Vous pouvez ajuster ce seuil ou changer de modèle IA depuis "
                f"l'onglet « IA » du back-office.</p>"
                f"<p>— ConstruPilot</p>")
        await send_email(email, f"⚠️ Budget IA dépassé — {total} appels en {month}", html)
        await db.app_settings.update_one({"_id": "ai"},
                                         {"$set": {"budget_alert_month": month}}, upsert=True)
    except Exception:
        pass

BRAND = (
    "Tu es ConstruPilot, l'expert travaux de l'plateforme ConstruPilot. "
    "Tu réponds toujours en français, de façon professionnelle, concrète et chiffrée. "
    "Tu n'encourages jamais un particulier à intervenir sur le gaz, un tableau électrique, "
    "un mur porteur, la structure, l'amiante, une toiture dangereuse ou l'étanchéité structurelle : "
    "dans ces cas tu recommandes explicitement un professionnel. "
    "Les prix et quantités définitifs viennent du moteur de calcul ConstruPilot, pas de toi : "
    "tu peux donner des ordres de grandeur mais tu invites à utiliser l'estimateur."
)


def _chat(system: str, session_id: str | None = None,
          provider: str = PROVIDER, model: str = MODEL) -> LlmChat:
    return LlmChat(api_key=KEY, session_id=session_id or str(uuid.uuid4()),
                   system_message=system).with_model(provider, model)


async def _complete(system: str, text: str, images: list[str] | None = None,
                    session_id: str | None = None, feature: str = "misc") -> str:
    # Claude (texte) par défaut ; bascule vision OpenAI si des images sont fournies.
    if images:
        provider, model = VISION_PROVIDER, VISION_MODEL
    else:
        provider, model = await _text_provider_model()
    await _log_usage(feature, provider, model)
    chat = _chat(system, session_id, provider, model)
    contents = [ImageContent(image_base64=i) for i in (images or [])]
    out = []
    async for ev in chat.stream_message(UserMessage(text=text, file_contents=contents or None)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)


async def stream_chat(history: list[dict], message: str, session_id: str, context: str = "") -> None:
    system = BRAND + (f"\n\nContexte du projet de l'utilisateur :\n{context}" if context else "")
    convo = "\n".join(f"{'Utilisateur' if m['role'] == 'user' else 'ConstruPilot'}: {m['content']}"
                      for m in history[-10:])
    prompt = (f"Historique de la conversation:\n{convo}\n\nNouveau message: {message}"
              if convo else message)
    chat_provider, chat_model = await _text_provider_model()
    await _log_usage("coach", chat_provider, chat_model)
    chat = _chat(system, session_id, chat_provider, chat_model)
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            yield ev.content
        elif isinstance(ev, StreamDone):
            break


GEMINI_PRO = ("gemini", "gemini-3.1-pro-preview")


async def _complete_vision(system: str, text: str, images: list[str],
                           provider: str, model: str, feature: str = "misc") -> str:
    """Appel vision avec modèle explicite (ex. Gemini 3.1 Pro pour plans techniques)."""
    await _log_usage(feature, provider, model)
    chat = _chat(system, None, provider, model)
    contents = [ImageContent(image_base64=i) for i in (images or [])]
    out = []
    async for ev in chat.stream_message(UserMessage(text=text, file_contents=contents or None)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)


async def analyze_rebar(images: list[str]) -> dict:
    """Analyse IA d'un plan de ferraillage (Gemini 3.1 Pro vision) → bordereau acier.

    Retourne {scale_confidence, lines:[{diameter, ml, bars, spacing_cm, zone, confidence, bbox}],
    treillis:[{ref, panels, area_m2, confidence}], notes}. Chaque quantité porte une confiance 0..1.
    """
    if not images:
        return {"lines": [], "treillis": [], "scale_confidence": 0, "notes": "aucune image"}
    system = (BRAND + " Tu es ingénieur structure & métreur béton armé, expert en lecture de plans "
              "de ferraillage (fondations, voiles, poteaux, poutres, dalles, escaliers, chaînages).")
    prompt = (
        "Analyse ce plan de ferraillage / béton armé et dresse le bordereau acier.\n"
        "Repère les aciers HA (HA6, HA8, HA10, HA12, HA14, HA16, HA20, HA25, HA32), les treillis "
        "soudés (ST25C, ST20, ST15C…), nomenclatures, repères, espacements, cadres/étriers.\n"
        "Retourne UNIQUEMENT ce JSON :\n"
        '{ "scale_detected": string|null, "scale_confidence": number(0-1),\n'
        '  "lines": [ { "diameter": "HA12", "ml": number, "bars": number|null, '
        '"spacing_cm": number|null, "zone": string, "confidence": number(0-1), '
        '"bbox": [x1,y1,x2,y2] (normalisé 0-1, zone principale) } ],\n'
        '  "treillis": [ { "ref": "ST25C", "panels": number|null, "area_m2": number, '
        '"confidence": number(0-1), "zone": string } ],\n'
        '  "notes": string }\n'
        "Règles : ne JAMAIS inventer un diamètre absent. Si une quantité est incertaine, baisse la "
        "confidence (<0.6). Estime les ml au mieux à partir des longueurs, nombres de barres et "
        "espacements visibles. N'additionne pas les treillis avec les barres."
    )
    data = _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO, feature="rebar"),
                 {"lines": [], "treillis": [], "scale_confidence": 0, "notes": ""})
    return data


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


async def suggest_line_description(designation: str, context: str = "") -> str:
    """Génère une description professionnelle multi-lignes pour une ligne de devis BTP."""
    system = (BRAND + " Tu rédiges des descriptions de lignes de devis BTP, concises, "
              "professionnelles et vendables pour un client.")
    prompt = (
        f"Rédige la description détaillée d'une ligne de devis de travaux : « {designation} ».\n"
        + (f"Contexte du devis : {context}\n" if context else "")
        + "Donne 3 à 6 prestations courtes décrivant ce qui est inclus (préparation du support, "
        "fournitures/matériaux, mise en œuvre, finitions, nettoyage). Adapté à un devis client, "
        "sans prix ni quantité. Réponds en texte simple, UNE prestation par ligne, "
        "commençant par « - », sans titre ni introduction.")
    return await _complete(system, prompt, feature="quote_describe")


async def quote_lines_from_text(transcript: str, images: list[str] | None = None) -> tuple[list[dict], str]:
    """Transforme une description orale (transcription) + photos optionnelles en lignes de devis BTP.

    Retourne (lines, title). Les prix restent à 0 (chiffrés ensuite via la bibliothèque).
    """
    system = (BRAND + " Tu transformes la description orale d'un artisan en lignes de devis BTP "
              "structurées et réalistes (désignations normalisées, unités et quantités estimées).")
    photo_hint = ("\n\nDes PHOTOS du chantier sont jointes : sers-t'en pour préciser les prestations "
                  "(état existant, matériaux, surfaces visibles, contraintes) et affiner les quantités."
                  if images else "")
    prompt = (
        "À partir de cette description de chantier (transcription vocale d'un artisan)"
        + (" et des photos jointes" if images else "")
        + ", génère les lignes de devis.\n"
        f"Description : « {(transcript or '').strip()[:4000]} »"
        + photo_hint
        + "\n\nRetourne UNIQUEMENT ce JSON :\n"
        '{ "title": "titre court du devis", '
        '"lines": [ { "designation": "libellé court de la prestation", '
        '"description": "détail des prestations incluses (2 à 4 lignes séparées par des retours à la ligne)", '
        '"unit": "u|m²|ml|m³|forfait|ens|h|j", "qty": nombre, "vat_rate": 10 } ] }\n'
        "Estime des quantités plausibles si elles ne sont pas données. N'invente pas de prix. "
        "3 à 12 lignes maximum, en français."
    )
    data = _json(await _complete(system, prompt, images=images, feature="quote_from_text"), {"lines": []})
    units = ("u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L")
    lines: list[dict] = []
    for l in (data.get("lines") or [])[:12]:
        try:
            lines.append({
                "designation": str(l.get("designation") or "").strip()[:160],
                "description": str(l.get("description") or "").strip()[:1000],
                "unit": l.get("unit") if l.get("unit") in units else "u",
                "qty": max(0.0, float(l.get("qty") or 1)),
                "unit_price_ht": 0.0,
                "vat_rate": float(l.get("vat_rate") or 10),
                "category": "",
            })
        except Exception:
            continue
    return lines, (data.get("title") or "").strip()[:160]


def _analysis_prompt(description: str) -> str:
    """Construit le prompt JSON d'analyse (séparé pour lisibilité/testabilité)."""
    types = ", ".join(f"{p['key']}" for p in PROJECT_TYPES)
    lots = ", ".join(l["key"] for l in LOTS)
    finishes = ", ".join(f["key"] for f in FINISH_LEVELS)
    return f"""Analyse cette description de projet de travaux et retourne ce JSON :
{{
 "project_type": "un de: {types}",
 "surface": nombre en m² (estime si absent),
 "ceiling_height_m": nombre en mètres (hauteur sous plafond ; si mentionnée dans la description utilise-la, sinon 2.5 par défaut pour une maison moderne, 2.7 pour un pavillon années 70+, 3.0 pour Haussmannien),
 "levels": [
    // Détail par étage SEULEMENT si le bâtiment a plusieurs niveaux avec HSP différentes
    // (ex : maison ancienne RDC 2.60m + R+1 2.30m + combles 1.80m).
    // Sinon renvoyer une liste vide ou omettre.
    {{"label": "RDC" | "R+1" | "R-1" | "combles" | "sous-sol", "surface_m2": nombre, "ceiling_height_m": nombre}}
 ],
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


def _clean_levels(levels: list) -> list[dict]:
    """Ne garde que les niveaux bien formés et bornés (1,5 m ≤ HSP ≤ 5 m)."""
    cleaned = []
    for lvl in levels or []:
        if not isinstance(lvl, dict):
            continue
        try:
            s = float(lvl.get("surface_m2") or 0)
            h = float(lvl.get("ceiling_height_m") or 0)
        except (TypeError, ValueError):
            continue
        if s > 0 and 1.5 <= h <= 5.0:
            cleaned.append({"label": str(lvl.get("label") or "niveau")[:20],
                            "surface_m2": round(s, 2),
                            "ceiling_height_m": round(h, 2)})
    return cleaned


def _normalize_analysis(data: dict, description: str) -> dict:
    """Applique défauts + bornes sur la réponse IA (parsing séparé de l'appel)."""
    defaults = {"project_type": "renovation_complete", "surface": 100,
                "ceiling_height_m": 2.5, "levels": [], "building_type": "maison",
                "finish_level": "standard", "condition": "moyen", "lots": [],
                "questions": [], "risks": [], "summary": description[:200],
                "diy_advice": ""}
    for k, v in defaults.items():
        data.setdefault(k, v)
    try:
        data["surface"] = float(data["surface"])
    except (TypeError, ValueError):
        data["surface"] = 100.0
    try:
        data["ceiling_height_m"] = max(2.0, min(5.0, float(data["ceiling_height_m"])))
    except (TypeError, ValueError):
        data["ceiling_height_m"] = 2.5
    data["levels"] = _clean_levels(data.get("levels"))
    return data


async def analyse_description(description: str) -> dict:
    system = BRAND + (
        "\nTu analyses une description de projet et retournes UNIQUEMENT du JSON valide, sans texte autour."
    )
    raw = await _complete(system, _analysis_prompt(description), feature="smart_project")
    return _normalize_analysis(_json(raw, {}), description)


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
    raw = await _complete(system, prompt, images=[image_b64], feature="photo_analyse")
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
    raw = await _complete(system, prompt, images=[image_b64] if image_b64 else None,
                          feature="quote_scan")
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
    raw = await _complete(system, prompt, feature="quote_compare")
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
    return await _complete(system, prompt, feature="project_advice")


async def extract_price_library(images: list[str]) -> list[dict]:
    """Extrait les lignes tarifaires d'un bordereau de prix PDF (images base64).

    Retourne [{"designation": str, "unit": str, "unit_price": number, "ref": str}].
    """
    if not images:
        return []
    system = (BRAND + " Tu es assistant d'extraction de bordereaux de prix BTP. "
              "Tu lis des tableaux de prix (désignation, unité, prix unitaire HT) "
              "sur des images de documents et tu retournes UNIQUEMENT du JSON valide.")
    prompt = (
        "Extrais TOUTES les lignes tarifaires visibles sur ces pages de bordereau "
        "de prix (fournitures/prestations avec un prix unitaire).\n"
        'Retourne UNIQUEMENT ce JSON : { "lines": [ { "designation": str, '
        '"unit": str, "unit_price": nombre, "ref": str } ] }\n'
        "- designation = libellé de la prestation/produit.\n"
        "- unit = unité (m2, ml, u, h, forfait…) ou \"\" si absente.\n"
        "- unit_price = prix unitaire HT en euros (nombre, sans symbole).\n"
        "- ref = code/référence article si présent, sinon \"\".\n"
        "Ignore les titres de section, sous-totaux et lignes sans prix."
    )
    data = _json(await _complete(system, prompt, images=images[:12],
                                 feature="price_library"), {"lines": []})
    out = []
    for row in (data.get("lines") or []):
        try:
            pu = float(row.get("unit_price") or 0)
        except Exception:
            continue
        des = str(row.get("designation") or "").strip()
        if not des or pu <= 0:
            continue
        out.append({
            "designation": des[:300],
            "unit": str(row.get("unit") or "").strip()[:20],
            "unit_price": round(pu, 2),
            "ref": str(row.get("ref") or "").strip()[:40],
        })
    return out


async def price_dpgf_lines(items: list[dict]) -> list[float]:
    """Estime un prix unitaire HT (€, fournitures + pose, France) par ligne de DPGF/BPU.

    items: [{"designation": str, "unit": str, "qty": number}]
    Retourne une liste de prix unitaires alignée sur items (0 si inconnu).
    """
    if not items:
        return []
    system = (BRAND + " Tu es métreur-économiste de la construction. Tu estimes des prix "
              "unitaires HT réalistes (fournitures + pose, prix France 2026) pour des lignes "
              "de bordereau. Tu retournes UNIQUEMENT du JSON valide.")
    slim = [{"i": n, "designation": (it.get("designation") or "")[:180],
             "unit": it.get("unit") or "u"} for n, it in enumerate(items[:200])]
    prompt = (
        "Estime le prix unitaire HT (€) de chaque ligne de ce bordereau BTP.\n"
        f"Lignes : {json.dumps(slim, ensure_ascii=False)}\n\n"
        'Retourne UNIQUEMENT ce JSON : { "prices": [ { "i": index, "pu": nombre } ] }\n'
        "pu = prix unitaire HT réaliste fournitures+pose pour l\u2019unité donnée. "
        "Mets 0 si la ligne n\u2019est pas chiffrable (titre, sous-total, texte)."
    )
    data = _json(await _complete(system, prompt, feature="dpgf_pricing"), {"prices": []})
    out = [0.0] * len(items)
    for row in (data.get("prices") or []):
        try:
            i = int(row.get("i"))
            if 0 <= i < len(out):
                out[i] = max(0.0, float(row.get("pu") or 0))
        except Exception:
            continue
    return out
