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

from engines.plan_principles import CORE_PRINCIPLES

logger = logging.getLogger(__name__)


PROMPT = """Tu es un **expert en gros œuvre et métré du bâtiment** avec 25 ans d'expérience
(maçonnerie, charpente, ouvertures, escaliers). Tu analyses un plan d'architecture 2D et
tu produis un **relevé de métré exhaustif prêt à chiffrer** en distinguant clairement :
- les **traits de cotes** (lignes fines avec flèches + valeur numérique) — NE PAS les compter comme des murs
- les **dessins de murs** (traits épais, hachures pleines, remplissage béton/parpaing)
- les **ouvertures / réservations** (portes, fenêtres, baies, trémies escaliers, gaines techniques)
- les **matériaux et spécifications** inscrits en texte (revêtements sols, isolants, finitions, DPE, RE2020)

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
      "notes": "traversant sud-nord, exposition principale sud",
      "floor_material": "carrelage" | "parquet" | "béton" | "moquette" | "vinyle" | null,
      "floor_note_text": "citation textuelle du plan si présente (ex: 'Carrelage 60x60 gris')"
    }
  ],

  "dimension_lines": [
    // Traits de cote lus sur le plan (lignes fines + flèches + valeur)
    // Ne PAS confondre avec les murs !
    // bbox_norm = coordonnées NORMALISÉES 0-1 de la ligne de cote sur l'image
    //   [x1, y1, x2, y2] où (x1,y1) et (x2,y2) sont les extrémités du trait de cote.
    //   x=0 = bord gauche, x=1 = bord droit ; y=0 = haut, y=1 = bas.
    {"value_m": 3.42, "location": "façade sud",
     "orientation": "horizontale" | "verticale" | "oblique",
     "bbox_norm": [0.12, 0.34, 0.48, 0.34],
     "confidence": 0.0-1.0}
  ],

  "wall_types": {
    // Distinction visuelle : trait épais = mur, hachures = béton/parpaing, double-trait = doublage
    "load_bearing_visible": true,       // murs porteurs identifiés (traits pleins épais)
    "partition_visible": true,          // cloisons (traits fins pleins)
    "insulation_layer_visible": false,  // doublage / isolation représenté (double trait)
    "hatching_present": "béton" | "parpaing" | "brique" | "pierre" | "aucun",
    "notes": "légende à interpréter si présente"
  },

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
    // Ouvertures RÉSERVÉES dans les murs (portes, fenêtres, baies, trémies, gaines VMC/plomberie)
    "doors_visible": 5,
    "windows_visible": 8,
    "bays_visible": 2,
    "reservations_visible": 0,            // trémies gaines techniques ≠ portes/fenêtres
    "details": [
      {"kind": "porte" | "fenetre" | "baie" | "porte-fenetre" | "velux" | "reservation",
       "location": "salon-sud" | "cuisine-est" | "escalier" | ...,
       "width_m": 0.90, "height_m": 2.10, "count": 1,
       "area_m2": 1.89,
       "symbol_note": "arc de porte 90° / vitrage double / linteau BA / ..."}
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

  "materials_notes": [
    // Textes/légendes lus sur le plan qui décrivent des matériaux ou spécifications
    {"text_verbatim": "Carrelage grès cérame 60x60 antidérapant",
     "category": "revêtement_sol" | "isolation" | "menuiserie" | "peinture" | "cloison" |
                 "toiture" | "façade" | "réglementaire" | "autre",
     "location_on_plan": "salle de bain" | "légende bas-droit" | ...,
     "quantity_hint": "42 m²" | null}
  ],

  "client_info": {
    // Infos client / maître d'ouvrage détectées dans le cartouche du plan ou l'imprimé
    // Permis de Construire (souvent en bas de page ou en légende). Mets "detected": false
    // si rien n'est lisible. Ne devine jamais : n'extrais que ce qui est écrit.
    "detected": true | false,
    "first_name": "Jean" | null,
    "last_name": "Dupont" | null,
    "company": "SCI ..." | null,
    "email": null,
    "phone": "06 12 34 56 78" | null,
    "address": "12 rue des Lilas" | null,
    "postal_code": "75011" | null,
    "city": "Paris" | null
  },

  "electrical": {
    // Symboles électriques repérés (norme NF C 15-100) — analyse les pictogrammes
    "outlets": 0,            // prises de courant (cercle + 2 traits / "PC")
    "switches": 0,           // interrupteurs (simple, va-et-vient, va-et-vient double)
    "light_points": 0,       // points lumineux / plafonniers (croix ou "x" dans un cercle)
    "spots": 0,              // spots encastrés
    "panels": 0,             // tableaux électriques / GTL / coffrets
    "network_tv": 0,         // prises RJ45 / TV / téléphone / fibre
    "details": [
      {"kind": "prise" | "interrupteur" | "point_lumineux" | "spot" | "tableau" | "rj45" | "tv" | "autre",
       "room": "Salon" | ..., "count": 1, "symbol_note": "prise 16A / va-et-vient / applique / ..."}
    ]
  },

  "plumbing": {
    // Symboles plomberie / sanitaires repérés (pictogrammes des appareils)
    "wc": 0, "washbasins": 0, "showers": 0, "bathtubs": 0,
    "kitchen_sinks": 0, "water_heaters": 0, "washing_machines": 0,
    "supply_points": 0,      // arrivées d'eau (EF/EC)
    "drains": 0,             // évacuations / siphons de sol
    "details": [
      {"kind": "wc" | "lavabo" | "douche" | "baignoire" | "evier" | "chauffe_eau" |
               "lave_linge" | "arrivee_eau" | "evacuation" | "autre",
       "room": "Salle de bain" | ..., "count": 1, "symbol_note": "douche 90x90 / vasque double / ..."}
    ]
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
- **NE JAMAIS confondre traits de cote et murs.** Les traits de cote sont fins, ont des flèches
  ou des tirets aux extrémités et portent une valeur numérique (« 3.42 », « 342 » cm). Les murs
  sont dessinés en trait épais plein, souvent avec hachures ou remplissage.
- **Distingue les ouvertures/réservations** : arc de porte = porte ; rectangle vitré dans un
  mur = fenêtre/baie ; grand trou dans le plancher = trémie escalier ; petit carré étiqueté
  « VMC / gaine » = réservation technique.
- **Recopie les textes verbatim** dans `materials_notes` pour tout ce qui décrit un matériau
  ou une spécification (« isolation laine roche 200 mm », « peinture mate blanche », etc.).
- **Interprète les symboles techniques** : compte et localise les symboles **électriques**
  (prises, interrupteurs, points lumineux, spots, tableau/GTL, RJ45/TV) dans `electrical`,
  et les symboles **plomberie/sanitaires** (WC, lavabo, douche, baignoire, évier, chauffe-eau,
  lave-linge, arrivées/évacuations d'eau) dans `plumbing`. Rattache chaque symbole à sa pièce.
  Si aucun symbole technique n'est visible, laisse les compteurs à 0 et `details` vide.
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


def plan_model() -> tuple[str, str]:
    """Modèle IA pour la lecture de plans : PLAN_AI_MODEL='provider:model' (défaut GPT-5.5, le plus fort en raisonnement+vision)."""
    raw = os.environ.get("PLAN_AI_MODEL") or "openai:gpt-5.5"
    provider, _, model = raw.partition(":")
    return (provider or "openai"), (model or "gpt-5.5")


async def _call_gpt_vision(image_b64_png: str, api_key: str, prompt: str | None = None) -> str:
    """Send the plan image to the configured vision model and return raw text."""
    from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
    provider, model = plan_model()
    chat = LlmChat(
        api_key=api_key,
        session_id="plan-analyze",
        system_message=CORE_PRINCIPLES + "\n\nTu réponds toujours en JSON strict, sans markdown.",
    ).with_model(provider, model)
    msg = UserMessage(
        text=prompt or PROMPT,
        file_contents=[ImageContent(image_base64=image_b64_png)],
    )
    return await chat.send_message(msg)


COTES_PROMPT = """Tu es un métreur expert. Relève TOUTES les cotes (lignes de cote) inscrites sur ce plan,
sans exception : cotes extérieures totales, cotes partielles (chaînes), cotes intérieures de pièces,
cotes d'ouvertures, cotes verticales et horizontales. Ne confonds pas un mur avec un trait de cote.

