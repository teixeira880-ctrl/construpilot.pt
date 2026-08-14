"""Étude Permis de Construire (PC) — lecture IA + calculs gros œuvre déterministes.

L'IA lit chaque page du PC (texte, plans, notice) et extrait les données du projet.
Les quantités/prix sont calculés ici avec des RÈGLES FIXES validées par l'utilisateur :
- Semelles filantes : toujours 60 × 30 cm (périmètre + refends porteurs)
- Plancher / dalle : épaisseur 15 cm
- Murs : brique isobrique ép. 20 cm
- Escaliers : béton armé
- Aciers : semelles 3+3 HA10 + cadres HA6 (15 kg/ml), dalle ST25C + chapeaux (14 kg/m²),
  escalier 100 kg/m³, chaînages 4 HA10 + cadres HA6 (3,6 kg/ml)
"""
from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---- Règles fixes (validées utilisateur) ---------------------------------
RULES = {
    "semelle_width_m": 0.60,
    "semelle_height_m": 0.30,
    "slab_thickness_m": 0.15,
    "wall_material": "Brique isobrique",
    "wall_thickness_m": 0.20,
    "stairs_material": "Béton armé",
    "acier_semelle_kg_ml": 15.0,     # 3+3 HA10 filants + cadres HA6
    "acier_dalle_kg_m2": 14.0,       # treillis ST25C + chapeaux
    "acier_escalier_kg_m3": 100.0,
    "acier_chainage_kg_ml": 3.6,     # 4 HA10 + cadres HA6
    "bricks_per_m2": 9.5,            # bloc 500 × 212 — ép. 200
}

# ---- Prix unitaires gros œuvre (€ HT / unité) -----------------------------
PC_UNIT_PRICES = {
    "fouilles":       {"mat": 0.0,  "mo": 38.0},   # m³ — pelle mécanique + évacuation
    "beton_proprete": {"mat": 125.0, "mo": 55.0},  # m³ — C16/20
    "beton_semelle":  {"mat": 145.0, "mo": 75.0},  # m³ — C25/30 coulé
    "acier_semelle":  {"mat": 1.45, "mo": 0.55},   # kg — HA façonné posé
    "beton_dalle":    {"mat": 150.0, "mo": 90.0},  # m³ — C25/30 + pompage
    "treillis_dalle": {"mat": 1.35, "mo": 0.40},   # kg — ST25C posé
    "coffrage_rive":  {"mat": 6.0,  "mo": 14.0},   # ml
    "mur_isobrique":  {"mat": 38.0, "mo": 42.0},   # m² — brique 20 + colle joint mince
    "chainage_beton": {"mat": 160.0, "mo": 180.0}, # m³ — CH + CV coffrés
    "acier_chainage": {"mat": 1.45, "mo": 0.65},   # kg
    "linteau":        {"mat": 22.0, "mo": 28.0},   # ml — linteau BA 20×20 coulé
    "escalier_beton": {"mat": 165.0, "mo": 420.0}, # m³ — coffrage + coulage
    "acier_escalier": {"mat": 1.45, "mo": 0.70},   # kg
}

TVA_RATE = 0.20  # construction neuve

