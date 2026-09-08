"""Couche IA modulaire (GPT-5.5 via Emergent LLM key)."""
import logging
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


# Chatbot d'aide public — meilleur modèle (Claude Opus 4.8) via la clé LLM universelle
HELP_PROVIDER, HELP_MODEL = "anthropic", "claude-opus-4-8"

# Aide contextuelle : route → libellé/description de page pour un support ciblé
_PAGE_HELP = {
    "/dashboard": "Tableau de bord (vue d'ensemble des projets et devis)",
    "/estimation": "Estimateur de travaux (chiffrage rapide)",
    "/appro": "Analyse technique & Approvisionnement (Acier, Étanchéité, Toiture, VRD)",
    "/plan": "Analyse de plans DWG/DXF/PDF, mesure 2D et métré",
    "/devis": "Gestion des devis",
    "/calculateurs": "Calculateurs (surfaces, volumes, quantités)",
    "/prix": "Recherche de prix matériaux",
    "/coach": "Coach IA travaux",
    "/fonctionnalites": "Page Fonctionnalités (présentation particulier & pro)",
    "/tarifs": "Page Tarifs",
    "/equipe": "Gestion d'équipe (Pro)",
    "/fournisseurs": "Mes fournisseurs (Pro)",
}

HELP_KB = """CONSTRUPILOT — base de connaissances produit.

POUR LES PARTICULIERS :
- Estimateur de travaux : chiffrage instantané (matériaux + main d'œuvre) par type de projet.
- Smart Project : décrivez « rénover salle de bain 8 m² » et l'IA génère lots, matériaux et budget.
- Analyse de photo : envoyez une photo d'une pièce/défaut, l'IA donne des pistes (sans certitude si données insuffisantes).
- Scanner de devis : importez un devis PDF, l'IA l'explique et le vérifie.
- Calculateurs : surfaces, volumes, quantités (peinture, carrelage, béton…).
- Recherche de prix, coach IA travaux, planning des phases de chantier.
- Sécurité : pour gaz, électricité, murs porteurs, structure, amiante, toiture, l'app recommande toujours un professionnel.

POUR LES PROS (offre Pro / Owner) :
- Analyse de plans DWG/DXF/PDF : rendu fidèle (cotes, textes) et métré exact (murs, planchers, escaliers, poutres, poteaux) via extraction des calques et empreinte au sol.
- Métré béton (structural) et devis détaillé par corps d'état, marges, acompte.
- Bibliothèque de prix DPGF/BPU personnalisée : importez votre Excel/PDF pour surcharger les prix IA.
- Module « Analyse technique & Approvisionnement IA » (page /appro), en onglets :
  • Ferraillage / Acier : extraction des barres HA et treillis, bordereau, quantités commandables.
  • Étanchéité (toiture-terrasse) : bordereau par couche → rouleaux/bidons/panneaux.
  • Toiture (couverture en pente) : tuiles/ardoises/bac acier, écran, liteaux, faîtage, noues, gouttières.
  • VRD / Réseaux : EP, EU, AEP, télécom, gaz + métré des tranchées (déblai, sable, grillage, remblai, réfection).
  Chaque bordereau : chiffrage via catalogue fournisseur ou bibliothèque DPGF, surlignage de l'élément sur le plan, export CSV et bon de commande envoyé par e-mail au fournisseur.
- Mes fournisseurs : carnet d'adresses + catalogue de prix par fournisseur.
- Devis en ligne signables, acompte Stripe (30 %), planning Gantt, portail Pro, gestion d'équipe, API, PWA mobile.

TARIFS / COMPTE : voir la page Tarifs. Essai avec comptes démo disponibles sur la page de connexion.
"""