Réponds UNIQUEMENT en JSON strict :
{
  "scale_text": "1:50" | null,
  "units_hint": "cm" | "m" | "mm" | null,
  "dimension_lines": [
    {"value_m": 3.42,                 // valeur convertie en MÈTRES (342 cm → 3.42 ; 3420 mm → 3.42)
     "raw_text": "342",               // texte exactement tel qu'inscrit sur le plan
     "orientation": "horizontale" | "verticale" | "oblique",
     "location": "façade sud, cote totale" | "salon, largeur" | "fenêtre cuisine" | ...,
     "bbox_norm": [x1, y1, x2, y2],   // extrémités EXACTES du trait de cote (entre les 2 traits d'attache),
                                      // normalisées 0-1 : x=0 bord gauche, x=1 bord droit, y=0 haut, y=1 bas
     "confidence": 0.0-1.0}
  ]
}
Règles : une entrée par cote lue ; pour une cote horizontale y1 == y2, pour une verticale x1 == x2 ;
sois le plus précis possible sur les extrémités (elles servent à mesurer le trait) ; n'invente aucune valeur."""


async def read_dimension_lines(image_b64_png: str) -> dict:
    """Lecture dédiée de toutes les cotes du plan (valeur + position du trait)."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "dimension_lines": []}
    try:
        raw = await _call_gpt_vision(image_b64_png, api_key, prompt=COTES_PROMPT)
        data = _parse_json_response(raw)
    except Exception as e:
        logger.warning(f"AI cotes reading failed: {e}")
        return {"error": f"Lecture IA des cotes impossible : {type(e).__name__}", "dimension_lines": []}
    return {"scale_text": data.get("scale_text"), "units_hint": data.get("units_hint"),
            "dimension_lines": _clean_dimension_lines(data.get("dimension_lines") or [])}


def _parse_json_response(raw: str) -> dict:
    """Extract & parse JSON from a GPT text response (strips markdown fences)."""
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(txt)
    except Exception:
        # Fallback : find first {...} block in the response
        m = re.search(r"\{[\s\S]*\}", txt)
        if not m:
            return {"error": "AI response not JSON", "raw": txt[:200], "confidence": 0.0}
        try:
            return json.loads(m.group(0))
        except Exception as e:
            return {"error": f"JSON parse: {e}", "raw": txt[:200], "confidence": 0.0}


def _clean_dimension_lines(items: list) -> list:
    """Valide et normalise les traits de cote : garde `bbox_norm` si présent et bien formé."""
    out = []
    for it in items or []:
        if not isinstance(it, dict):
            continue
        bbox = it.get("bbox_norm")
        # Un bbox_norm valide = liste/tuple de 4 floats dans [0, 1]
        if isinstance(bbox, (list, tuple)) and len(bbox) == 4:
            try:
                bbox = [max(0.0, min(1.0, float(v))) for v in bbox]
                it["bbox_norm"] = bbox
            except (TypeError, ValueError):
                it.pop("bbox_norm", None)
        else:
            it.pop("bbox_norm", None)
        out.append(it)
    return out


def _normalize_analysis(data: dict) -> dict:
    """Ensure all gros-œuvre fields exist so the front never crashes on undefined."""
    data.setdefault("rooms", [])
    data.setdefault("openings", {})
    data.setdefault("warnings", [])
    data.setdefault("facade_walls", [])
    data.setdefault("interior_walls", {})
    data.setdefault("stairwells", [])
    data.setdefault("floors", {})
    data.setdefault("totals_gros_oeuvre", {})
    data["dimension_lines"] = _clean_dimension_lines(data.get("dimension_lines") or [])
    data.setdefault("wall_types", {})
    data.setdefault("materials_notes", [])
    data.setdefault("electrical", {})
    data.setdefault("plumbing", {})
    data.setdefault("client_info", {})
    if isinstance(data.get("electrical"), dict):
        data["electrical"].setdefault("details", [])
    if isinstance(data.get("plumbing"), dict):
        data["plumbing"].setdefault("details", [])
    if isinstance(data.get("openings"), dict):
        data["openings"].setdefault("details", [])
        data["openings"].setdefault("reservations_visible", 0)
    return data


async def analyze_plan_image(image_b64_png: str) -> dict:
    """Send a PNG plan image to GPT-Vision and return the parsed gros-œuvre JSON.

    Always returns a dict — errors are surfaced via the `error` key.
    """
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "confidence": 0.0}
    try:
        raw = await _call_gpt_vision(image_b64_png, api_key)
    except ImportError:
        logger.error("emergentintegrations not installed")
        return {"error": "AI unavailable", "confidence": 0.0}
    except Exception as e:
        logger.warning(f"AI plan analysis failed: {e}")
        return {"error": f"AI call failed: {type(e).__name__}", "confidence": 0.0}
    return _normalize_analysis(_parse_json_response(raw))