PC_PROMPT = """Tu es un **économiste de la construction expert en Permis de Construire (PC) français**
avec 25 ans d'expérience. Tu analyses UNE page d'un dossier de permis de construire
(plan de masse, plan de niveau, façade, coupe, notice descriptive, CERFA…).

Ta mission : IDENTIFIER le texte, le LIRE, COMPRENDRE ce qui est demandé, et extraire
toutes les données nécessaires au chiffrage gros œuvre.

Rends STRICTEMENT du JSON (pas de markdown) avec CETTE structure :

{
  "page_kind": "plan_niveau" | "plan_masse" | "facade" | "coupe" | "notice" | "cerfa" | "autre",
  "texts_verbatim": ["textes clés lus sur la page, recopiés mot pour mot (max 15)"],
  "demandes": ["ce que le PC demande, en clair (ex: 'Construction d'une maison individuelle R+1 de 120 m²')"],
  "project": {
    "nature_travaux": "construction maison neuve" | "extension" | "surélévation" | null,
    "surface_plancher_m2": 120.0,
    "emprise_au_sol_m2": 80.0,
    "nb_niveaux": 2,
    "hauteur_totale_m": 6.5,
    "hauteur_sous_plafond_m": 2.5
  },
  "geometry": {
    "perimeter_ext_m": 38.0,
    "refends_porteurs_m": 9.0,
    "ground_floor_area_m2": 80.0,
    "upper_floors_area_m2": 40.0
  },
  "openings": {"count": 12, "total_area_m2": 22.0, "avg_width_m": 1.2},
  "stairs": {"count": 1, "type": "droit" | "quart-tournant" | null, "steps": 15, "footprint_m2": 4.5},
  "warnings": ["plan flou", "échelle absente", ...],
  "confidence": 0.0-1.0
}

RÈGLES :
- Lis TOUS les textes visibles (cotes, surfaces écrites, notice, cartouche, CERFA).
- `demandes` = reformulation claire de ce que le pétitionnaire demande (nature, surface, niveaux).
- Utilise les cotes écrites pour estimer périmètre et refends (murs porteurs intérieurs).
- Si une valeur n'est pas déterminable sur CETTE page, mets null (jamais 0 par défaut).
- Ordres de grandeur réalistes : HSP 2,50 m, niveau courant ~2,70 m brut.
- Réponds UNIQUEMENT le JSON."""


async def analyze_pc_page(image_b64_png: str) -> dict:
    """Analyse UNE page d'un PC via GPT-Vision. Retourne toujours un dict."""
    api_key = os.environ.get("EMERGENT_LLM_KEY")
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "confidence": 0.0}
    try:
        from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent
        chat = LlmChat(api_key=api_key, session_id="pc-study",
                       system_message="Tu réponds toujours en JSON strict, sans markdown.",
                       ).with_model("openai", "gpt-4o")
        msg = UserMessage(text=PC_PROMPT,
                          file_contents=[ImageContent(image_base64=image_b64_png)])
        raw = await chat.send_message(msg)
    except Exception as e:
        logger.warning(f"PC page analysis failed: {e}")
        return {"error": f"AI call failed: {type(e).__name__}", "confidence": 0.0}
    return _parse_json(raw)


def _parse_json(raw: str) -> dict:
    txt = re.sub(r"^```(?:json)?\s*|\s*```$", "", (raw or "").strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(txt)
    except Exception:
        m = re.search(r"\{[\s\S]*\}", txt)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"error": "AI response not JSON", "confidence": 0.0}


def _pick(analyses: list[dict], path: list[str]) -> float | int | None:
    """Retourne la valeur non-nulle de la page la plus confiante."""
    best, best_conf = None, -1.0
    for a in analyses:
        node = a
        for k in path:
            node = node.get(k) if isinstance(node, dict) else None
        if node is not None and float(a.get("confidence") or 0) > best_conf:
            best, best_conf = node, float(a.get("confidence") or 0)
    return best