async def help_assistant(history: list[dict], message: str, session_id: str,
                         page: str | None = None, provider: str | None = None,
                         model: str | None = None) -> str:
    """Chatbot d'aide (Claude Opus 4.8) : répond aux questions sur ConstruPilot."""
    system = (BRAND + "\n\nTu es l'assistant d'aide de ConstruPilot. Tu réponds UNIQUEMENT à "
              "propos de ConstruPilot (ses fonctionnalités, comment les utiliser, quelle offre "
              "choisir). Sois concis, clair et chaleureux. Si on te demande une chose hors sujet, "
              "ramène poliment vers ConstruPilot. Base-toi sur ces informations :\n" + HELP_KB)
    page_ctx = _PAGE_HELP.get((page or "").rstrip("/"), None)
    if page_ctx:
        system += (f"\n\nCONTEXTE : l'utilisateur est actuellement sur la page « {page_ctx} » "
                   f"(URL {page}). Adapte ton aide à cette page en priorité, propose l'action "
                   f"la plus utile ici, mais réponds aussi à sa question précise.")
    convo = "\n".join(f"{'Utilisateur' if m.get('role') == 'user' else 'Assistant'}: {m.get('content','')}"
                      for m in (history or [])[-8:])
    prompt = (f"Conversation:\n{convo}\n\nNouveau message: {message}" if convo else message)
    prov, mdl = provider or HELP_PROVIDER, model or HELP_MODEL
    await _log_usage("help_chat", prov, mdl)
    chat = _chat(system, session_id, prov, mdl)
    out = []
    async for ev in chat.stream_message(UserMessage(text=prompt)):
        if isinstance(ev, TextDelta):
            out.append(ev.content)
        elif isinstance(ev, StreamDone):
            break
    return "".join(out)



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
        '  "element_count": number (nombre d\'éléments identiques indiqué au cartouche, ex "Nombre : 2" → 2 ; sinon 1),\n'
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


async def analyze_waterproofing(images: list[str]) -> dict:
    """Analyse IA d'un plan/détail d'étanchéité toiture terrasse (Gemini 3.1 Pro)."""
    if not images:
        return {"layers": [], "surface_m2": 0, "perimeter_m": 0, "releve_h_m": 0.5,
                "system_type": "bicouche", "scale_confidence": 0, "notes": "aucune image"}
    system = (BRAND + " Tu es métreur étanchéité expert (toiture terrasse, DTU 43.1) : "
              "complexes bitume SBS/APP, PVC, EPDM, relevés, acrotères, EP.")
    prompt = (
        "Analyse ce plan/détail d'étanchéité de toiture terrasse. Retourne UNIQUEMENT ce JSON :\n"
        '{ "scale_detected": string|null, "scale_confidence": number(0-1),\n'
        '  "system_type": "monocouche"|"bicouche",\n'
        '  "surface_m2": number, "perimeter_m": number, "releve_h_m": number,\n'
        '  "layers": [ { "name": string, "present": true } ] (couches détectées : forme de pente, '
        'chape, EIF/primaire, pare-vapeur, isolant, membrane 1, membrane 2, protection),\n'
        '  "singular": [ { "name": string, "unit": string, "qty": number } ] (acrotères ml, EP/drains u…),\n'
        '  "regions": [ { "key": "surface"|"releve", "bbox": [x1,y1,x2,y2] (normalisé 0-1) } ],\n'
        '  "confidence": number(0-1), "notes": string }\n'
        "Estime la surface horizontale et le périmètre au mieux via l'échelle/cotations. "
        "Si incertain, baisse la confiance (<0.6). N'invente pas de couche absente."
    )
    return _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO,
                                         feature="waterproofing"),
                 {"layers": [], "surface_m2": 0, "perimeter_m": 0, "releve_h_m": 0.5,
                  "system_type": "bicouche", "scale_confidence": 0, "notes": ""})


async def analyze_roofing(images: list[str]) -> dict:
    """Analyse IA d'un plan de toiture en pente (Gemini 3.1 Pro) → surfaces + linéaires."""
    if not images:
        return {"surface_projetee_m2": 0, "pente_pct": 35, "roof_type": "4 pans",
                "faitage_ml": 0, "aretiers_ml": 0, "noues_ml": 0, "rives_ml": 0,
                "egout_ml": 0, "scale_confidence": 0, "notes": "aucune image"}
    system = (BRAND + " Tu es métreur couverture/charpente expert (toitures en pente : "
              "tuiles, ardoises, bac acier). Tu sais lire un plan de toiture (croupes/arêtiers, "
              "noues, faîtage, rives, égout) et estimer les surfaces rampantes.")
    prompt = (
        "Analyse ce plan de toiture en pente. Repère le type (2 pans, 4 pans/croupe, "
        "monopente…), la surface au sol projetée, la pente, et les linéaires de faîtage, "
        "arêtiers, noues, rives et égout.\n"
        "Retourne UNIQUEMENT ce JSON :\n"
        '{ "scale_detected": string|null, "scale_confidence": number(0-1),\n'
        '  "roof_type": string, "surface_projetee_m2": number, "pente_pct": number,\n'
        '  "faitage_ml": number, "aretiers_ml": number, "noues_ml": number,\n'
        '  "rives_ml": number, "egout_ml": number,\n'
        '  "regions": [ { "key": "couverture"|"faitage"|"aretiers"|"noues"|"rives"|"egout", '
        '"bbox": [x1,y1,x2,y2] (normalisé 0-1) } ],\n'
        '  "confidence": number(0-1), "notes": string }\n'
        "Estime au mieux via l'échelle/cotations. Le faîtage est l'arête horizontale haute ; "
        "les arêtiers sont les arêtes inclinées sortantes (croupe) ; les noues sont les arêtes "
        "rentrantes ; l'égout est le périmètre bas (gouttières). Si incertain, baisse la "
        "confiance (<0.6). N'invente pas de valeur : mets 0 si l'élément est absent."
    )
    return _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO,
                                         feature="roofing"),
                 {"surface_projetee_m2": 0, "pente_pct": 35, "roof_type": "4 pans",
                  "faitage_ml": 0, "aretiers_ml": 0, "noues_ml": 0, "rives_ml": 0,
                  "egout_ml": 0, "scale_confidence": 0, "notes": ""})


