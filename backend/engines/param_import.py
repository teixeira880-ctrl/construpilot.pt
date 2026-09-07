"""Bibliothèque paramétrique ConstruPilot — ouvrages composés (recettes).

Parse le fichier v3 (Excel/CSV) : chaque ouvrage (base_code) = plusieurs lignes de
recette (composant + formule de quantité + métier + heures MO + % pertes).
Fournit aussi l'évaluateur de formules et les valeurs par défaut (taux horaires
2026, coefficients régionaux, variables moteur, prix matériaux de départ).
"""
from __future__ import annotations

import ast
import csv
import io
import operator as op
import re
import unicodedata

LINE_FIELDS = [
    "recipe_line_id", "base_code", "famille", "variables_entree", "pertes_pct",
    "metier_mo", "heures_mo_unite", "ordre", "composant", "unite_composant",
    "formule_quantite", "quantite_defaut", "requete_api_fournisseur",
    "note_technique", "supplier_price_ht", "date_base", "note_recette",
]


def _norm(s: str) -> str:
    s = (s or "").replace("œ", "oe").replace("’", " ").replace("'", " ")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()


def _num(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().replace("\xa0", "").replace(" ", "").replace("€", "").replace(",", ".")
    if not s:
        return None
    try:
        return float(re.sub(r"[^0-9.\-]", "", s))
    except ValueError:
        return None


_ALLOWED = re.compile(r"^[0-9a-zA-Z_+\-*/(). ]+$")

_AST_BINOPS = {ast.Add: op.add, ast.Sub: op.sub, ast.Mult: op.mul,
               ast.Div: op.truediv, ast.Pow: op.pow, ast.Mod: op.mod}
_AST_UNARY = {ast.UAdd: op.pos, ast.USub: op.neg}


def _eval_node(node, variables: dict):
    if isinstance(node, ast.Expression):
        return _eval_node(node.body, variables)
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError("literal non numérique")
    if isinstance(node, ast.Name):
        return float(variables.get(node.id, 0) or 0)
    if isinstance(node, ast.BinOp) and type(node.op) in _AST_BINOPS:
        return _AST_BINOPS[type(node.op)](_eval_node(node.left, variables),
                                          _eval_node(node.right, variables))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _AST_UNARY:
        return _AST_UNARY[type(node.op)](_eval_node(node.operand, variables))
    raise ValueError("expression non autorisée")


def eval_formula(expr: str, variables: dict) -> float | None:
    """Évalue une formule de quantité en toute sécurité (arithmétique + variables)."""
    if not expr:
        return None
    expr = str(expr).replace(",", ".").strip()
    if not _ALLOWED.match(expr):
        return None
    try:
        tree = ast.parse(expr, mode="eval")
        val = _eval_node(tree, {k: (v or 0) for k, v in variables.items()})
        return round(float(val), 4)
    except Exception:  # noqa: BLE001
        return None


def _row_to_line(row: dict) -> dict:
    def g(*keys):
        for k in keys:
            for rk in row:
                if _norm(rk) == _norm(k):
                    return row[rk]
        return None
    base = (str(g("base_code") or "").strip())
    if not base:
        return None
    return {
        "recipe_line_id": str(g("recipe_line_id") or "").strip(),
        "base_code": base,
        "famille": str(g("famille") or "").strip(),
        "variables_entree": str(g("variables_entree") or "").strip(),
        "pertes_pct": _num(g("pertes_pct")) or 0,
        "metier_mo": str(g("metier_mo") or "").strip(),
        "heures_mo_unite": _num(g("heures_mo_unite")) or 0,
        "ordre": int(_num(g("ordre")) or 0),
        "composant": str(g("composant") or "").strip(),
        "unite_composant": str(g("unite_composant") or "u").strip(),
        "formule_quantite": str(g("formule_quantite") or "").strip(),
        "quantite_defaut": _num(g("quantite_defaut")) or 0,
        "note_technique": str(g("note_technique") or "").strip()[:400],
        "note_recette": str(g("note_recette") or "").strip()[:400],
    }


def parse_param_library(content: bytes, filename: str) -> dict:
    fn = (filename or "").lower()
    lines_raw: list[dict] = []
    reference = {"variables": [], "api_rules": [], "constraints": []}
    if fn.endswith((".xlsx", ".xlsm", ".xls")):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        for ws in wb.worksheets:
            rows = [r for r in ws.iter_rows(values_only=True) if any(c is not None for c in r)]
            if not rows:
                continue
            hdr = [str(c) if c is not None else "" for c in rows[0]]
            nname = _norm(ws.title)
            dicts = [dict(zip(hdr, r)) for r in rows[1:]]
            if "recette" in nname or any(_norm(h) == "base_code" for h in hdr):
                lines_raw = dicts
            elif "variable" in nname:
                reference["variables"] = [{"variable": str(r[0] or ""), "unite": str(r[1] or ""),
                                           "description": str(r[2] or "") if len(r) > 2 else ""}
                                          for r in rows[1:]]
            elif "api" in nname or "regle" in nname:
                reference["api_rules"] = [[str(c or "") for c in r] for r in rows[1:]]
            elif "contrainte" in nname:
                reference["constraints"] = [[str(c or "") for c in r] for r in rows[1:]]
        wb.close()
    else:
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = content.decode("latin-1")
        delim = ";" if text[:4000].count(";") >= text[:4000].count(",") else ","
        lines_raw = list(csv.DictReader(io.StringIO(text), delimiter=delim))

    parsed = [x for x in (_row_to_line(r) for r in lines_raw) if x]
    if not parsed:
        raise ValueError("Aucune ligne de recette détectée (colonne 'base_code' introuvable).")
    ouvrages = {}
    for ln in parsed:
        o = ouvrages.setdefault(ln["base_code"], {
            "base_code": ln["base_code"], "famille": ln["famille"],
            "variables_entree": ln["variables_entree"], "metier_mo": ln["metier_mo"],
            "heures_mo_unite": ln["heures_mo_unite"], "pertes_pct": ln["pertes_pct"],
            "line_count": 0})
        o["line_count"] += 1
    return {"lines": parsed, "ouvrages": list(ouvrages.values()),
            "reference": reference, "count_lines": len(parsed),
            "count_ouvrages": len(ouvrages)}


# ---------------- Valeurs par défaut (éditables ensuite dans l'admin) ----------------

DEFAULT_LABOR_RATES = [
    {"metier": "Maçon", "low": 35, "mid": 52, "high": 70},
    {"metier": "Couvreur", "low": 40, "mid": 52, "high": 65},
    {"metier": "Étancheur", "low": 40, "mid": 52, "high": 65},
    {"metier": "Menuisier", "low": 40, "mid": 50, "high": 60},
    {"metier": "Plaquiste", "low": 35, "mid": 45, "high": 55},
    {"metier": "Carreleur", "low": 38, "mid": 48, "high": 60},
    {"metier": "Peintre", "low": 32, "mid": 42, "high": 55},
    {"metier": "Plombier", "low": 40, "mid": 55, "high": 70},
    {"metier": "Électricien", "low": 35, "mid": 55, "high": 75},
    {"metier": "Chauffagiste", "low": 45, "mid": 58, "high": 75},
    {"metier": "Ouvrier BTP", "low": 30, "mid": 38, "high": 48},
    {"metier": "Façadier", "low": 38, "mid": 48, "high": 62},
]

DEFAULT_REGIONAL_COEFS = [
    {"region": "idf", "label": "Île-de-France", "coef": 1.15},
    {"region": "grandes_villes", "label": "Grandes villes", "coef": 1.08},
    {"region": "standard", "label": "Standard / national", "coef": 1.00},
    {"region": "rural", "label": "Rural", "coef": 0.95},
]

DEFAULT_VARIABLES = {
    "surface_m2": 85, "surface_nette_m2": 72, "longueur_ml": 10, "hauteur_m": 2.5,
    "epaisseur_m": 0.2, "perimetre_ml": 38, "largeur_m": 4, "longueur_faitage_ml": 10,
    "longueur_rives_ml": 16, "surface_toiture_m2": 100, "pente_deg": 35, "densite_tuile_m2": 14,
    "entraxe_liteaux_m": 0.33, "entraxe_chevrons_m": 0.6, "nb_ouvertures": 4,
    "nb_chainages_verticaux": 4, "nb_barres_verticales": 4, "nb_lits_horizontaux": 3,
    "nb_briques_m2": 10, "rendement_m2_l": 10, "nb_points": 8,
    "longueur_moyenne_circuit_ml": 12, "nb_bouches": 4, "longueur_reseau_ml": 20,
    "quantite_ouvrage": 1,
}

DEFAULT_MATERIALS = [
    {"name": "Betão C25/30", "unit": "m³", "price": 145},
    {"name": "Betão de limpeza", "unit": "m³", "price": 120},
    {"name": "Armadura sapata contínua tipo S35", "unit": "ml", "price": 9},
    {"name": "Aço HA (armaduras)", "unit": "kg", "price": 1.6},
    {"name": "Arame de amarrar", "unit": "kg", "price": 3.5},
    {"name": "Calços de betão", "unit": "u", "price": 0.3},
    {"name": "Bloco de betão 20 cm", "unit": "u", "price": 1.6},
    {"name": "Argamassa / cola", "unit": "kg", "price": 0.4},
    {"name": "Placa de gesso cartonado BA13", "unit": "u", "price": 6.5},
    {"name": "Perfil / montante estrutura", "unit": "ml", "price": 2.2},
    {"name": "Lã de vidro", "unit": "m²", "price": 9},
    {"name": "Reboco / fita", "unit": "kg", "price": 1.2},
    {"name": "Telha", "unit": "u", "price": 1.1},
    {"name": "Ripa", "unit": "ml", "price": 1.4},
    {"name": "Vigota", "unit": "ml", "price": 3.5},
    {"name": "Sub-telha", "unit": "m²", "price": 3},
    {"name": "Membrana EPDM", "unit": "m²", "price": 18},
    {"name": "Janela PVC vidro duplo", "unit": "u", "price": 320},
    {"name": "Grés porcelânico", "unit": "m²", "price": 32},
    {"name": "Soalho flutuante", "unit": "m²", "price": 25},
    {"name": "Tinta acrílica", "unit": "L", "price": 6.5},
    {"name": "Cabo elétrico", "unit": "ml", "price": 1.2},
    {"name": "Ponto elétrico (aparelhagem)", "unit": "u", "price": 18},
    {"name": "Tubo PER / cobre", "unit": "ml", "price": 4.5},
    {"name": "Grelha VMC", "unit": "u", "price": 22},
    {"name": "Reboco de fachada", "unit": "m²", "price": 12},
]
