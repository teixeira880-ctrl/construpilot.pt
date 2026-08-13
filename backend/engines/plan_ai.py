"""AI Plan Interpreter — utilise GPT-Vision pour comprendre un plan 2D.

⚠️ Ce module **ne calcule PAS** les mesures. Il extrait des indices sémantiques :
- pièces détectées avec noms et surfaces textuelles inscrites sur le plan
- ouvertures probables (portes, fenêtres)
- échelle éventuelle
- warnings (plan de mauvaise qualité, échelle absente, etc.)

Les calculs géométriques restent la responsabilité du `geometry.py`.
"""
from __future__ import annotations

import json
import logging
import os
import re

logger = logging.getLogger(__name__)


PROMPT = """Tu es un **expert en gros œuvre et métré du bâtiment** avec 25 ans d'expérience
(maçonnerie, charpente, ouvertures, escaliers). Tu analyses un plan d'architecture 2D et
tu produis un **relevé de métré exhaustif prêt à chiffrer**.

Rends STRICTEMENT du JSON (pas de markdown, pas de texte hors JSON) avec CETTE structure :

{
  "plan_type": "residential" | "commercial" | "facade" | "coupe" | "unknown",
  "detected_scale": "1:50" | "1:100" | "1:200" | null,
  "quality": "excellent" | "good" | "poor" | "unreadable",
  "warnings": ["texte libre : plan flou / échelle absente / etc."],

  "rooms": [
    {
      "name": "Salon",
      "surface_written_m2": 32.40,      // si inscrit sur le plan, sinon null
      "estimated_surface_m2": 32.5,     // ton estimation à partir des cotes visibles
      "perimeter_estimated_m": 22.8,    // périmètre estimé (mètres linéaires)
      "ceiling_height_m": 2.50,         // hauteur sous plafond si indiquée
      "level": "RDC" | "R+1" | "R-1" | "combles" | null,
      "notes": "traversant sud-nord, exposition principale sud"
    }
  ],

  "facade_walls": [
    // Murs extérieurs (façades) : chaque orientation ou pan
    {
      "orientation": "sud" | "nord" | "est" | "ouest" | "sud-est" | "nord-ouest" | "unknown",
      "length_m": 12.4,
      "height_m": 2.50,
      "area_gross_m2": 31.0,             // longueur × hauteur (avant déduction ouvertures)
      "openings_area_m2": 6.2,           // total portes+fenêtres+baies sur cette façade
      "area_net_m2": 24.8,               // net (à peindre / ravaler / isoler)
      "wall_type": "porteur" | "cloison" | "doublage",
      "material_guess": "parpaing" | "béton" | "brique" | "bois" | "pierre" | "unknown"
    }
  ],

  "interior_walls": {
    "total_length_m": 45.0,              // linéaire total cloisons intérieures
    "load_bearing_length_m": 12.0,       // sous-total murs porteurs internes
    "partition_length_m": 33.0,          // sous-total cloisons
    "total_area_gross_m2": 112.5         // linéaire × hauteur moyenne
  },

  "openings": {
    "doors_visible": 5,
    "windows_visible": 8,
    "bays_visible": 2,
    "details": [
      {"kind": "porte" | "fenetre" | "baie" | "porte-fenetre" | "velux",
       "location": "salon-sud" | "cuisine-est" | "escalier" | ...,
       "width_m": 0.90, "height_m": 2.10, "count": 1,
       "area_m2": 1.89}
    ],
    "total_openings_area_m2": 24.5
  },

  "stairwells": [
    // Trémies + emprise escaliers
    {"location": "central" | "façade-est" | ...,
     "type": "droit" | "quart-tournant" | "hélicoïdal" | "unknown",
     "trémie_area_m2": 3.2,              // trou de plancher
     "footprint_m2": 4.5,                // emprise au sol
     "steps": 14, "riser_height_m": 0.17, "tread_depth_m": 0.28,
     "connects_levels": ["RDC", "R+1"]}
  ],

  "floors": {
    "ground_floor_area_m2": 92.0,        // dalle RDC (sur terre-plein ou vide sanitaire)
    "upper_floors_area_m2": 78.0,        // planchers intermédiaires (bois / béton)
    "total_floor_slab_m2": 170.0,
    "slab_thickness_m": 0.20,            // épaisseur estimée dalle béton
    "floor_type": "béton-plein" | "hourdis" | "poutres-bois" | "unknown"
  },

  "totals_gros_oeuvre": {
    "linear_walls_m": 92.5,              // TOTAL linéaire murs (façades + intérieurs)
    "facade_walls_area_net_m2": 145.0,   // TOTAL m² murs extérieurs à ravaler/isoler
    "interior_walls_area_m2": 112.5,     // TOTAL m² cloisons/refends intérieurs
    "openings_area_m2": 24.5,            // TOTAL surface ouvertures
    "floor_slab_area_m2": 170.0,         // TOTAL surface planchers/dalles
    "concrete_volume_m3_estimated": 34.0,// volume béton estimé (dalles + linteaux)
    "confidence": 0.0-1.0
  },

  "total_surface_written_m2": 170.0,
  "confidence": 0.0-1.0
}

RÈGLES CRITIQUES :
- Tu es EXPERT — utilise des ordres de grandeur réalistes (hauteur sous plafond 2.50m
  par défaut, épaisseur dalle 0.20m, porte 0.90×2.10, fenêtre 1.20×1.20…).
- Si l'échelle est écrite (« 1:100 ») utilise-la pour affiner les longueurs.
- Si tu ne peux pas déterminer une valeur avec suffisamment de certitude, mets `null`
  (jamais 0 par défaut, jamais deviner à l'aveugle).
- Distingue **façades (extérieur)** des **cloisons/refends (intérieur)**.
- Détecte les trémies d'escalier (rectangle vide dans le plancher) et donne l'emprise.
- Toujours renseigner `totals_gros_oeuvre` — c'est la partie la plus critique pour le
  chiffrage. Additionne cohéremment les sous-totaux.
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

    # Normalisation — garantit tous les champs de gros œuvre pour le front
    data.setdefault("rooms", [])
    data.setdefault("openings", {})
    data.setdefault("warnings", [])
    data.setdefault("facade_walls", [])
    data.setdefault("interior_walls", {})
    data.setdefault("stairwells", [])
    data.setdefault("floors", {})
    data.setdefault("totals_gros_oeuvre", {})
    # Coerce openings.details to a list even if the model omits it
    if isinstance(data.get("openings"), dict):
        data["openings"].setdefault("details", [])
    return data