async def analyze_vrd(images: list[str]) -> dict:
    """Analyse IA d'un plan VRD / plan masse (Gemini 3.1 Pro) → réseaux + tranchées."""
    if not images:
        return {"networks": [], "scale_confidence": 0, "notes": "aucune image"}
    system = (BRAND + " Tu es métreur VRD expert (voirie & réseaux divers) : tu lis les plans "
              "masse/réseaux et repères les tracés EP (eaux pluviales), EU (eaux usées), "
              "AEP (eau potable), télécom/électricité et gaz, avec leurs longueurs.")
    prompt = (
        "Analyse ce plan VRD / plan de masse. Repère chaque réseau tracé et estime sa "
        "longueur en mètres, la largeur et la profondeur de tranchée si indiquées.\n"
        "Retourne UNIQUEMENT ce JSON :\n"
        '{ "scale_detected": string|null, "scale_confidence": number(0-1),\n'
        '  "networks": [ { "key": "EP"|"EU"|"AEP"|"telecom"|"gaz", "label": string,\n'
        '    "length_ml": number, "larg_m": number|null, "prof_m": number|null,\n'
        '    "confidence": number(0-1), "bbox": [x1,y1,x2,y2] (normalisé 0-1, emprise du tracé) } ],\n'
        '  "notes": string }\n'
        "Estime les longueurs au mieux via l'échelle/cotations. Si un réseau est absent, ne "
        "le liste pas. Si incertain, baisse la confiance (<0.6). N'invente pas de réseau."
    )
    return _json(await _complete_vision(system, prompt, images[:4], *GEMINI_PRO, feature="vrd"),
                 {"networks": [], "scale_confidence": 0, "notes": ""})


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


async def plan_command(rooms: list[dict], walls: list[dict], command: str) -> dict:
    """Interprète une commande en langage naturel sur un plan et renvoie UNE action
    structurée (aperçu, sans appliquer). Utilisé par l'assistant IA du plan (P3).

    Actions possibles :
      rename_room       {room_id, new_name}
      delete_room       {room_id}
      set_room_surface  {room_id, surface_m2}
      set_room_height   {room_id, height_m}
      reclassify_wall   {wall_id, new_type}  new_type ∈ porteur|cloison|doublage
      add_note          {text}
      none              {}  (commande non comprise / hors périmètre)
    """
    rooms_ctx = [{"room_id": r.get("room_id"), "name": r.get("name"),
                  "surface_m2": r.get("surface_m2"),
                  "height_m": r.get("ceiling_height_m") or r.get("height_m")}
                 for r in (rooms or [])]
    walls_ctx = [{"wall_id": w.get("wall_id") or w.get("id"),
                  "wall_type": w.get("wall_type")} for w in (walls or [])][:60]
    system = (BRAND + " Tu es l'assistant d'édition d'un plan de métré BTP. "
              "Tu convertis une instruction utilisateur en UNE seule action JSON stricte. "
              "Réponds UNIQUEMENT en JSON, sans markdown.")
    prompt = (
        "PIÈCES du plan (room_id → nom, surface m², hauteur m) :\n"
        f"{json.dumps(rooms_ctx, ensure_ascii=False)}\n\n"
        "MURS détectés (wall_id → type) :\n"
        f"{json.dumps(walls_ctx, ensure_ascii=False)}\n\n"
        f"INSTRUCTION UTILISATEUR : « {command} »\n\n"
        "Choisis l'action correspondante et renvoie ce schéma EXACT :\n"
        '{\n'
        '  "action": "rename_room|delete_room|set_room_surface|set_room_height|reclassify_wall|add_note|none",\n'
        '  "params": { ... },\n'
        '  "summary": "phrase courte en français décrivant ce qui va être fait",\n'
        '  "confidence": 0.0\n'
        '}\n'
        "Règles : résous les noms de pièce vers leur room_id EXACT de la liste. "
        "Pour set_room_surface, params={room_id, surface_m2 (nombre)}. "
        "Pour set_room_height, params={room_id, height_m (nombre en mètres)}. "
        "Pour reclassify_wall, params={wall_id, new_type}. "
        "Pour add_note, params={text}. "
        "Si l'instruction ne correspond à aucune action, action=none et summary explique pourquoi."
    )
    raw = await _complete(system, prompt, feature="plan_command")
    data = _json(raw, {"action": "none", "params": {},
                       "summary": "Commande non comprise.", "confidence": 0.0})
    if not isinstance(data, dict) or "action" not in data:
        return {"action": "none", "params": {}, "summary": "Commande non comprise.", "confidence": 0.0}
    data.setdefault("params", {})
    data.setdefault("summary", "")
    data.setdefault("confidence", 0.5)
    return data



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


