"""AI Plan Interpreter — utilise GPT-Vision pour comprendre un plan 2D.

⚠️ Ce module **ne calcule PAS** les mesures. Il extrait des indices sémantiques :
- pièces détectées avec noms et surfaces textuelles inscrites sur le plan
- ouvertures probables (portes, fenêtres)
- échelle éventuelle
- warnings (plan de mauvaise qualité, échelle absente, etc.)

Les calculs géométriques restent la responsabilité du `geometry.py`.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re

logger = logging.getLogger(__name__)


PROMPT = """Tu es un expert du bâtiment analysant un plan d'architecture 2D (résidentiel).

Analyse cette image de plan et renvoie STRICTEMENT un JSON avec cette structure exacte :

{
  "plan_type": "residential" | "commercial" | "facade" | "unknown",
  "detected_scale": "1:50" | "1:100" | "1:200" | null,
  "quality": "excellent" | "good" | "poor" | "unreadable",
  "warnings": ["texte libre..."],
  "rooms": [
    {"name": "Salon", "surface_written_m2": 32.40, "notes": "surface inscrite sur le plan"},
    {"name": "Cuisine", "surface_written_m2": 11.20}
  ],
  "openings": {
    "doors_visible": 5,
    "windows_visible": 4,
    "bays_visible": 1
  },
  "total_surface_written_m2": 76.60,
  "confidence": 0.0-1.0
}

Règles STRICTES :
- Si tu ne peux PAS lire une info avec certitude, mets `null` (jamais deviner).
- `surface_written_m2` : uniquement si la surface est ÉCRITE sur le plan.
- Réponds UNIQUEMENT le JSON, sans markdown, sans commentaire.
"""


async def analyze_plan_image(image_b64_png: str) -> dict:
    """Envoie une image PNG (base64) à GPT-Vision et parse le JSON retourné.

    Retourne un dict même en cas d'erreur (avec `error` renseigné).
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "confidence": 0.0}

    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    except ImportError:
        logger.error("emergentintegrations not installed")
        return {"error": "AI unavailable", "confidence": 0.0}

    try:
        chat = LlmChat(
            api_key=api_key,
            session_id="plan-analyze",
            system_message="Tu réponds toujours en JSON strict, sans markdown.",
        ).with_model("openai", "gpt-4o")  # vision-capable

        msg = UserMessage(
            text=PROMPT,
            file_contents=[ImageContent(image_base64=image_b64_png)],
        )
        raw = await chat.send_message(msg)
    except Exception as e:
        logger.warning(f"AI plan analysis failed: {e}")
        return {"error": f"AI call failed: {type(e).__name__}", "confidence": 0.0}

    # Parse strict JSON
    txt = (raw or "").strip()
    # Retire fences éventuelles ```json ... ```
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", txt, flags=re.MULTILINE).strip()
    try:
        data = json.loads(txt)
    except Exception:
        # Cherche 1er { … } dans la réponse
        m = re.search(r"\{[\s\S]*\}", txt)
        if not m:
            return {"error": "AI response not JSON", "raw": txt[:200], "confidence": 0.0}
        try:
            data = json.loads(m.group(0))
        except Exception as e:
            return {"error": f"JSON parse: {e}", "raw": txt[:200], "confidence": 0.0}

    # Normalisation
    data.setdefault("rooms", [])
    data.setdefault("openings", {})
    data.setdefault("warnings", [])
    return data
