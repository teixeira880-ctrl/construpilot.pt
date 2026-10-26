"""Étude Permis de Construire (PC) — lecture IA + calculs gros œuvre déterministes.

L'IA lit chaque page du PC (texte, plans, notice) et extrait les données du projet.
Les quantités/prix sont calculés ici avec des RÈGLES FIXES validées par l'utilisateur :
- Semelles filantes : toujours 60 × 30 cm (périmètre + refends porteurs)
- Plancher / dalle : épaisseur 15 cm
- Murs : brique isobrique ép. 20 cm
- Escaliers : béton armé
- Aciers : semelles 3+3 HA10 + cadres HA6 (15 kg/ml), dalle ST25C + chapeaux (14 kg/m²),
  escalier 100 kg/m³, chaînages 4 HA10 + cadres HA6 (3,6 kg/ml)
- FORFAITS calibrés sur coûts réels utilisateur (06/2026) : terrassement 15 k€,
  fondations ≈ 12 k€, plancher étage 15 k€/niveau, charpente trad. 20 k€,
  couverture tuiles 14 k€, menuiseries ext. 18 k€, chantier/engins/échafaudage
  ≈ 10,5 k€ — main d'œuvre 35 €/h.
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from engines.llm_keys import studies_key
from engines.plan_ai import plan_model

logger = logging.getLogger(__name__)

# ---- Règles fixes (validées utilisateur) ---------------------------------
RULES = {
    "semelle_width_m": 0.60,
    "semelle_height_m": 0.30,
    "slab_thickness_m": 0.15,
    "wall_material": "Tijolo térmico",
    "wall_thickness_m": 0.20,
    "stairs_material": "Betão armado",
    "acier_semelle_kg_ml": 15.0,     # 3+3 HA10 filants + cadres HA6
    "acier_dalle_kg_m2": 14.0,       # treillis ST25C + chapeaux
    "acier_escalier_kg_m3": 100.0,
    "acier_chainage_kg_ml": 3.6,     # 4 HA10 + cadres HA6
    "bricks_per_m2": 9.5,            # bloc 500 × 212 — ép. 200
}

# ---- Prix unitaires (€ HT / unité) — forfaits calibrés sur coûts réels user
PC_UNIT_PRICES = {
    "terrassement_complet": {"mat": 7500.0, "mo": 7500.0},   # forfait ≈ 15 000 €
    "beton_proprete": {"mat": 125.0, "mo": 55.0},  # m³ — C16/20
    "beton_semelle":  {"mat": 145.0, "mo": 75.0},  # m³ — C25/30 coulé
    "acier_semelle":  {"mat": 1.45, "mo": 0.55},   # kg — HA façonné posé
    "fondations_moe": {"mat": 1200.0, "mo": 7000.0},  # forfait — implantation + coffrage + coulage
    "beton_dalle":    {"mat": 150.0, "mo": 90.0},  # m³ — C25/30 + pompage
    "treillis_dalle": {"mat": 1.35, "mo": 0.40},   # kg — ST25C posé
    "coffrage_rive":  {"mat": 6.0,  "mo": 14.0},   # ml
    "plancher_etage": {"mat": 9500.0, "mo": 5500.0},  # forfait/niveau ≈ 15 000 €
    "mur_isobrique":  {"mat": 38.0, "mo": 42.0},   # m² — brique 20 + colle joint mince
    "chainage_beton": {"mat": 160.0, "mo": 180.0}, # m³ — CH + CV coffrés
    "acier_chainage": {"mat": 1.45, "mo": 0.65},   # kg
    "linteau":        {"mat": 22.0, "mo": 28.0},   # ml — linteau BA 20×20 coulé
    "escalier_beton": {"mat": 165.0, "mo": 420.0}, # m³ — coffrage + coulage
    "acier_escalier": {"mat": 1.45, "mo": 0.70},   # kg
    "charpente_trad":    {"mat": 12500.0, "mo": 7500.0},  # forfait ≈ 20 000 €
    "couverture_tuiles": {"mat": 9500.0, "mo": 4500.0},   # forfait ≈ 14 000 €
    "menuiseries_ext":   {"mat": 14500.0, "mo": 3500.0},  # forfait ≈ 18 000 €
    "installation_chantier": {"mat": 1200.0, "mo": 800.0},  # forfait — base vie, clôture, benne
    "engins_levage":  {"mat": 5500.0, "mo": 500.0},  # forfait — grue/manuscopique, bétonnière, outillage
    "echafaudage":    {"mat": 2200.0, "mo": 300.0},  # forfait — location + montage/démontage
    "protection_securite": {"mat": 1500.0, "mo": 900.0},  # forfait — garde-corps, filets, signalisation, PPSPS
}

TVA_RATE = 0.23  # construção nova — taxa normal de IVA (Portugal continental)

# ---- Planning de chantier ---------------------------------------------
CREW_SIZE = 3
HOURLY_RATE_EUR = 35.0  # coût horaire MO — convertit les PU MO en heures

PLANNING_PHASES = [
    ("Instalação de estaleiro — instalações sociais, vedação, máquinas, andaime",
     ["Instalação de estaleiro", "Máquinas", "Andaime", "Protection collective"], 0),
    ("Movimento de terras — decapagem, abertura de valas, aterros", ["Movimento de terras completo"], 0),
    ("Fundações — betão de limpeza + sapatas contínuas 60×30 + aços",
     ["propreté", "Sapatas contínuas", "Aços sapatas", "Execução de fundações"], 7),
    ("Laje térrea R/C esp. 15 cm + malha",
     ["Laje térrea R/C", "Malha", "Cofragem de bordas"], 7),
    ("Alvenarias — paredes de tijolo térmico + lintéis + padieiras",
     ["tijolo térmico", "Lintéis", "Padieiras"], 2),
    ("Laje de piso — vigotas e abobadilhas + lâmina de compressão",
     ["Laje de piso"], 7),
    ("Escada betão armado", ["Escada de betão", "Aços escada"], 7),
    ("Carpintaria tradicional", ["Carpintaria tradicional"], 0),
    ("Cobertura de telhas", ["Cobertura de telhas"], 0),
    ("Caixilharia exterior — aplicação das janelas", ["Caixilharia exterior"], 0),
]


def compute_planning(lots: list[dict], crew_size: int = CREW_SIZE,
                     hourly_rate: float = HOURLY_RATE_EUR) -> dict:
    """Planning séquentiel des corps d'état : durées issues des heures MO + séchages."""
    all_lines = [ln for l in lots for ln in l["lines"]]
    phases: list[dict] = []
    cursor = 1
    for name, keys, cure in PLANNING_PHASES:
        tasks = [ln for ln in all_lines
                 if any(k.lower() in ln["designation"].lower() for k in keys)]
        if not tasks:
            continue
        hours = sum(ln["total_mo"] for ln in tasks) / hourly_rate
        work_days = max(1, math.ceil(hours / (crew_size * 8)))
        phases.append({"name": name, "tasks": [t["designation"] for t in tasks],
                       "hours": round(hours, 1), "work_days": work_days,
                       "cure_days": cure, "start_day": cursor,
                       "end_day": cursor + work_days - 1})
        cursor += work_days + cure
    return {"crew_size": crew_size, "hourly_rate_eur": hourly_rate,
            "phases": phases,
            "total_work_days": sum(p["work_days"] for p in phases),
            "total_cure_days": sum(p["cure_days"] for p in phases),
            "total_days": cursor - 1,
            "total_weeks": round((cursor - 1) / 5, 1)}