async def ocr_pages_to_text(images: list[str], batch: int = 4) -> str:
    """OCR de pages scannées (PNG base64) via le modèle vision → texte brut, dans l'ordre."""
    system = (BRAND + " Tu es un moteur OCR spécialisé documents techniques du bâtiment (CCTP, DPGF, devis). "
              "Tu transcris fidèlement le texte des pages, sans résumer ni interpréter.")
    parts: list[str] = []
    for i in range(0, len(images), batch):
        chunk = images[i:i + batch]
        prompt = (f"Transcris intégralement le texte de ces {len(chunk)} page(s) scannée(s), dans l'ordre. "
                  "Conserve la numérotation des articles, les titres de lots, les quantités et unités, "
                  "les marques et normes. Sépare chaque page par une ligne '--- page ---'. "
                  "Réponds uniquement avec le texte transcrit.")
        try:
            parts.append((await _complete(system, prompt, images=chunk, feature="cctp_ocr")).strip())
        except Exception as e:  # noqa: BLE001
            logging.getLogger(__name__).warning(f"OCR batch {i} failed: {e}")
    return "\n".join(parts).strip()



async def cctp_lines_from_text(text: str, lot_filter: str = "") -> tuple[list[dict], str, list[dict]]:
    """Lit un CCTP (texte) et en extrait les ouvrages imposés + prescriptions (marques, normes, DTU).

    Retourne (lines, title, prescriptions). Prix à 0 (chiffrés ensuite via la bibliothèque).
    """
    system = (BRAND + " Tu es économiste de la construction : tu lis un CCTP (Cahier des Clauses Techniques "
              "Particulières) et tu en extrais les ouvrages à chiffrer, avec les matériaux, marques, normes et "
              "DTU imposés, pour préparer le devis d'une entreprise.")
    scope = f"\nNe traite QUE le lot : « {lot_filter} »." if lot_filter else ""
    prompt = (
        "Voici le texte d'un CCTP (extrait). Identifie chaque ouvrage / prestation que l'entreprise doit "
        "chiffrer et les prescriptions techniques imposées." + scope +
        "\n\nCCTP :\n« " + (text or "").strip()[:60000] + " »\n\n"
        "Retourne UNIQUEMENT ce JSON :\n"
        '{ "title": "titre court (opération / lot)", '
        '"lines": [ { "category": "nom du lot CCTP (ex. LOT 03 - PLÂTRERIE)", '
        '"article": "n° d\'article CCTP si présent (ex. 3.2.1)", '
        '"designation": "libellé court de l\'ouvrage", '
        '"description": "prescriptions imposées : matériaux, marque/référence ou équivalent, épaisseurs, '
        'classement, normes/DTU, mise en œuvre (2 à 5 lignes séparées par des retours à la ligne)", '
        '"unit": "u|m²|ml|m³|forfait|ens|kg|h", "qty": nombre ou null si non indiqué, '
        '"imposed_materials": ["matériau ou marque imposé", "..."] } ], '
        '"prescriptions": [ { "theme": "ex. Normes / Sécurité / Réception", "text": "prescription générale" } ] }\n'
        "Respecte la numérotation et l'ordre du CCTP. Regroupe par lot. N'invente pas de prix. "
        "Jusqu'à 60 lignes, en français."
    )
    data = _json(await _complete(system, prompt, feature="cctp_read"), {"lines": []})
    units = ("u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L")
    lines: list[dict] = []
    for l in (data.get("lines") or [])[:60]:
        try:
            desig = str(l.get("designation") or "").strip()[:160]
            if not desig:
                continue
            art = str(l.get("article") or "").strip()[:20]
            desc = str(l.get("description") or "").strip()[:900]
            mats = [str(m).strip()[:80] for m in (l.get("imposed_materials") or []) if str(m).strip()][:8]
            if mats:
                desc = (desc + "\nImposé : " + " · ".join(mats)).strip()
            unit = str(l.get("unit") or "u").strip()
            qty = l.get("qty")
            lines.append({
                "designation": (f"{art} — " if art else "") + desig,
                "description": desc, "unit": unit if unit in units else "u",
                "qty": float(qty) if isinstance(qty, (int, float)) and qty > 0 else 1.0,
                "qty_from_cctp": isinstance(qty, (int, float)) and qty > 0,
                "unit_price_ht": 0, "vat_rate": 10,
                "category": str(l.get("category") or "").strip()[:80],
                "imposed_materials": mats,
            })
        except Exception:  # noqa: BLE001
            continue
    prescriptions = [{"theme": str(p.get("theme") or "")[:60], "text": str(p.get("text") or "")[:500]}
                     for p in (data.get("prescriptions") or [])[:20] if p.get("text")]
    return lines, str(data.get("title") or "").strip()[:120], prescriptions



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