def merge_pc_analyses(analyses: list[dict]) -> dict:
    """Consolide les analyses de pages en un seul jeu de données projet."""
    ok = [a for a in analyses if not a.get("error")]
    demandes, texts, warnings = [], [], []
    for a in ok:
        demandes += [d for d in (a.get("demandes") or []) if d and d not in demandes]
        texts += [t for t in (a.get("texts_verbatim") or []) if t and t not in texts]
        warnings += [w for w in (a.get("warnings") or []) if w and w not in warnings]
    return {
        "demandes": demandes[:20],
        "texts": texts[:30],
        "warnings": warnings[:15],
        "nature_travaux": _pick(ok, ["project", "nature_travaux"]),
        "surface_plancher_m2": _pick(ok, ["project", "surface_plancher_m2"]),
        "emprise_au_sol_m2": _pick(ok, ["project", "emprise_au_sol_m2"]),
        "nb_niveaux": _pick(ok, ["project", "nb_niveaux"]),
        "hauteur_sous_plafond_m": _pick(ok, ["project", "hauteur_sous_plafond_m"]),
        "perimeter_ext_m": _pick(ok, ["geometry", "perimeter_ext_m"]),
        "refends_porteurs_m": _pick(ok, ["geometry", "refends_porteurs_m"]),
        "ground_floor_area_m2": _pick(ok, ["geometry", "ground_floor_area_m2"]),
        "upper_floors_area_m2": _pick(ok, ["geometry", "upper_floors_area_m2"]),
        "openings_count": _pick(ok, ["openings", "count"]),
        "openings_area_m2": _pick(ok, ["openings", "total_area_m2"]),
        "avg_opening_width_m": _pick(ok, ["openings", "avg_width_m"]),
        "stairs_count": _pick(ok, ["stairs", "count"]),
        "stairs_steps": _pick(ok, ["stairs", "steps"]),
        "stairs_footprint_m2": _pick(ok, ["stairs", "footprint_m2"]),
        "confidence": round(max((float(a.get("confidence") or 0) for a in ok), default=0.0), 2),
        "pages_ok": len(ok), "pages_failed": len(analyses) - len(ok),
    }


def _resolve_inputs(merged: dict, overrides: dict, rooms_surface_m2: float) -> tuple[dict, dict]:
    """Résout les entrées du calcul : manuel > IA (PC) > mesures plan > estimé."""
    src: dict[str, str] = {}

    def res(key: str, ai_val, fallback, fb_label="estimé"):
        if overrides.get(key) is not None:
            src[key] = "manuel"
            return float(overrides[key])
        if ai_val is not None:
            src[key] = "PC (IA)"
            return float(ai_val)
        src[key] = fb_label
        return float(fallback)

    levels = int(res("levels", merged.get("nb_niveaux"), 1))
    levels = max(1, min(levels, 4))
    surface = res("surface_m2", merged.get("surface_plancher_m2"),
                  rooms_surface_m2 if rooms_surface_m2 > 0 else 100.0,
                  "mesures plan" if rooms_surface_m2 > 0 else "estimé")
    s_rdc = merged.get("ground_floor_area_m2")
    if s_rdc is None:
        s_rdc = merged.get("emprise_au_sol_m2")
    s_rdc = float(s_rdc) if s_rdc is not None else round(surface / levels, 2)
    s_up = merged.get("upper_floors_area_m2")
    s_up = float(s_up) if s_up is not None else max(0.0, round(surface - s_rdc, 2))
    h = res("wall_height_m", merged.get("hauteur_sous_plafond_m"), 2.5)
    per = res("perimeter_m", merged.get("perimeter_ext_m"),
              round(4 * math.sqrt(max(s_rdc, 1)) * 1.08, 1))
    ref = res("refends_m", merged.get("refends_porteurs_m"),
              round(math.sqrt(max(s_rdc, 1)), 1))
    n_open = int(merged.get("openings_count") or max(4, round(surface / 10)))
    w_open = float(merged.get("avg_opening_width_m") or 1.20)
    open_area = float(merged.get("openings_area_m2") or round(surface / 6 + 2, 1))
    stairs = merged.get("stairs_count")
    stairs = int(stairs) if stairs is not None else max(0, levels - 1)
    return ({"levels": levels, "surface_m2": round(surface, 2),
             "ground_floor_area_m2": round(s_rdc, 2), "upper_floors_area_m2": round(s_up, 2),
             "wall_height_m": round(h, 2), "perimeter_m": round(per, 2),
             "refends_m": round(ref, 2), "openings_count": n_open,
             "avg_opening_width_m": w_open, "openings_area_m2": round(open_area, 2),
             "stairs_count": stairs}, src)