PC_PROMPT = "És um **orçamentista da construção especialista em projetos de licenciamento portugueses (RJUE)**\ncom 25 anos de experiência. Analisas UMA página de um processo de licenciamento\n(planta de implantação, planta de piso, alçado, corte, memória descritiva, formulários camarários…).\n\nA tua missão: IDENTIFICAR o texto, LÊ-LO, COMPREENDER o que é pedido e extrair\ntodos os dados necessários à orçamentação da estrutura e alvenarias.\n\nDevolve ESTRITAMENTE JSON (sem markdown) com ESTA estrutura:\n\n{\n  \"page_kind\": \"plan_niveau\" | \"plan_masse\" | \"facade\" | \"coupe\" | \"notice\" | \"cerfa\" | \"autre\",\n  \"texts_verbatim\": [\"textos-chave lidos na página, copiados palavra por palavra (máx. 15)\"],\n  \"demandes\": [\"o que o projeto pede, de forma clara (ex.: \'Construção de uma moradia unifamiliar de 2 pisos com 120 m²\')\"],\n  \"project\": {\n    \"nature_travaux\": \"construction maison neuve\" | \"extension\" | \"surélévation\" | null,\n    \"surface_plancher_m2\": 120.0,\n    \"emprise_au_sol_m2\": 80.0,\n    \"nb_niveaux\": 2,\n    \"hauteur_totale_m\": 6.5,\n    \"hauteur_sous_plafond_m\": 2.5\n  },\n  \"geometry\": {\n    \"perimeter_ext_m\": 38.0,\n    \"refends_porteurs_m\": 9.0,\n    \"ground_floor_area_m2\": 80.0,\n    \"upper_floors_area_m2\": 40.0\n  },\n  \"openings\": {\"count\": 12, \"total_area_m2\": 22.0, \"avg_width_m\": 1.2},\n  \"stairs\": {\"count\": 1, \"type\": \"droit\" | \"quart-tournant\" | null, \"steps\": 15, \"footprint_m2\": 4.5},\n  \"warnings\": [\"planta desfocada\", \"escala ausente\", ...],\n  \"confidence\": 0.0-1.0\n}\n\nREGRAS:\n- Lê TODOS os textos visíveis (cotas, áreas escritas, memória descritiva, legenda, formulários).\n- `demandes` = reformulação clara do que o requerente pede (natureza, área, pisos), em português europeu.\n- Utiliza as cotas escritas para estimar o perímetro e as paredes interiores resistentes.\n- Se um valor não for determinável NESTA página, põe null (nunca 0 por omissão).\n- Ordens de grandeza realistas: pé-direito 2,50 m (mínimo RGEU 2,40 m), piso corrente ~2,70 m bruto.\n- Responde APENAS com o JSON."