async def extract_document_from_pdf(text: str = "", images: list[str] | None = None) -> dict:
    """Extrait un devis/facture (venant d'un autre logiciel) en structure ConstruPilot.

    `text` = texte extrait du PDF (PDF natif) ; `images` = pages rendues en PNG b64 (scans).
    Retourne un dict : doc_type, number, issue_date, client{}, lines[], notes.
    """
    system = (BRAND + " Tu extrais les données d'un devis ou d'une facture du BTP (émis par un autre "
              "logiciel) pour les importer. Tu lis les coordonnées du CLIENT (destinataire), le NUMÉRO "
              "du document tel qu'imprimé, la DATE, et TOUTES les lignes de prestations avec quantités, "
              "unités, prix unitaires HT et taux de TVA.")
    body = (
        "Analyse ce document" + (" (texte extrait ci-dessous)" if text else " (voir les images/pages jointes)")
        + " et renvoie UNIQUEMENT ce JSON, sans commentaire :\n"
        '{ "doc_type": "quote|invoice|credit_note", '
        '"number": "numéro EXACT tel qu\'imprimé sur le document", '
        '"issue_date": "AAAA-MM-JJ ou vide", '
        '"client": { "first_name": "", "last_name": "", "company": "", "email": "", '
        '"phone": "", "address": "", "postal_code": "", "city": "", "siret": "" }, '
        '"lines": [ { "designation": "libellé de la prestation", "unit": "u|m²|ml|m³|forfait|ens|h|j|kg|L", '
        '"qty": nombre, "unit_price_ht": nombre, "vat_rate": nombre } ], '
        '"notes": "conditions/paiement éventuels" }\n'
        "Règles : doc_type = 'invoice' si c'est une FACTURE, 'credit_note' si AVOIR, sinon 'quote' (DEVIS). "
        "Le CLIENT est le destinataire, PAS l'entreprise émettrice. Reprends le numéro EXACTEMENT "
        "(ex. '2024-045', 'FAC0012'). Prix unitaires HORS TAXES. Ne surtout rien inventer : laisse vide "
        "si l'information est absente."
    )
    if text:
        body += f"\n\n=== TEXTE DU DOCUMENT ===\n{text[:12000]}"
    raw = await _complete(system, body, images=images or None, feature="doc_import")
    data = _json(raw, {})
    units = ("u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L")
    dt = data.get("doc_type")
    if dt not in ("quote", "invoice", "credit_note"):
        dt = "quote"
    lines: list[dict] = []
    for l in (data.get("lines") or [])[:200]:
        try:
            lines.append({
                "designation": str(l.get("designation") or "").strip()[:200],
                "description": "",
                "unit": l.get("unit") if l.get("unit") in units else "u",
                "qty": max(0.0, float(l.get("qty") or 0)),
                "unit_price_ht": max(0.0, float(l.get("unit_price_ht") or 0)),
                "vat_rate": float(l.get("vat_rate") if l.get("vat_rate") is not None else 20),
                "category": "Importé",
            })
        except Exception:
            continue
    cl = data.get("client") or {}
    client = {k: str(cl.get(k) or "").strip()[:200] for k in
              ("first_name", "last_name", "company", "email", "phone",
               "address", "postal_code", "city", "siret")}
    return {
        "doc_type": dt,
        "number": str(data.get("number") or "").strip()[:60],
        "issue_date": str(data.get("issue_date") or "").strip()[:10],
        "client": client,
        "lines": lines,
        "notes": str(data.get("notes") or "").strip()[:2000],
    }



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