def _line(designation: str, detail: str, unit: str, qty: float, price_key: str) -> dict:
    p = PC_UNIT_PRICES[price_key]
    qty = round(qty, 2)
    t_mat = round(qty * p["mat"], 2)
    t_mo = round(qty * p["mo"], 2)
    return {"designation": designation, "detail": detail, "unit": unit, "qty": qty,
            "pu_mat": p["mat"], "pu_mo": p["mo"],
            "total_mat": t_mat, "total_mo": t_mo, "total": round(t_mat + t_mo, 2)}


def _stair_volume(height_m: float, steps: int | None) -> float:
    """Volume béton d'une volée : paillasse ép. 15 + marches 17×28, largeur 1,0 m."""
    n = int(steps or max(3, math.ceil(height_m / 0.17)))
    going = n * 0.28
    slope_len = math.sqrt(height_m ** 2 + going ** 2)
    paillasse = slope_len * 1.0 * 0.15
    marches = n * (0.17 * 0.28 / 2) * 1.0
    return round(paillasse + marches, 3)


def compute_gros_oeuvre(i: dict, stairs_steps: int | None = None) -> dict:
    """Calcul déterministe des quantités + devis détaillé (règles fixes)."""
    R = RULES
    per, ref, lv, h = i["perimeter_m"], i["refends_m"], i["levels"], i["wall_height_m"]
    L_sem = round(per + ref, 2)

    fondations = [
        _line("Fouilles en rigole 60 × 60 cm (mise hors gel)",
              f"{L_sem} ml sous murs porteurs (périmètre {per} m + refends {ref} m)",
              "m³", L_sem * 0.6 * 0.6, "fouilles"),
        _line("Béton de propreté ép. 5 cm",
              "C16/20 — largeur 60 cm en fond de fouille", "m³",
              L_sem * 0.6 * 0.05, "beton_proprete"),
        _line("Semelles filantes BA 60 × 30 cm",
              f"C25/30 — {L_sem} ml sous tous murs porteurs", "m³",
              L_sem * R["semelle_width_m"] * R["semelle_height_m"], "beton_semelle"),
        _line("Aciers semelles — 3+3 HA10 filants + cadres HA6",
              f"{R['acier_semelle_kg_ml']} kg/ml × {L_sem} ml", "kg",
              L_sem * R["acier_semelle_kg_ml"], "acier_semelle"),
    ]

    slab_area = round(i["ground_floor_area_m2"] + i["upper_floors_area_m2"], 2)
    detail_slab = f"RDC {i['ground_floor_area_m2']} m²"
    if i["upper_floors_area_m2"] > 0:
        detail_slab += f" + étages {i['upper_floors_area_m2']} m²"
    planchers = [
        _line(f"Dalle / plancher BA ép. {int(R['slab_thickness_m'] * 100)} cm",
              f"C25/30 — {detail_slab}", "m³",
              slab_area * R["slab_thickness_m"], "beton_dalle"),
        _line("Treillis soudé ST25C + chapeaux",
              f"{R['acier_dalle_kg_m2']} kg/m² × {slab_area} m²", "kg",
              slab_area * R["acier_dalle_kg_m2"], "treillis_dalle"),
        _line("Coffrage de rives de dalle", "périmètre dalle RDC", "ml", per, "coffrage_rive"),
    ]

    wall_gross = round((per + ref) * h * lv, 2)
    wall_net = round(max(0.0, wall_gross - i["openings_area_m2"]), 2)
    bricks = math.ceil(wall_net * R["bricks_per_m2"])
    ch_h = round((per + ref) * lv, 2)
    n_raid = max(4, round(per / 5))
    ch_v = round(n_raid * h * lv, 2)
    ch_beton = (ch_h + ch_v) * 0.2 * 0.2
    lint_ml = round(i["openings_count"] * (i["avg_opening_width_m"] + 0.40), 2)
    murs = [
        _line(f"Murs en brique isobrique ép. {int(R['wall_thickness_m'] * 100)} cm",
              f"{bricks} briques (≈ {R['bricks_per_m2']} u/m²) — pose joint mince — "
              f"{wall_gross} m² bruts − {i['openings_area_m2']} m² d'ouvertures",
              "m²", wall_net, "mur_isobrique"),
        _line("Chaînages horizontaux + raidisseurs verticaux BA 20 × 20",
              f"{ch_h} ml CH + {ch_v} ml CV ({n_raid} raidisseurs/niveau)", "m³",
              ch_beton, "chainage_beton"),
        _line("Aciers chaînages — 4 HA10 + cadres HA6",
              f"{R['acier_chainage_kg_ml']} kg/ml × {round(ch_h + ch_v, 1)} ml", "kg",
              (ch_h + ch_v) * R["acier_chainage_kg_ml"], "acier_chainage"),
        _line("Linteaux BA sur ouvertures",
              f"{i['openings_count']} ouvertures (larg. moy. {i['avg_opening_width_m']} m "
              "+ 2 × 20 cm d'appuis)", "ml", lint_ml, "linteau"),
    ]

    escalier = []
    vol_esc = 0.0
    if i["stairs_count"] > 0:
        vol_esc = round(i["stairs_count"] * _stair_volume(h, stairs_steps), 2)
        escalier = [
            _line("Escalier béton armé coulé en place",
                  f"{i['stairs_count']} volée(s) — paillasse 15 cm + marches 17 × 28, larg. 1,00 m",
                  "m³", vol_esc, "escalier_beton"),
            _line("Aciers escalier",
                  f"{R['acier_escalier_kg_m3']} kg/m³ × {vol_esc} m³", "kg",
                  vol_esc * R["acier_escalier_kg_m3"], "acier_escalier"),
        ]

    lots = [l for l in [
        {"lot": "Terrassement & Fondations", "lines": fondations},
        {"lot": "Planchers / Dalles (ép. 15 cm)", "lines": planchers},
        {"lot": "Élévations — murs brique isobrique 20 cm", "lines": murs},
        {"lot": "Escalier béton", "lines": escalier},
    ] if l["lines"]]

    all_lines = [ln for l in lots for ln in l["lines"]]
    beton = round(sum(ln["qty"] for ln in all_lines if ln["unit"] == "m³"
                      and "Fouilles" not in ln["designation"]), 2)
    acier = round(sum(ln["qty"] for ln in all_lines if ln["unit"] == "kg"), 1)
    ht = round(sum(ln["total"] for ln in all_lines), 2)
    tva = round(ht * TVA_RATE, 2)
    return {"lots": lots,
            "totals": {"beton_m3": beton, "acier_kg": acier, "briques_u": bricks,
                       "murs_net_m2": wall_net, "semelles_ml": L_sem,
                       "ht": ht, "tva_rate": TVA_RATE, "tva": tva,
                       "ttc": round(ht + tva, 2)}}


def build_study(merged: dict, overrides: dict, rooms_surface_m2: float = 0.0,
                pages_analyzed: list[int] | None = None) -> dict:
    """Assemble l'étude complète : demandes lues + hypothèses + devis quantifié."""
    inputs, sources = _resolve_inputs(merged, overrides, rooms_surface_m2)
    computed = compute_gros_oeuvre(inputs, merged.get("stairs_steps"))
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pages_analyzed": pages_analyzed or [],
        "nature_travaux": merged.get("nature_travaux"),
        "demandes": merged.get("demandes") or [],
        "texts": merged.get("texts") or [],
        "warnings": merged.get("warnings") or [],
        "confidence": merged.get("confidence", 0.0),
        "inputs": inputs,
        "input_sources": sources,
        "rules": RULES,
        **computed,
    }