async def analyze_pc_page(image_b64_png: str) -> dict:
    """Analyse UNE page d'un PC via GPT-Vision. Retourne toujours un dict."""
    api_key = studies_key(plan_model()[0])
    if not api_key:
        return {"error": "EMERGENT_LLM_KEY absent", "confidence": 0.0}
    try:
        from emergentintegrations.llm.chat import ImageContent, UserMessage

        from engines.expenses.metering import MeteredChat as LlmChat
        chat = LlmChat(api_key=api_key, session_id="pc-study", expense_feature="planning_study",
                       system_message="Respondes sempre em JSON estrito, sem markdown.",
                       ).with_model(*plan_model())
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
                  "medições da planta" if rooms_surface_m2 > 0 else "estimé")
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


def merge_unit_prices(custom: dict | None) -> dict:
    """Fusionne les prix personnalisés (réglages user) avec les défauts."""
    if not custom:
        return PC_UNIT_PRICES
    out = {}
    for k, v in PC_UNIT_PRICES.items():
        c = custom.get(k) or {}
        out[k] = {"mat": float(c.get("mat", v["mat"])), "mo": float(c.get("mo", v["mo"]))}
    return out


def _line(designation: str, detail: str, unit: str, qty: float, price_key: str,
          prices: dict | None = None) -> dict:
    p = (prices or PC_UNIT_PRICES)[price_key]
    qty = round(qty, 2)
    t_mat = round(qty * p["mat"], 2)
    t_mo = round(qty * p["mo"], 2)
    return {"key": price_key, "designation": designation, "detail": detail,
            "unit": unit, "qty": qty,
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


def compute_gros_oeuvre(i: dict, stairs_steps: int | None = None,
                        prices: dict | None = None) -> dict:
    """Calcul déterministe des quantités + devis détaillé (règles fixes)."""
    R = RULES
    P = prices or PC_UNIT_PRICES
    per, ref, lv, h = i["perimeter_m"], i["refends_m"], i["levels"], i["wall_height_m"]
    L_sem = round(per + ref, 2)
    n_up = lv - 1 if i["upper_floors_area_m2"] > 0 else 0

    terrassement = [
        _line("Movimento de terras completo — decapagem, abertura de valas, remoção e aterros",
              f"emprise {i['ground_floor_area_m2']} m² — {L_sem} ml de valas 60 × 60 sob paredes resistentes (valor global)", "forfait", 1, "terrassement_complet", P),
    ]

    fondations = [
        _line("Betão de limpeza esp. 5 cm",
              "C16/20 — largura 60 cm no fundo da vala", "m³",
              L_sem * 0.6 * 0.05, "beton_proprete", P),
        _line("Sapatas contínuas BA 60 × 30 cm",
              f'C25/30 — {L_sem} ml sob todas as paredes resistentes', "m³",
              L_sem * R["semelle_width_m"] * R["semelle_height_m"], "beton_semelle", P),
        _line("Aços das sapatas — 3+3 Ø10 contínuos + estribos Ø6",
              f"{R['acier_semelle_kg_ml']} kg/ml × {L_sem} ml", "kg",
              L_sem * R["acier_semelle_kg_ml"], "acier_semelle", P),
        _line("Execução das fundações — implantação, cofragem, acerto e betonagem",
              "valor global mão de obra + consumíveis", "forfait", 1, "fondations_moe", P),
    ]

    ground = i["ground_floor_area_m2"]
    planchers = [
        _line(f"Laje térrea R/C — laje BA esp. {int(R['slab_thickness_m'] * 100)} cm",
              f"C25/30 — {ground} m²", "m³",
              ground * R["slab_thickness_m"], "beton_dalle", P),
        _line("Malha eletrossoldada AQ38 + armaduras superiores",
              f"{R['acier_dalle_kg_m2']} kg/m² × {ground} m²", "kg",
              ground * R["acier_dalle_kg_m2"], "treillis_dalle", P),
        _line("Cofragem dos bordos da laje", "perímetro da laje R/C", "ml", per, "coffrage_rive", P),
    ]
    if n_up:
        planchers.append(
            _line("Laje de piso completa — vigotas e abobadilhas + lâmina de compressão",
                  f"{i['upper_floors_area_m2']} m² — escoramento incluído ({n_up} piso(s), valor global/piso)",
                  "forfait", n_up, "plancher_etage", P))

    wall_gross = round((per + ref) * h * lv, 2)
    wall_net = round(max(0.0, wall_gross - i["openings_area_m2"]), 2)
    bricks = math.ceil(wall_net * R["bricks_per_m2"])
    ch_h = round((per + ref) * lv, 2)
    n_raid = max(4, round(per / 5))
    ch_v = round(n_raid * h * lv, 2)
    ch_beton = (ch_h + ch_v) * 0.2 * 0.2
    lint_ml = round(i["openings_count"] * (i["avg_opening_width_m"] + 0.40), 2)
    murs = [
        _line(f"Paredes em tijolo térmico esp. {int(R['wall_thickness_m'] * 100)} cm",
              f"{bricks} briques (≈ {R['bricks_per_m2']} u/m²) — pose joint mince — {wall_gross} m² brutos − {i['openings_area_m2']} m² de vãos",
              "m²", wall_net, "mur_isobrique", P),
        _line("Lintéis horizontais + pilaretes verticais BA 20 × 20",
              f"{ch_h} ml CH + {ch_v} ml CV ({n_raid} pilaretes/piso)", "m³",
              ch_beton, "chainage_beton", P),
        _line("Aços dos lintéis — 4 Ø10 + estribos Ø6",
              f"{R['acier_chainage_kg_ml']} kg/ml × {round(ch_h + ch_v, 1)} ml", "kg",
              (ch_h + ch_v) * R["acier_chainage_kg_ml"], "acier_chainage", P),
        _line("Padieiras BA sobre vãos",
              f"{i['openings_count']} vãos (larg. média {i['avg_opening_width_m']} m + 2 × 20 cm de apoio)", "ml", lint_ml, "linteau", P),
    ]

    escalier = []
    vol_esc = 0.0
    if i["stairs_count"] > 0:
        vol_esc = round(i["stairs_count"] * _stair_volume(h, stairs_steps), 2)
        escalier = [
            _line("Escada de betão armado betonada no local",
                  f"{i['stairs_count']} lanço(s) — lanço 15 cm + degraus 17 × 28, larg. 1,00 m",
                  "m³", vol_esc, "escalier_beton", P),
            _line("Aços escada",
                  f"{R['acier_escalier_kg_m3']} kg/m³ × {vol_esc} m³", "kg",
                  vol_esc * R["acier_escalier_kg_m3"], "acier_escalier", P),
        ]

    toiture = [
        _line("Estrutura de cobertura tradicional — madeira maciça montada",
              f"cobertura sobre implantação {i['ground_floor_area_m2']} m² (valor global)",
              "forfait", 1, "charpente_trad", P),
        _line("Cobertura em telha — telhas, subtelha, ripas e cumeeira",
              "fornecimento + aplicação (valor global)", "forfait", 1, "couverture_tuiles", P),
    ]

    menuiseries = [
        _line("Caixilharia exterior — janelas e portas-janelas aplicadas",
              f"{i['openings_count']} ouvertures (≈ {i['openings_area_m2']} m² de vãos, valor global)", "forfait", 1, "menuiseries_ext", P),
    ]

    chantier = [
        _line("Instalação de estaleiro — instalações sociais, vedação, contentor de entulho",
              "valor global pela duração da obra", "forfait", 1, "installation_chantier", P),
        _line("Máquinas e equipamentos — grua/manipulador telescópico, betoneira, ferramentas",
              "aluguer pela duração da estrutura (valor global)", "forfait", 1, "engins_levage", P),
        _line("Andaime periférico — aluguer, montagem e desmontagem",
              f'perímetro {per} m (valor global)', "forfait", 1, "echafaudage", P),
        _line("Proteção coletiva e segurança — guarda-corpos periféricos, redes, sinalização e plano de segurança e saúde", "valor global pela duração da obra", "forfait", 1,
              "protection_securite", P),
    ]

    lots = [l for l in [
        {"lot": "Instalação de estaleiro e máquinas", "lines": chantier},
        {"lot": "Movimentação de terras", "lines": terrassement},
        {"lot": "Fondations", "lines": fondations},
        {"lot": "Pavimentos / Lajes", "lines": planchers},
        {"lot": "Alvenarias — paredes de tijolo térmico 20 cm", "lines": murs},
        {"lot": "Escada de betão", "lines": escalier},
        {"lot": "Estrutura de cobertura e cobertura", "lines": toiture},
        {"lot": "Caixilharia exterior", "lines": menuiseries},
    ] if l["lines"]]

    all_lines = [ln for l in lots for ln in l["lines"]]
    beton = round(sum(ln["qty"] for ln in all_lines if ln["unit"] == "m³"), 2)
    acier = round(sum(ln["qty"] for ln in all_lines if ln["unit"] == "kg"), 1)
    ht = round(sum(ln["total"] for ln in all_lines), 2)
    tva = round(ht * TVA_RATE, 2)
    return {"lots": lots,
            "totals": {"beton_m3": beton, "acier_kg": acier, "briques_u": bricks,
                       "murs_net_m2": wall_net, "semelles_ml": L_sem,
                       "ht": ht, "tva_rate": TVA_RATE, "tva": tva,
                       "ttc": round(ht + tva, 2)}}


def compute_levels_breakdown(i: dict, prices: dict | None = None,
                             stairs_steps: int | None = None) -> list[dict]:
    """Quantités détaillées niveau par niveau (Fondations, RDC, R+1…) pour phaser
    les commandes. Mêmes règles fixes que le devis global."""
    R = RULES
    P = prices or PC_UNIT_PRICES
    per, ref, lv, h = i["perimeter_m"], i["refends_m"], i["levels"], i["wall_height_m"]
    L_sem = round(per + ref, 2)
    n_raid = max(4, round(per / 5))
    open_per_lvl = round(i["openings_area_m2"] / lv, 2)
    base_open, extra_open = divmod(int(i["openings_count"]), lv)
    stairs_left = i["stairs_count"]

    def summarize(name: str, lines: list[dict], briques: int, murs_m2: float) -> dict:
        return {"name": name, "lines": lines,
                "beton_m3": round(sum(ln["qty"] for ln in lines if ln["unit"] == "m³"), 2),
                "acier_kg": round(sum(ln["qty"] for ln in lines if ln["unit"] == "kg"), 1),
                "briques_u": briques, "murs_m2": murs_m2,
                "ht": round(sum(ln["total"] for ln in lines), 2)}

    out = [summarize("Estaleiro, movimento de terras e fundações", [
        _line("Instalação de estaleiro — instalações sociais, vedação, contentor de resíduos",
              "forfait", "forfait", 1, "installation_chantier", P),
        _line("Máquinas e equipamentos — grua/manipulador telescópico, betoneira, ferramentas",
              "forfait", "forfait", 1, "engins_levage", P),
        _line("Andaime periférico — aluguer e montagem",
              "forfait", "forfait", 1, "echafaudage", P),
        _line("Proteção coletiva e segurança — guarda-corpos, redes, sinalização e plano de segurança e saúde",
              "forfait", "forfait", 1, "protection_securite", P),
        _line("Movimento de terras completo — decapagem, valas, remoção e aterros",
              f'{L_sem} ml de valas 60 × 60', "forfait", 1, "terrassement_complet", P),
        _line("Betão de limpeza esp. 5 cm", "C16/20", "m³",
              L_sem * 0.6 * 0.05, "beton_proprete", P),
        _line("Sapatas contínuas BA 60 × 30 cm", f"{L_sem} ml", "m³",
              L_sem * R["semelle_width_m"] * R["semelle_height_m"], "beton_semelle", P),
        _line("Aços das sapatas (3+3 Ø10 + estribos Ø6)", f"{R['acier_semelle_kg_ml']} kg/ml",
              "kg", L_sem * R["acier_semelle_kg_ml"], "acier_semelle", P),
        _line("Execução das fundações — implantação, cofragem, betonagem",
              "forfait", "forfait", 1, "fondations_moe", P),
    ], 0, 0.0)]

    for k in range(lv):
        name = "RDC" if k == 0 else f"R+{k}"
        wall_net = round(max(0.0, (per + ref) * h - open_per_lvl), 2)
        briques = math.ceil(wall_net * R["bricks_per_m2"])
        ch_ml = round((per + ref) + n_raid * h, 2)
        if k == 0:
            ground = i["ground_floor_area_m2"]
            lines = [
                _line(f"Laje térrea R/C — laje BA esp. {int(R['slab_thickness_m'] * 100)} cm",
                      f"{ground} m²", "m³", ground * R["slab_thickness_m"],
                      "beton_dalle", P),
                _line("Malha eletrossoldada AQ38 + armaduras superiores", f"{R['acier_dalle_kg_m2']} kg/m²",
                      "kg", ground * R["acier_dalle_kg_m2"], "treillis_dalle", P),
                _line("Cofragem dos bordos da laje", "perímetro do R/C", "ml",
                      per, "coffrage_rive", P),
            ]
        elif i["upper_floors_area_m2"] > 0:
            lines = [
                _line("Laje de piso completa — vigotas e abobadilhas + lâmina de compressão",
                      f"≈ {round(i['upper_floors_area_m2'] / max(1, lv - 1), 2)} m² — escoramento incluído (valor global)", "forfait", 1, "plancher_etage", P),
            ]
        else:
            lines = []
        lines += [
            _line(f"Paredes de tijolo térmico esp. {int(R['wall_thickness_m'] * 100)} cm",
                  f"{briques} briques", "m²", wall_net, "mur_isobrique", P),
            _line("Lintéis horizontais + pilaretes (BA 20 × 20)", f"{ch_ml} ml", "m³",
                  ch_ml * 0.2 * 0.2, "chainage_beton", P),
            _line("Aços dos lintéis (4 Ø10 + estribos Ø6)",
                  f"{R['acier_chainage_kg_ml']} kg/ml", "kg",
                  ch_ml * R["acier_chainage_kg_ml"], "acier_chainage", P),
        ]
        n_open_lvl = base_open + (1 if k < extra_open else 0)
        if n_open_lvl > 0:
            lines.append(
                _line("Padieiras BA sobre vãos", f"{n_open_lvl} vãos", "ml",
                      n_open_lvl * (i["avg_opening_width_m"] + 0.40), "linteau", P))
        if stairs_left > 0 and k < lv - 1:
            vol = _stair_volume(h, stairs_steps)
            lines += [
                _line(f'Escada de betão {name} → R+{k + 1}', "lanço 15 + degraus 17×28",
                      "m³", vol, "escalier_beton", P),
                _line("Aços escada", f"{R['acier_escalier_kg_m3']} kg/m³", "kg",
                      vol * R["acier_escalier_kg_m3"], "acier_escalier", P),
            ]
            stairs_left -= 1
        out.append(summarize(name, lines, briques, wall_net))

    out.append(summarize("Estrutura de cobertura, cobertura e caixilharia", [
        _line("Estrutura de cobertura tradicional — madeira maciça montada", "forfait",
              "forfait", 1, "charpente_trad", P),
        _line("Cobertura em telha — telhas, subtelha, ripas e cumeeira", "forfait",
              "forfait", 1, "couverture_tuiles", P),
        _line("Caixilharia exterior — janelas e portas-janelas aplicadas",
              f"{i['openings_count']} vãos", "forfait", 1, "menuiseries_ext", P),
    ], 0, 0.0))
    return out


# ---- Bon de commande fournisseur (par niveau) -----------------------------
ORDER_ITEMS = {
    "beton_proprete": ("Betão de limpeza C16/20", "m³"),
    "beton_semelle": ("Betão pronto C25/30 — sapatas", "m³"),
    "beton_dalle": ("Betão pronto C25/30 — laje / pavimento", "m³"),
    "chainage_beton": ("Betão C25/30 — lintéis e pilaretes", "m³"),
    "escalier_beton": ("Betão C25/30 — escada", "m³"),
    "acier_semelle": ("Aços A500 moldados — sapatas (3+3 Ø10 + estribos Ø6)", "kg"),
    "acier_chainage": ("Aços A500 moldados — lintéis (4 Ø10 + estribos Ø6)", "kg"),
    "acier_escalier": ("Aços A500 moldados — escada", "kg"),
    "treillis_dalle": ("Malha eletrossoldada AQ38 (painéis)", "kg"),
    "mur_isobrique": ("Tijolos térmicos esp. 20 cm", "u"),
    "linteau": ("Padieiras / cofragem BA 20 × 20", "ml"),
    "coffrage_rive": ("Tábuas de cofragem de bordos", "ml"),
    "plancher_etage": ("Laje de vigotas e abobadilhas — piso (fornecimento completo)", "forfait"),
    "charpente_trad": ("Estrutura de cobertura tradicional (fornecimento de madeira)", "forfait"),
    "couverture_tuiles": ("Telhas + subtelha + ripas (fornecimento)", "forfait"),
    "menuiseries_ext": ("Caixilharia exterior — janelas (fornecimento)", "forfait"),
}
WASTE_FACTOR = 1.05  # +5 % de chutes / pertes


def _order_round(qty: float, unit: str) -> float:
    if unit == "m³":
        return math.ceil(qty * 2) / 2   # au 0,5 m³ supérieur
    if unit == "kg":
        return float(math.ceil(qty / 5) * 5)
    return float(math.ceil(qty))


def build_purchase_order_items(level: dict, prices: dict | None = None) -> list[dict]:
    """Convertit les lignes d'un niveau en articles matériaux à commander (+5 % chutes)."""
    P = prices or PC_UNIT_PRICES
    items: list[dict] = []
    for ln in level.get("lines") or []:
        key = ln.get("key")
        if key not in ORDER_ITEMS:
            continue
        name, unit = ORDER_ITEMS[key]
        pu = P.get(key, PC_UNIT_PRICES.get(key, {})).get("mat", 0)
        if key == "mur_isobrique":
            qty = _order_round(ln["qty"] * RULES["bricks_per_m2"] * WASTE_FACTOR, "u")
            pu = round(P[key]["mat"] / RULES["bricks_per_m2"], 2)  # €/brique indicatif
            items.append({"designation": name, "unit": unit, "qty": qty,
                          "pu_mat": pu, "total": round(qty * pu, 2)})
            colle = _order_round(ln["qty"] * 1.5 * WASTE_FACTOR, "kg")
            items.append({"designation": "Cola / argamassa de junta fina", "unit": "kg",
                          "qty": colle, "pu_mat": 0.85,
                          "total": round(colle * 0.85, 2)})
            continue
        if pu <= 0:
            continue
        qty = ln["qty"] if unit == "forfait" else _order_round(ln["qty"] * WASTE_FACTOR, unit)
        items.append({"designation": name, "unit": unit, "qty": qty,
                      "pu_mat": pu, "total": round(qty * pu, 2)})
    return items


def schedule_with_dates(planning: dict, start_iso: str) -> list[dict]:
    """Dates réelles des phases : jours ouvrés (week-ends sautés) + séchage calendaire."""
    from datetime import date, timedelta

    def skip_we(x: "date") -> "date":
        while x.weekday() >= 5:
            x += timedelta(days=1)
        return x

    cursor = skip_we(date.fromisoformat(start_iso))
    rows = []
    for ph in planning.get("phases") or []:
        ws = skip_we(cursor)
        e = ws
        remaining = ph["work_days"] - 1
        while remaining > 0:
            e += timedelta(days=1)
            if e.weekday() < 5:
                remaining -= 1
        ce = e + timedelta(days=ph["cure_days"])
        rows.append({**ph, "work_start": ws.isoformat(), "work_end": e.isoformat(),
                     "cure_end": ce.isoformat()})
        cursor = ce + timedelta(days=1)
    return rows


DEFAULT_MARGIN_PCT = 30.0


def apply_margin(prices: dict, pct: float) -> dict:
    """Prix de vente = coût × (1 + marge %). Retourne un nouveau barème."""
    if not pct:
        return prices
    c = 1 + pct / 100.0
    return {k: {"mat": round(v["mat"] * c, 2), "mo": round(v["mo"] * c, 2)}
            for k, v in prices.items()}


def compute_study_costing(inputs: dict, stairs_steps: int | None, prices: dict,
                          margin_pct: float, crew: int, rate: float) -> tuple:
    """Devis client aux prix de vente margés + planning basé sur les coûts MO réels."""
    sale_prices = apply_margin(prices, margin_pct)
    computed = compute_gros_oeuvre(inputs, stairs_steps, sale_prices)
    raw = compute_gros_oeuvre(inputs, stairs_steps, prices) if margin_pct else computed
    computed["totals"].update(
        marge_pct=round(margin_pct, 1),
        cout_ht=raw["totals"]["ht"],
        marge_eur=round(computed["totals"]["ht"] - raw["totals"]["ht"], 2))
    planning = compute_planning(raw["lots"], crew, rate)
    levels_breakdown = compute_levels_breakdown(inputs, sale_prices, stairs_steps)
    return computed, planning, levels_breakdown


def build_study(merged: dict, overrides: dict, rooms_surface_m2: float = 0.0,
                pages_analyzed: list[int] | None = None,
                settings: dict | None = None) -> dict:
    """Assemble l'étude complète : demandes lues + hypothèses + devis quantifié."""
    settings = settings or {}
    prices = merge_unit_prices(settings.get("unit_prices"))
    crew = int(settings.get("crew_size") or CREW_SIZE)
    rate = float(settings.get("hourly_rate_eur") or HOURLY_RATE_EUR)
    margin = settings.get("margin_pct")
    margin = DEFAULT_MARGIN_PCT if margin is None else float(margin)
    inputs, sources = _resolve_inputs(merged, overrides, rooms_surface_m2)
    computed, planning, levels_breakdown = compute_study_costing(
        inputs, merged.get("stairs_steps"), prices, margin, crew, rate)
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
        "custom_pricing": bool(settings.get("unit_prices")),
        "planning": planning,
        "levels_breakdown": levels_breakdown,
        **computed,
    }
