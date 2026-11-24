"""Plan d'installation de chantier (PIC) — moteur déterministe.

L'IA lit le plan de masse (emprise, bâtiment, accès) ; CE moteur calcule : position de
grue, portée nécessaire, charge admissible au rayon utile et en bout de flèche, implantation
des éléments (aire de livraison, bennes, stockage, base vie…), contrôles et points d'attention.

Aucune valeur de grue n'est inventée : le catalogue ne contient que des caractéristiques
publiées par les constructeurs (source indiquée par modèle). Quand la courbe de charge
complète n'est pas connue, la charge au rayon r est bornée par le moment en pointe
(Q_pointe × L / r), ce qui est PRUDENT : la vraie courbe est toujours au-dessus (les poids
propres du chariot et du moufle sont constants). Tout résultat reste à confirmer avec la
fiche technique du loueur (configuration, mouflage, mâture, ancrages).
"""
from __future__ import annotations

import math
import re

from shapely.geometry import Point, Polygon, box
from shapely.affinity import rotate as _rotate
from shapely.ops import unary_union

# ---------------------------------------------------------------------------
# Catalogue de grues (données constructeur publiées)
#   cmax_t     : charge maximale (t)
#   jib_max_m  : flèche maximale (m)
#   tips       : {longueur de flèche (m): charge en bout de flèche (t)}
#   curves     : {longueur de flèche (m): [(rayon m, charge t), …]} courbe de charge publiée
#   jibs       : longueurs de flèche publiées (m) ; absent = à confirmer avec le loueur
#   hsc_m      : hauteur sous crochet maximale publiée (grue autonome), si connue
# ---------------------------------------------------------------------------
_SRC_POTAIN = "Manitowoc / Potain — ficha técnica e gama publicadas"
_SRC_LIEBHERR = "Liebherr — ficha de produto publicada"

CRANES: dict[str, dict] = {
    "potain_igo_m14": {"label": "Potain Igo M 14", "family": "GMA", "cmax_t": 1.8, "jib_max_m": 22,
                       "tips": {22: 0.6}, "hsc_m": 19.0, "base_m": 4.0, "source": _SRC_POTAIN},
    "potain_igo_18": {"label": "Potain Igo 18", "family": "GMA", "cmax_t": 1.8, "jib_max_m": 24,
                      "tips": {24: 0.7}, "hsc_m": 19.1, "source": _SRC_POTAIN},
    "potain_igo_ma21": {"label": "Potain Igo MA 21", "family": "GMA", "cmax_t": 1.8, "jib_max_m": 26,
                        "tips": {26: 0.7}, "hsc_m": 19.3, "source": _SRC_POTAIN},
    "potain_igo_30": {"label": "Potain Igo 30", "family": "GMA", "cmax_t": 2.2, "jib_max_m": 30,
                      "tips": {30: 0.9}, "hsc_m": 21.0, "source": _SRC_POTAIN},
    "potain_igo_32": {"label": "Potain Igo 32", "family": "GMA", "cmax_t": 4.0, "jib_max_m": 30,
                      "tips": {30: 1.1}, "hsc_m": 22.0, "source": _SRC_POTAIN},
    "potain_igo_50": {"label": "Potain Igo 50", "family": "GMA", "cmax_t": 4.0, "jib_max_m": 40,
                      "tips": {40: 1.1}, "hsc_m": 23.2, "source": _SRC_POTAIN},
    "potain_igo_t99": {"label": "Potain Igo T 99", "family": "GMA", "cmax_t": 6.0, "jib_max_m": 48,
                       "tips": {48: 1.2}, "jibs": [31.7, 33.8, 40, 45, 48], "source": _SRC_POTAIN},
    "potain_igo_t139": {"label": "Potain Igo T 139", "family": "GMA", "cmax_t": 8.0, "jib_max_m": 55,
                        "tips": {55: 1.2}, "hsc_m": 40.7, "source": _SRC_POTAIN},
    "potain_mct_68": {"label": "Potain MCT 68", "family": "GME", "cmax_t": 3.0, "jib_max_m": 46,
                      "tips": {46: 1.1}, "hsc_m": 38.9, "source": _SRC_POTAIN},
    "potain_mct_88": {"label": "Potain MCT 88 (5 t)", "family": "GME", "cmax_t": 5.0, "jib_max_m": 52,
                      "tips": {52: 1.1}, "hsc_m": 39.4,
                      "curves": {52: [(13.7, 5.0), (15, 4.5), (17, 3.9), (20, 3.2), (22, 2.85),
                                      (26.4, 2.5), (27, 2.45), (30, 2.15), (32, 2.0), (35, 1.8),
                                      (37, 1.7), (40, 1.55), (42, 1.45), (45, 1.3), (47, 1.25),
                                      (50, 1.15), (52, 1.1)]},
                      "source": _SRC_POTAIN},
    "potain_mdt_109": {"label": "Potain MDT 109", "family": "GME", "cmax_t": 6.0, "jib_max_m": 55,
                       "tips": {55: 1.35}, "source": _SRC_POTAIN},
    "potain_mdt_159": {"label": "Potain MDT 159", "family": "GME", "cmax_t": 6.0, "jib_max_m": 60,
                       "tips": {60: 1.6, 45: 3.3}, "jibs": [25, 30, 35, 40, 45, 50, 55, 60],
                       "source": _SRC_POTAIN},
    "liebherr_125_ecb6": {"label": "Liebherr 125 EC-B 6", "family": "GME", "cmax_t": 6.0,
                          "jib_max_m": 58, "tips": {58: 1.6}, "hsc_m": 59.0, "source": _SRC_LIEBHERR},
    "potain_mdt_178": {"label": "Potain MDT 178", "family": "GME", "cmax_t": 8.0, "jib_max_m": 60,
                       "tips": {60: 1.5}, "jibs": [25, 30, 35, 40, 45, 50, 55, 60], "hsc_m": 41.2,
                       "base_m": 4.5,
                       "curves": {60: [(14.3, 8.0), (15, 7.5), (17, 6.5), (20, 5.3), (22, 4.7),
                                       (27.4, 4.0), (30, 3.6), (32, 3.3), (35, 3.0), (37, 2.8),
                                       (40, 2.55), (42, 2.4), (45, 2.2), (47, 2.05), (50, 1.9),
                                       (52, 1.8), (55, 1.7), (57, 1.6), (60, 1.5)]},
                       "source": _SRC_POTAIN},
    "potain_mct_185_j8": {"label": "Potain MCT 185 J8", "family": "GME", "cmax_t": 8.0,
                          "jib_max_m": 65, "tips": {65: 1.5}, "source": _SRC_POTAIN},
    "potain_mct_205": {"label": "Potain MCT 205", "family": "GME", "cmax_t": 10.0, "jib_max_m": 65,
                       "tips": {65: 1.75}, "source": _SRC_POTAIN},
    "potain_mdt_249_j10": {"label": "Potain MDT 249 J10", "family": "GME", "cmax_t": 10.0,
                           "jib_max_m": 65, "tips": {65: 2.75}, "source": _SRC_POTAIN},
    "potain_mdt_259_j10": {"label": "Potain MDT 259 J10", "family": "GME", "cmax_t": 10.0,
                           "jib_max_m": 65, "tips": {65: 3.1}, "source": _SRC_POTAIN},
    "potain_mdt_269_j10": {"label": "Potain MDT 269 J10", "family": "GME", "cmax_t": 10.0,
                           "jib_max_m": 65, "tips": {65: 3.3}, "source": _SRC_POTAIN},
}

FAMILIES = {"GMA": "Grua de montagem automática", "GME": "Grua de montagem por elementos"}

# Peso volúmico do betão armado / betão fresco: 25 kN/m³ (NP EN 1991-1-1, quadro A.1)
BETON_T_M3 = 2.5

# Dimensões máximas dos veículos (Decreto-Lei n.º 132/2017 — Diretiva 96/53/CE)
VEHICULES = {
    "porteur": {"label": "Camião rígido (12 m)", "long_m": 12.0, "larg_m": 2.55},
    "semi": {"label": "Veículo articulado (16,50 m)", "long_m": 16.5, "larg_m": 2.55},
}

# Bennes à déchets : encombrements indicatifs, à confirmer avec le loueur (modifiables).
BENNES = {
    "8": {"label": "Contentor 8 m³", "long_m": 3.5, "larg_m": 1.8},
    "15": {"label": "Contentor 15 m³", "long_m": 5.0, "larg_m": 2.3},
    "30": {"label": "Contentor 30 m³", "long_m": 6.0, "larg_m": 2.5},
}

# Module de base vie : conteneur 20 pieds ISO (6,06 × 2,44 m)
BUNGALOW = {"long_m": 6.06, "larg_m": 2.44}

DEFAULTS = {
    "grue": None, "grue_modele": "auto", "fleche_m": None,
    "grue_cmax_t": None, "grue_tip_t": None, "grue_jib_max_m": None,
    "grue_base_m": 4.5,            # emprise au sol (châssis / calage) — hypothèse modifiable
    "recul_facade_m": 2.0,         # recul du pied de grue par rapport aux façades — hypothèse
    "charge_max_t": None, "benne_beton_m3": None, "benne_tare_kg": None, "accessoires_kg": 0,
    "hauteur_batiment_m": None, "hauteur_charge_m": None, "garde_m": 2.0,
    "bennes": False, "nb_bennes": 1, "benne_type": "8",
    "aire_livraison": False, "vehicule": "porteur", "marge_livraison_m": 1.0,
    "stockage": False, "stockage_m2": 40.0,
    "base_vie": False, "effectif": None, "nb_bungalows": 2,
    "aire_lavage": False, "cloture": True,
    "nb_grues": "1", "grue2_modele": "identique", "fleche2_m": None, "charges": [],
    "stationnement": False, "nb_places": 4, "silo": False, "branchements": False,
    "cloture_panneau_m": 3.5, "portail_m": 4.0,
}

# Dimensions de travail (modifiables) des installations sans gabarit réglementaire
PLACE_PARKING = {"long_m": 5.0, "larg_m": 2.5}
SILO = {"long_m": 3.0, "larg_m": 3.0}

# Palette vive : chaque famille d'éléments se distingue d'un coup d'œil sur plan et photo aérienne
COLORS = {"grue": "#FF1744", "livraison": "#2979FF", "benne": "#FF6D00", "stockage": "#D500F9",
          "base_vie": "#00BFA5", "lavage": "#00B8D4", "acces": "#00C853", "parking": "#3D5AFE",
          "silo": "#AA00FF", "branchement": "#FFAB00"}


def questions(analysis: dict | None = None) -> list[dict]:
    """Options à valider par le client. Les valeurs proposées viennent de la lecture du plan
    quand elle les donne ; sinon le champ reste vide et doit être renseigné."""
    a = analysis or {}
    levels = a.get("levels")
    height = a.get("building_height_m")
    grue = None if levels is None else bool(levels >= 2)
    models = [{"value": "auto", "label": "Escolha automática (a grua mais pequena que serve)"}]
    models += [{"value": k, "label": _fr_txt(f"{c['label']} — {c['cmax_t']:g} t / {c['jib_max_m']:g} m")}
               for k, c in CRANES.items()]
    models.append({"value": "autre", "label": "Outro modelo (dados da ficha da empresa de aluguer)"})
    g = {"key": "grue", "is": True}
    return [
        {"key": "grue", "label": "O estaleiro tem grua-torre?", "type": "bool",
         "proposed": grue, "group": "Elevação"},
        {"key": "grue_modele", "label": "Modelo de grua", "type": "select", "options": models,
         "proposed": "auto", "group": "Elevação", "if": g},
        {"key": "fleche_m", "label": "Comprimento da lança (m) — vazio = calculado", "type": "number",
         "group": "Elevação", "if": g},
        {"key": "nb_grues", "label": "Número de gruas", "type": "select", "proposed": "1",
         "options": [{"value": "1", "label": "1 grua"}, {"value": "2", "label": "2 gruas (obra grande)"}],
         "group": "Elevação", "if": g},
        {"key": "grue2_modele", "label": "Modelo da 2.ª grua", "type": "select", "proposed": "identique",
         "options": [{"value": "identique", "label": "A mesma escolha da 1.ª grua"}] + models[1:-1],
         "group": "Elevação", "if": {"key": "nb_grues", "is": "2"}},
        {"key": "fleche2_m", "label": "Lança da 2.ª grua (m) — vazio = calculada", "type": "number",
         "group": "Elevação", "if": {"key": "nb_grues", "is": "2"}},
        {"key": "grue_cmax_t", "label": "Carga máxima da grua (t)", "type": "number",
         "group": "Elevação", "if": {"key": "grue_modele", "is": "autre"}},
        {"key": "grue_jib_max_m", "label": "Lança máxima da grua (m)", "type": "number",
         "group": "Elevação", "if": {"key": "grue_modele", "is": "autre"}},
        {"key": "grue_tip_t", "label": "Carga admissível na ponta da lança (t)", "type": "number",
         "group": "Elevação", "if": {"key": "grue_modele", "is": "autre"}},
        {"key": "charge_max_t", "label": "Carga mais pesada a elevar (t), sem contar o balde de betão",
         "type": "number", "group": "Elevação", "if": g},
        {"key": "benne_beton_m3", "label": "Balde de betão na grua — volume (m³), vazio = nenhum",
         "type": "number", "group": "Elevação", "if": g},
        {"key": "benne_tare_kg", "label": "Peso em vazio do balde de betão (kg)", "type": "number",
         "group": "Elevação", "if": g},
        {"key": "charges", "label": "Outras cargas a elevar (nome e peso)", "type": "loads",
         "group": "Elevação", "if": g},
        {"key": "accessoires_kg", "label": "Lingas / balancim / acessórios (kg)",
         "type": "number", "proposed": 0, "group": "Elevação", "if": g},
        {"key": "hauteur_batiment_m", "label": "Altura do edifício a sobrevoar (m)",
         "type": "number", "proposed": height, "group": "Elevação", "if": g},
        {"key": "hauteur_charge_m", "label": "Altura da carga + lingagem sob o gancho (m)",
         "type": "number", "group": "Elevação", "if": g},
        {"key": "aire_livraison", "label": "É necessária uma zona de cargas e descargas?", "type": "bool",
         "proposed": True, "group": "Logística"},
        {"key": "vehicule", "label": "Maior veículo de entrega", "type": "select",
         "options": [{"value": k, "label": v["label"]} for k, v in VEHICULES.items()],
         "proposed": "porteur", "group": "Logística", "if": {"key": "aire_livraison", "is": True}},
        {"key": "bennes", "label": "São necessários contentores de resíduos?", "type": "bool",
         "proposed": True, "group": "Logística"},
        {"key": "nb_bennes", "label": "Número de contentores de resíduos", "type": "number", "proposed": 1,
         "group": "Logística", "if": {"key": "bennes", "is": True}},
        {"key": "benne_type", "label": "Tipo de contentor", "type": "select",
         "options": [{"value": k, "label": v["label"]} for k, v in BENNES.items()],
         "proposed": "8", "group": "Logística", "if": {"key": "bennes", "is": True}},
        {"key": "stockage", "label": "É necessária uma zona de armazenamento?", "type": "bool",
         "proposed": True, "group": "Logística"},
        {"key": "stockage_m2", "label": "Área de armazenamento (m²)", "type": "number",
         "proposed": 40, "group": "Logística", "if": {"key": "stockage", "is": True}},
        {"key": "aire_lavage", "label": "Zona de lavagem de autobetoneiras / baldes de betão?", "type": "bool",
         "proposed": False, "group": "Logística"},
        {"key": "stationnement", "label": "Estacionamento no estaleiro?", "type": "bool",
         "proposed": False, "group": "Logística"},
        {"key": "nb_places", "label": "Número de lugares (5,00 × 2,50 m)", "type": "number",
         "proposed": 4, "group": "Logística", "if": {"key": "stationnement", "is": True}},
        {"key": "silo", "label": "Silo / central de argamassa?", "type": "bool", "proposed": False,
         "group": "Logística"},
        {"key": "branchements", "label": "Assinalar quadro elétrico e ponto de água de obra?",
         "type": "bool", "proposed": True, "group": "Instalações sociais"},
        {"key": "base_vie", "label": "São necessárias instalações sociais (contentores)?", "type": "bool",
         "proposed": True, "group": "Instalações sociais"},
        {"key": "effectif", "label": "Número máximo de trabalhadores em simultâneo", "type": "number",
         "group": "Instalações sociais", "if": {"key": "base_vie", "is": True}},
        {"key": "nb_bungalows", "label": "Número de contentores sociais (6,06 × 2,44 m)", "type": "number",
         "proposed": 2, "group": "Instalações sociais", "if": {"key": "base_vie", "is": True}},
        {"key": "cloture", "label": "Vedação do estaleiro em todo o perímetro?", "type": "bool",
         "proposed": True, "group": "Instalações sociais"},
    ]


# ---------------------------------------------------------------------------
# Grue : charge admissible
# ---------------------------------------------------------------------------
def _num(v):
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _fr_txt(s: str) -> str:
    """Virgule décimale française dans les textes affichés."""
    return re.sub(r"(?<=\d)\.(?=\d)", ",", s)


def _fr_list(items: list[str]) -> list[str]:
    return [_fr_txt(s) for s in items]


def _lookup(d: dict | None, key: float):
    for k, v in (d or {}).items():
        if abs(float(k) - float(key)) < 1e-6:
            return v
    return None


def _step_down(curve: list, r: float, cmax: float) -> float:
    """Valeur tabulée au premier rayon ≥ r (jamais d'interpolation optimiste)."""
    pts = sorted(curve)
    if r <= pts[0][0]:
        return cmax
    for rad, load in pts:
        if rad >= r - 1e-9:
            return load
    return 0.0


def capacity_at(crane: dict, jib_m: float, radius_m: float) -> dict:
    """Charge admissible (t) au rayon `radius_m` pour la flèche `jib_m`."""
    cmax = float(crane["cmax_t"])
    jmax = float(crane["jib_max_m"])
    r = max(float(radius_m), 0.0)
    if jib_m > jmax + 1e-6:
        return {"t": 0.0, "method": f"lança de {jib_m:g} m superior à lança máxima ({jmax:g} m)"}
    if r > jib_m + 1e-6:
        return {"t": 0.0, "method": "fora do alcance"}
    curve = _lookup(crane.get("curves"), jib_m)
    if curve:
        return {"t": _step_down(curve, r, cmax),
                "method": f"curva de carga do fabricante, lança de {jib_m:g} m"}
    tip = _lookup(crane.get("tips"), jib_m)
    if tip is not None:
        t = cmax if r <= 0 else min(cmax, float(tip) * jib_m / r)
        return {"t": round(t, 3), "method": f"limite prudente pelo momento na ponta "
                                            f"({tip:g} t a {jib_m:g} m, dado do fabricante)"}
    curve = _lookup(crane.get("curves"), jmax)
    if curve:
        return {"t": _step_down(curve, r, cmax),
                "method": f"curva do fabricante para a lança máxima de {jmax:g} m "
                          f"(prudente para uma lança de {jib_m:g} m)"}
    tip = _lookup(crane.get("tips"), jmax)
    t = cmax if r <= 0 else min(cmax, float(tip) * jmax / r)
    return {"t": round(t, 3), "method": f"limite prudente pelo momento na ponta da lança "
                                        f"máxima ({tip:g} t a {jmax:g} m, dado do fabricante)"}


def jib_for(crane: dict, reach_m: float) -> float | None:
    """Plus petite longueur de flèche couvrant la portée nécessaire."""
    jmax = float(crane["jib_max_m"])
    if reach_m > jmax + 1e-6:
        return None
    jibs = sorted(crane.get("jibs") or [])
    if jibs:
        return next((float(j) for j in jibs if j >= reach_m - 1e-6), None)
    # longueurs non publiées : pas de 5 m borné par la flèche maximale (à confirmer loueur)
    return min(jmax, max(5.0, math.ceil(reach_m / 5.0) * 5.0))


def _custom_crane(a: dict) -> dict | None:
    cmax, tip, jmax = _num(a.get("grue_cmax_t")), _num(a.get("grue_tip_t")), _num(a.get("grue_jib_max_m"))
    if not (cmax and tip and jmax):
        return None
    return {"label": "Grua introduzida (ficha de aluguer)", "family": "GME", "cmax_t": cmax, "jib_max_m": jmax,
            "tips": {jmax: tip}, "source": "Valores introduzidos pelo utilizador"}


def load_list(a: dict) -> dict:
    """Toutes les charges déclarées (t, accessoires compris) et informations manquantes."""
    rows, missing = [], []
    acc = (_num(a.get("accessoires_kg")) or 0.0) / 1000.0
    c = _num(a.get("charge_max_t"))
    if c:
        rows.append({"label": "Carga mais pesada declarada", "base_t": round(c, 3)})
    vol = _num(a.get("benne_beton_m3"))
    if vol:
        tare = _num(a.get("benne_tare_kg"))
        if tare is None:
            missing.append("Peso em vazio do balde de betão (kg)")
            tare = 0.0
        rows.append({"label": f"Balde de betão {vol:g} m³ × {BETON_T_M3:g} t/m³ + {tare:g} kg em vazio",
                     "base_t": round(vol * BETON_T_M3 + tare / 1000.0, 3)})
    for item in a.get("charges") or []:
        if not isinstance(item, dict):
            continue
        t = _num(item.get("t"))
        if t and t > 0:
            rows.append({"label": str(item.get("label") or "Carga").strip()[:60] or "Carga",
                         "base_t": round(t, 3)})
    for r in rows:
        r["t"] = round(r["base_t"] + acc, 3)
    return {"rows": rows, "accessoires_t": round(acc, 3), "missing": missing}


def design_load(a: dict) -> dict:
    """Charge de calcul (t) = plus lourde des charges déclarées + accessoires."""
    ll = load_list(a)
    detail = [{"label": r["label"], "t": r["base_t"]} for r in ll["rows"]]
    missing = list(ll["missing"])
    if not ll["rows"]:
        missing.append("Carga mais pesada a elevar (t) ou volume do balde de betão")
        return {"t": None, "detail": detail, "missing": missing, "rows": []}
    if ll["accessoires_t"]:
        detail.append({"label": "Lingas / acessórios", "t": ll["accessoires_t"]})
    return {"t": max(r["t"] for r in ll["rows"]), "detail": detail, "missing": missing, "rows": ll["rows"]}


def max_radius_for(crane: dict, jib_m: float, load_t: float) -> float:
    """Plus grand rayon (m, au décimètre) où `load_t` reste admissible ; 0 si jamais."""
    if jib_m > float(crane["jib_max_m"]) + 1e-6:
        return 0.0
    r = float(jib_m)
    while r > 0:
        if capacity_at(crane, jib_m, r)["t"] + 1e-9 >= load_t:
            return round(r, 1)
        r = round(r - 0.1, 1)
    return 0.0


def load_curve(crane: dict, jib_m: float) -> list[dict]:
    """Courbe charge / rayon échantillonnée au mètre (pour le graphique)."""
    pts, r = [], 2.0
    while r < jib_m - 1e-9:
        pts.append({"r_m": round(r, 1), "t": capacity_at(crane, jib_m, r)["t"]})
        r += 1.0
    pts.append({"r_m": round(float(jib_m), 1), "t": capacity_at(crane, jib_m, jib_m)["t"]})
    return pts


# ---------------------------------------------------------------------------
# Géométrie
# ---------------------------------------------------------------------------
def _poly(pts) -> Polygon | None:
    try:
        p = Polygon([(float(x), float(y)) for x, y in pts])
    except (TypeError, ValueError):
        return None
    if len(p.exterior.coords) < 4:
        return None
    if not p.is_valid:
        p = p.buffer(0)
    if p.is_empty or p.area <= 0:
        return None
    if p.geom_type == "MultiPolygon":
        p = max(p.geoms, key=lambda g: g.area)
    return p


def to_m(site: dict, pt) -> tuple[float, float]:
    k = float(site["m_per_px"])
    return float(pt[0]) * float(site["img_w"]) * k, float(pt[1]) * float(site["img_h"]) * k


def to_norm(site: dict, x: float, y: float) -> list[float]:
    k = float(site["m_per_px"])
    return [round(x / (float(site["img_w"]) * k), 5), round(y / (float(site["img_h"]) * k), 5)]


def _rect(cx, cy, w, h, rot=0.0) -> Polygon:
    r = box(cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)
    return _rotate(r, rot, origin=(cx, cy)) if rot else r


def _grid(poly: Polygon, step: float):
    minx, miny, maxx, maxy = poly.bounds
    y = miny + step / 2
    while y < maxy:
        x = minx + step / 2
        while x < maxx:
            yield x, y
            x += step
        y += step


def _edge_angles(parcel: Polygon) -> list[float]:
    """Orientations des côtés de la parcelle (0–180°), pour aligner les éléments."""
    out = [0.0, 90.0]
    c = list(parcel.exterior.coords)
    for (x1, y1), (x2, y2) in zip(c, c[1:]):
        if math.hypot(x2 - x1, y2 - y1) < 3:
            continue
        a = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180
        for b in (a, (a + 90) % 180):
            if all(min(abs(b - o), 180 - abs(b - o)) > 4 for o in out):
                out.append(round(b, 1))
    return out


def _place(free, taken: list, w: float, h: float, target, angles, step: float, gap=0.5,
           prefer=None):
    """Meilleure position d'un rectangle w×h dans `free`, sans chevauchement. `prefer(poly)`
    renvoie une pénalité (m) ajoutée à la distance à la cible."""
    best = None
    obstacles = unary_union(taken).buffer(gap) if taken else None
    tx, ty = target
    for x, y in _grid(free, step):
        for ang in angles:
            r = _rect(x, y, w, h, ang)
            if not free.contains(r):
                continue
            if obstacles is not None and r.intersects(obstacles):
                continue
            score = math.hypot(x - tx, y - ty) + (prefer(r) if prefer else 0.0)
            if best is None or score < best[0] - 1e-9:
                best = (score, x, y, ang, r)
    return best


def _far_reach(pos, polys) -> float:
    px, py = pos
    d = 0.0
    for p in polys:
        geoms = p.geoms if hasattr(p, "geoms") else [p]
        for g in geoms:
            for x, y in g.exterior.coords:
                d = max(d, math.hypot(x - px, y - py))
    return d


def suggest_crane_position(parcel: Polygon, buildings, base_m: float, recul_m: float,
                           extra_targets=None) -> dict:
    """Position du pied de grue qui minimise la portée nécessaire pour couvrir le bâtiment."""
    b_union = unary_union(buildings)
    targets = list(buildings) + list(extra_targets or [])
    keepout = b_union.buffer(recul_m)
    free = parcel.difference(keepout)
    step = max(0.5, math.sqrt(parcel.area) / 60.0)
    best = None
    if not free.is_empty:
        for x, y in _grid(free, step):
            base = _rect(x, y, base_m, base_m)
            if not free.contains(base):
                continue
            reach = _far_reach((x, y), targets)
            if best is None or reach < best[0] - 1e-9:
                best = (reach, x, y)
    if best:
        return {"x": best[1], "y": best[2], "inside_building": False}
    c = b_union.centroid
    return {"x": c.x, "y": c.y, "inside_building": True}


def select_crane(reach_m: float, load_t: float | None, hsc_req: float | None = None) -> list[dict]:
    """Grues du catalogue classées de la plus petite à la plus grande, avec leur verdict."""
    out = []
    for key, c in CRANES.items():
        jib = jib_for(c, reach_m)
        row = {"key": key, "label": c["label"], "jib_m": jib, "ok": False, "reasons": []}
        if jib is None:
            row["reasons"].append(f"lança máxima de {c['jib_max_m']:g} m < alcance de {reach_m:.1f} m")
        else:
            cap = capacity_at(c, jib, reach_m)
            row["capacity_t"] = cap["t"]
            if load_t is not None and cap["t"] + 1e-9 < load_t:
                row["reasons"].append(f"{cap['t']:g} t admissíveis a {reach_m:.1f} m < {load_t:g} t")
            if hsc_req is not None and c.get("hsc_m") is not None and c["hsc_m"] + 1e-9 < hsc_req:
                row["reasons"].append(f"altura sob o gancho autoestável de {c['hsc_m']:g} m < {hsc_req:g} m")
            row["ok"] = not row["reasons"]
        row["moment"] = max(float(t) * float(j) for j, t in c["tips"].items())
        out.append(row)
    out.sort(key=lambda r: (r["moment"], CRANES[r["key"]]["cmax_t"]))
    return out


# ---------------------------------------------------------------------------
# Lecture IA → géométrie
# ---------------------------------------------------------------------------
OBSTACLES = {"ligne_electrique": "Linha elétrica", "arbre": "Árvore", "voisin": "Construção vizinha",
             "batiment_existant": "Edifício existente", "autre": "Obstáculo"}


def _pt(v):
    try:
        x, y = float(v[0]), float(v[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (math.isfinite(x) and math.isfinite(y)):
        return None
    return [min(max(x, 0.0), 1.0), min(max(y, 0.0), 1.0)]


def norm_points(lst):
    return [p for p in (_pt(v) for v in (lst or [])) if p]


def site_from_analysis(d: dict, img_w: int, img_h: int) -> dict:
    """Géométrie exploitable par le moteur à partir de la lecture IA (échelle = cote lue)."""
    m_per_px = None
    ref = d.get("reference") or None
    if isinstance(ref, dict):
        p1, p2 = _pt(ref.get("p1")), _pt(ref.get("p2"))
        try:
            length = float(ref.get("length_m") or 0)
        except (TypeError, ValueError):
            length = 0
        if p1 and p2 and length > 0:
            px = math.hypot((p2[0] - p1[0]) * img_w, (p2[1] - p1[1]) * img_h)
            if px > 5:
                m_per_px = length / px
                ref = {"p1": p1, "p2": p2, "length_m": length, "label": ref.get("label")}
            else:
                ref = None
        else:
            ref = None
    buildings = [b for b in (d.get("buildings") or []) if isinstance(b, dict)]
    obstacles = []
    for o in d.get("obstacles") or []:
        bb = (o or {}).get("bbox") if isinstance(o, dict) else None
        if not isinstance(bb, (list, tuple)) or len(bb) != 4:
            continue
        p1, p2 = _pt(bb[:2]), _pt(bb[2:])
        if p1 and p2 and abs(p2[0] - p1[0]) > 1e-4 and abs(p2[1] - p1[1]) > 1e-4:
            kind = o.get("type") if o.get("type") in OBSTACLES else "autre"
            obstacles.append({"type": kind, "label": str(o.get("label") or OBSTACLES[kind])[:60],
                              "bbox": [min(p1[0], p2[0]), min(p1[1], p2[1]), max(p1[0], p2[0]), max(p1[1], p2[1])]})
    return {
        "obstacles": obstacles,
        "img_w": img_w, "img_h": img_h, "m_per_px": m_per_px, "reference": ref,
        "parcel": norm_points(d.get("parcel")),
        "buildings": [pts for pts in (norm_points(b.get("polygon")) for b in buildings) if len(pts) >= 3],
        "accesses": [p for p in (_pt((a or {}).get("point")) for a in (d.get("accesses") or [])
                                 if isinstance(a, dict)) if p],
    }


def hints(d: dict) -> dict:
    levels, height = None, None
    for b in d.get("buildings") or []:
        if not isinstance(b, dict):
            continue
        if isinstance(b.get("levels"), (int, float)):
            levels = max(levels or 0, int(b["levels"]))
        if isinstance(b.get("height_m"), (int, float)):
            height = max(height or 0, float(b["height_m"]))
    return {"levels": levels, "building_height_m": height}


# ---------------------------------------------------------------------------
# Vue aérienne géoréférencée (orthophoto IGN) : cadrage et conversion des coordonnées
# ---------------------------------------------------------------------------
def meters_per_degree(lat: float) -> tuple[float, float]:
    """Longueur (m) d'un degré de latitude et de longitude à la latitude donnée (ellipsoïde WGS84)."""
    p = math.radians(lat)
    m_lat = 111132.92 - 559.82 * math.cos(2 * p) + 1.175 * math.cos(4 * p) - 0.0023 * math.cos(6 * p)
    m_lon = 111412.84 * math.cos(p) - 93.5 * math.cos(3 * p) + 0.118 * math.cos(5 * p)
    return m_lat, m_lon


def _ring_points(geometry: dict | None) -> list[list[float]]:
    """Contour extérieur (lon, lat) du plus grand polygone d'une géométrie GeoJSON."""
    if not isinstance(geometry, dict):
        return []
    coords = geometry.get("coordinates") or []
    polys = [coords] if geometry.get("type") == "Polygon" else coords if geometry.get("type") == "MultiPolygon" else []
    best, best_area = [], -1.0
    for poly in polys:
        try:
            ring = [[float(x), float(y)] for x, y, *_ in poly[0]]
            area = Polygon(ring).area if len(ring) >= 4 else 0.0
        except (TypeError, ValueError, IndexError):
            continue
        if area > best_area:
            best, best_area = ring, area
    return best


def aerial_frame(lat: float, lon: float, span_m: float, size: int = 1280) -> dict:
    """Emprise carrée de `span_m` mètres centrée sur (lat, lon), pour une image de `size` px."""
    m_lat, m_lon = meters_per_degree(lat)
    hlat, hlon = span_m / 2 / m_lat, span_m / 2 / m_lon
    return {"lat": lat, "lon": lon, "span_m": float(span_m), "size": int(size),
            "minlat": lat - hlat, "maxlat": lat + hlat, "minlon": lon - hlon, "maxlon": lon + hlon,
            "m_per_px": span_m / size}


def aerial_frame_for(geometry: dict | None, lat: float, lon: float, span_m: float | None = None,
                     size: int = 1280) -> dict:
    """Cadrage centré sur la parcelle cadastrale (avec ses abords) ou, à défaut, sur l'adresse."""
    ring = _ring_points(geometry)
    if ring:
        lons, lats = [p[0] for p in ring], [p[1] for p in ring]
        lat, lon = (min(lats) + max(lats)) / 2, (min(lons) + max(lons)) / 2
        m_lat, m_lon = meters_per_degree(lat)
        extent = max((max(lats) - min(lats)) * m_lat, (max(lons) - min(lons)) * m_lon)
        auto = extent * 2.2          # la parcelle + ses abords (survol de la flèche)
    else:
        auto = 160.0
    span = float(span_m) if span_m else auto
    return aerial_frame(lat, lon, min(max(span, 80.0), 800.0), size)


def geo_to_norm(frame: dict, lon: float, lat: float) -> list[float]:
    x = (lon - frame["minlon"]) / (frame["maxlon"] - frame["minlon"])
    y = (frame["maxlat"] - lat) / (frame["maxlat"] - frame["minlat"])
    return [round(min(max(x, 0.0), 1.0), 5), round(min(max(y, 0.0), 1.0), 5)]


def aerial_site(frame: dict, geometry: dict | None) -> dict:
    """Site PIC posé sur l'orthophoto : échelle exacte par construction, emprise = parcelle
    cadastrale si elle est connue. Le bâtiment à construire reste à tracer."""
    ring = _ring_points(geometry)
    parcel = [geo_to_norm(frame, lon, lat) for lon, lat in ring[:-1]] if len(ring) >= 4 else []
    return {"base": "aerial", "img_w": frame["size"], "img_h": frame["size"],
            "m_per_px": frame["m_per_px"], "reference": None, "parcel": parcel,
            "buildings": [], "accesses": [], "obstacles": []}


# ---------------------------------------------------------------------------
# Calcul complet
# ---------------------------------------------------------------------------
def _el(site, kind, label, x, y, w, h, rot=0.0, **extra) -> dict:
    return {"id": extra.pop("id", kind), "type": kind, "label": label, "x": round(x, 2),
            "y": round(y, 2), "w": round(w, 2), "h": round(h, 2), "rot": round(rot, 1),
            "n": to_norm(site, x, y), "color": COLORS.get(kind, "#334155"), **extra}


def sanitaires(effectif: int) -> dict:
    """Mínimo do Regulamento das Instalações Provisórias Destinadas ao Pessoal Empregado nas Obras
    (Decreto n.º 46427, de 1965), art. 7.º: pelo menos uma retrete por cada 25 trabalhadores.
    Os restantes equipamentos não são calculados aqui: remete-se para o regulamento."""
    n = max(int(effectif), 0)
    return {"wc": math.ceil(n / 25), "ref": "Decreto n.º 46427, de 1965, art. 7.º — pelo menos uma retrete por cada 25 trabalhadores",
            "nota": "Lavatórios, chuveiros, vestiários e refeitório: dimensione segundo o Decreto n.º 46427 "
                    "e a Portaria n.º 101/96."}


def _sample(polys, step: float = 2.0) -> list[tuple[float, float]]:
    """Points du contour (sommets + un point tous les `step` m) des polygones à desservir."""
    pts = []
    for p in polys:
        for g in (p.geoms if hasattr(p, "geoms") else [p]):
            ext = g.exterior
            n = max(int(ext.length / step), 1)
            pts += [ext.interpolate(i * ext.length / n).coords[0] for i in range(n)]
            pts += list(ext.coords)[:-1]
    return pts


def suggest_two_cranes(parcel: Polygon, buildings, base_m: float, recul_m: float,
                       extra_targets=None) -> list[dict] | None:
    """Deux pieds de grue minimisant la plus grande portée nécessaire (chaque point du
    contour est desservi par la grue la plus proche)."""
    import numpy as np

    b_union = unary_union(buildings)
    free = parcel.difference(b_union.buffer(recul_m))
    if free.is_empty:
        return None
    step = max(1.0, math.sqrt(parcel.area) / 14.0)
    cands = [(x, y) for x, y in _grid(free, step) if free.contains(_rect(x, y, base_m, base_m))]
    if len(cands) < 2:
        return None
    pts = np.array(_sample(list(buildings) + list(extra_targets or [])))
    c = np.array(cands)
    d = np.hypot(c[:, None, 0] - pts[None, :, 0], c[:, None, 1] - pts[None, :, 1])
    best = None
    for i in range(len(c) - 1):
        m = np.minimum(d[i][None, :], d[i + 1:]).max(axis=1)
        j = int(m.argmin())
        if best is None or m[j] < best[0] - 1e-9:
            best = (float(m[j]), i, i + 1 + j)
    return [{"x": float(c[best[1]][0]), "y": float(c[best[1]][1])},
            {"x": float(c[best[2]][0]), "y": float(c[best[2]][1])}]


def _empty(missing: str) -> dict:
    return {"ok": False, "missing": [missing], "warnings": [], "elements": [], "hypotheses": [],
            "crane": None, "cranes": [], "materiel": [], "obstacles": []}


def compute(site: dict, answers: dict | None = None, placed: list | None = None,
            _targets: list | None = None) -> dict:
    """Calcule le PIC. `site` : {img_w, img_h, m_per_px, parcel:[[x,y]…] (0–1),
    buildings:[[[x,y]…]…], accesses:[[x,y]…], obstacles:[{type,label,bbox}]}. `placed` :
    éléments déjà positionnés par l'utilisateur (mètres) — conservés tels quels et vérifiés."""
    a = {**DEFAULTS, **{k: v for k, v in (answers or {}).items() if v is not None and v != ""}}
    warnings: list[str] = []
    missing: list[str] = []
    hypotheses: list[str] = []

    if not _num(site.get("m_per_px")) or not site.get("img_w") or not site.get("img_h"):
        return _empty("Escala da planta (calibre dois pontos de distância conhecida)")
    parcel = _poly([to_m(site, p) for p in site.get("parcel") or []])
    if parcel is None:
        return _empty("Contorno do limite do estaleiro (prédio)")
    buildings = [b for b in (_poly([to_m(site, p) for p in pts]) for pts in site.get("buildings") or [])
                 if b is not None]
    if not buildings:
        return _empty("Contorno do edifício a construir")
    b_union = unary_union(buildings)
    if not parcel.buffer(0.5).contains(b_union):
        warnings.append("O edifício ultrapassa o limite do estaleiro: verifique os contornos.")

    # obstacles lus sur le plan (boîtes englobantes)
    obstacles = []
    for o in site.get("obstacles") or []:
        try:
            x1, y1 = to_m(site, o["bbox"][:2])
            x2, y2 = to_m(site, o["bbox"][2:])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        obstacles.append({"type": o.get("type") or "autre", "label": o.get("label") or "Obstáculo",
                          "poly": box(min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)),
                          "x": round((x1 + x2) / 2, 2), "y": round((y1 + y2) / 2, 2),
                          "w": round(abs(x2 - x1), 2), "h": round(abs(y2 - y1), 2)})

    accesses = [to_m(site, p) for p in site.get("accesses") or []]
    if accesses:
        access = accesses[0]
    else:
        access = parcel.exterior.interpolate(0).coords[0]
        warnings.append("Acesso ao estaleiro não identificado na planta: posicione o portão.")

    fixed = {e["id"]: e for e in (placed or []) if e.get("id")}
    elements: list[dict] = []
    taken: list = []
    free = parcel.difference(b_union.buffer(1.0))
    solid = [o["poly"] for o in obstacles if o["type"] in ("arbre", "batiment_existant")]
    if solid:
        free = free.difference(unary_union(solid))
    angles = _edge_angles(parcel)
    step = max(0.5, math.sqrt(parcel.area) / 50.0)

    elements.append(_el(site, "acces", "Acesso ao estaleiro / portão", access[0], access[1], 0, 0))

    # --- Pieds de grue ------------------------------------------------------
    n_cranes = 0
    crane_pos: list[tuple[float, float]] = []
    base_m = _num(a["grue_base_m"]) or 4.5
    if a["grue"] is None:
        missing.append("O estaleiro tem grua?")
    if a["grue"]:
        n_cranes = 2 if str(a["nb_grues"]) == "2" else 1
        recul = _num(a["recul_facade_m"]) or 0.0
        hypotheses.append(f"Base da grua de {base_m:g} × {base_m:g} m e afastamento de {recul:g} m "
                          "em relação às fachadas: valores de trabalho, a ajustar ao chassis "
                          "e à fundação reais.")
        ids = ["grue", "grue_2"][:n_cranes]
        auto = None
        if n_cranes == 2 and not all(i in fixed for i in ids):
            auto = suggest_two_cranes(parcel, buildings, base_m, recul, _targets)
            if auto is None:
                warnings.append("Não há espaço livre para duas bases de grua: foi implantada uma só grua.")
                n_cranes, ids = 1, ["grue"]
        inside = False
        for i, ident in enumerate(ids):
            if ident in fixed:
                xy = (float(fixed[ident]["x"]), float(fixed[ident]["y"]))
                inside = inside or b_union.contains(Point(xy))
            elif auto:
                xy = (auto[i]["x"], auto[i]["y"])
            else:
                s = suggest_crane_position(parcel, buildings, base_m, recul, _targets)
                xy, inside = (s["x"], s["y"]), inside or s["inside_building"]
            if not parcel.contains(Point(xy)):
                warnings.append(f"A base da grua {i + 1} está fora do limite do estaleiro.")
            crane_pos.append(xy)
            taken.append(_rect(xy[0], xy[1], base_m, base_m))
        if inside:
            warnings.append("Não há espaço livre para a base da grua fora do edifício: grua dentro "
                            "da implantação do edifício (abertura / caixa a reservar) ou no domínio "
                            "público com licença de ocupação da via pública.")

    # --- Éléments au sol ----------------------------------------------------
    def add(kind, label, w, h, target, ident=None, **extra):
        ident = ident or kind
        if ident in fixed:
            f = fixed[ident]
            e = _el(site, kind, label, float(f["x"]), float(f["y"]), float(f.get("w", w)),
                    float(f.get("h", h)), float(f.get("rot", 0)), id=ident, **extra)
            r = _rect(e["x"], e["y"], e["w"], e["h"], e["rot"])
            if not parcel.buffer(0.05).contains(r):
                warnings.append(f"«{label}» ultrapassa o limite do estaleiro.")
            if r.intersects(b_union):
                warnings.append(f"«{label}» sobrepõe-se ao edifício.")
            if taken and r.intersects(unary_union(taken)):
                warnings.append(f"«{label}» sobrepõe-se a outro elemento.")
            if solid and r.intersects(unary_union(solid)):
                warnings.append(f"«{label}» sobrepõe-se a um obstáculo existente.")
            taken.append(r)
            elements.append(e)
            return e
        best = _place(free, taken, w, h, target, angles, step)
        if best is None:
            warnings.append(f"Espaço insuficiente para «{label}» ({w:g} × {h:g} m): posicione "
                            "à mão ou fora do estaleiro (licença de ocupação da via pública).")
            return None
        _, x, y, ang, r = best
        taken.append(r)
        e = _el(site, kind, label, x, y, w, h, ang, id=ident, **extra)
        elements.append(e)
        return e

    if a["aire_livraison"]:
        v = VEHICULES.get(str(a["vehicule"]), VEHICULES["porteur"])
        m = _num(a["marge_livraison_m"]) or 0.0
        add("livraison", f"Zona de cargas e descargas — {v['label']}", v["long_m"] + 2 * m,
            v["larg_m"] + 2 * m, access, vehicule=v["label"])
        hypotheses.append(f"Zona de cargas e descargas = dimensões máximas legais do veículo ({v['long_m']:g} × "
                          f"{v['larg_m']:g} m, Decreto-Lei n.º 132/2017) + {m:g} m de margem de "
                          "cada lado (margem modificável).")
    n_bennes = 0
    benne = BENNES.get(str(a["benne_type"]), BENNES["8"])
    if a["bennes"]:
        n_bennes = max(1, int(_num(a["nb_bennes"]) or 1))
        for i in range(n_bennes):
            add("benne", f"{benne['label']} n.º {i + 1}", benne["long_m"], benne["larg_m"], access,
                ident=f"benne_{i + 1}")
        hypotheses.append(f"Dimensões dos contentores de resíduos ({benne['long_m']:g} × {benne['larg_m']:g} m) "
                          "indicativas: confirme com a empresa de aluguer.")
    if a["aire_lavage"]:
        add("lavage", "Zona de lavagem de autobetoneiras", 6.0, 4.0, access)
        hypotheses.append("Zona de lavagem de 6 × 4 m: dimensão de trabalho modificável.")
    centre = crane_pos[0] if crane_pos else (b_union.centroid.x, b_union.centroid.y)
    stock_m2 = None
    if a["stockage"]:
        stock_m2 = max(_num(a["stockage_m2"]) or 0.0, 1.0)
        w = round(math.sqrt(stock_m2 * 2.0), 2)
        add("stockage", f"Zona de armazenamento {stock_m2:g} m²", w, round(stock_m2 / w, 2), centre)
    if a["silo"]:
        add("silo", "Silo / central de argamassa", SILO["long_m"], SILO["larg_m"], centre)
        hypotheses.append(f"Silo de {SILO['long_m']:g} × {SILO['larg_m']:g} m: ocupação de trabalho, "
                          "a confirmar com o fornecedor.")
    n_bung = 0
    if a["base_vie"]:
        n_bung = max(1, int(_num(a["nb_bungalows"]) or 1))
        for i in range(n_bung):
            add("base_vie", f"Contentor social n.º {i + 1}", BUNGALOW["long_m"], BUNGALOW["larg_m"],
                access, ident=f"base_vie_{i + 1}")
    n_places = 0
    if a["stationnement"]:
        n_places = max(1, int(_num(a["nb_places"]) or 1))
        add("parking", f"Estacionamento {n_places} lugares", n_places * PLACE_PARKING["larg_m"],
            PLACE_PARKING["long_m"], access)
        hypotheses.append(f"Lugar de estacionamento de {PLACE_PARKING['long_m']:g} × "
                          f"{PLACE_PARKING['larg_m']:g} m: dimensão de trabalho.")
    if a["branchements"]:
        add("branchement", "Quadro elétrico de obra", 1.0, 1.0, access, ident="armoire")
        add("branchement", "Ponto de água de obra", 1.0, 1.0, access, ident="point_eau")
        hypotheses.append("Quadro elétrico e ponto de água colocados junto ao acesso: ajuste aos "
                          "ramais reais (entidades gestoras).")

    served = [(e["label"], _rect(e["x"], e["y"], e["w"], e["h"], e["rot"])) for e in elements
              if e["type"] in ("livraison", "stockage")]
    # 2e passe : les grues sont repositionnées pour desservir aussi livraison et stockage
    if crane_pos and served and _targets is None and not all(i in fixed for i in ["grue", "grue_2"][:n_cranes]):
        return compute(site, answers, placed, _targets=[r for _, r in served])

    # --- Vérification des grues ---------------------------------------------
    cranes: list[dict] = []
    interference = None
    coverage = None
    loads_out: list[dict] = []
    if crane_pos:
        load = design_load(a)
        missing += load["missing"]
        hb, hc, garde = _num(a["hauteur_batiment_m"]), _num(a["hauteur_charge_m"]), _num(a["garde_m"]) or 0.0
        hsc_req = None
        if hb is not None and hc is not None:
            hsc_req = round(hb + garde + hc, 2)
            hypotheses.append(f"Altura sob o gancho necessária = {hb:g} m (edifício) + {garde:g} m "
                              f"(folga de segurança, modificável) + {hc:g} m (carga e lingagem).")
        else:
            missing.append("Altura do edifício e altura da carga + lingagem (altura sob o gancho)")

        # répartition : chaque point à desservir revient à la grue la plus proche
        groups = [{"bat": 0.0, "all": 0.0, "labels": []} for _ in crane_pos]

        def nearest(pt):
            return min(range(len(crane_pos)), key=lambda i: math.hypot(pt[0] - crane_pos[i][0], pt[1] - crane_pos[i][1]))

        for pt in _sample(buildings):
            i = nearest(pt)
            dist = math.hypot(pt[0] - crane_pos[i][0], pt[1] - crane_pos[i][1])
            groups[i]["bat"] = max(groups[i]["bat"], dist)
        for g in groups:
            g["all"] = g["bat"]
            if g["bat"] > 0:
                g["labels"].append("edifício")
        for label, r in served:
            i = nearest((r.centroid.x, r.centroid.y))
            groups[i]["all"] = max(groups[i]["all"], _far_reach(crane_pos[i], [r]))
            groups[i]["labels"].append(label)

        first_model = str(a["grue_modele"] or "auto")
        objs = []
        for i, xy in enumerate(crane_pos):
            g = groups[i]
            reach, reach_bat = g["all"], g["bat"]
            model = first_model
            asked = _num(a["fleche_m"])
            if i == 1:
                asked = _num(a["fleche2_m"])
                if str(a["grue2_modele"]) != "identique":
                    model = str(a["grue2_modele"])
            ranking = select_crane(reach, load["t"], hsc_req)
            crane, key = None, None
            if model == "autre":
                crane = _custom_crane(a)
                if crane is None and i == 0:
                    missing.append("Ficha da grua: carga máxima, lança máxima, carga na ponta da lança")
            elif model in CRANES:
                key, crane = model, CRANES[model]
            else:
                pick = next((r for r in ranking if r["ok"]), None)
                if pick:
                    key, crane = pick["key"], CRANES[pick["key"]]
                else:
                    tail = ("preveja duas gruas, um modelo mais potente (ficha de aluguer) ou uma elevação com "
                            "grua móvel." if n_cranes == 1 else "introduza a ficha de um modelo mais potente.")
                    warnings.append(f"Grua {i + 1}: nenhuma grua do catálogo cobre {reach:.1f} m com "
                                    f"a carga pedida — {tail}")
            ident = "grue" if i == 0 else "grue_2"
            res = {"id": ident, "num": i + 1, "x": round(xy[0], 2), "y": round(xy[1], 2),
                   "n": to_norm(site, *xy), "reach_building_m": round(reach_bat, 2),
                   "reach_required_m": round(reach, 2), "covered": g["labels"], "load": load,
                   "hsc_required_m": hsc_req, "ok": False, "checks": [],
                   "alternatives": [{k: r.get(k) for k in ("key", "label", "jib_m", "capacity_t", "ok", "reasons")}
                                    for r in ranking]}
            if not crane:
                elements.append(_el(site, "grue", f"Grua {i + 1}", xy[0], xy[1], base_m, base_m, id=ident))
                cranes.append(res)
                objs.append(None)
                continue
            jmax = float(crane["jib_max_m"])
            jib = asked or jib_for(crane, reach) or jmax
            tip = capacity_at(crane, jib, jib)
            cap = capacity_at(crane, jib, min(reach, jib))
            checks = [{"label": "Lança disponível neste modelo", "ok": jib <= jmax + 1e-6,
                       "detail": f"lança de {jib:g} m — máximo {jmax:g} m"},
                      {"label": "Alcance: a lança cobre toda a zona servida",
                       "ok": jib + 1e-6 >= reach, "detail": f"lança de {jib:g} m — alcance necessário {reach:.1f} m"}]
            lift_r = None
            if load["t"] is not None:
                lift_r = max_radius_for(crane, jib, load["t"])
                checks.append({"label": "Carga admissível no raio mais afastado",
                               "ok": jib + 1e-6 >= reach and cap["t"] + 1e-9 >= load["t"],
                               "detail": f"{cap['t']:g} t admissíveis a {min(reach, jib):.1f} m — "
                                         f"carga a elevar {load['t']:g} t ({cap['method']})"})
                checks.append({"label": "Carga admissível na ponta da lança",
                               "ok": tip["t"] + 1e-9 >= load["t"], "info": True,
                               "detail": f"{tip['t']:g} t na ponta da lança ({jib:g} m) — carga a elevar "
                                         f"{load['t']:g} t ({tip['method']})"})
            if hsc_req is not None:
                if crane.get("hsc_m") is not None:
                    checks.append({"label": "Altura sob o gancho (grua autoestável)",
                                   "ok": crane["hsc_m"] + 1e-9 >= hsc_req,
                                   "detail": f"{crane['hsc_m']:g} m publicados — {hsc_req:g} m necessários "
                                             "(acima disso: mais torre / ancoragens a estudar com a empresa de aluguer)"})
                else:
                    warnings.append(f"Grua {i + 1}: altura sob o gancho não publicada no catálogo — "
                                    f"verifique {hsc_req:g} m na ficha da empresa de aluguer.")
            if not crane.get("jibs") and model != "autre":
                hypotheses.append(f"Grua {i + 1}: comprimentos de lança intermédios não publicados no "
                                  "catálogo — confirme o comprimento adotado com a empresa de aluguer.")
            sweep = Point(xy).buffer(jib, 64)
            survol = round(sweep.difference(parcel).area, 1)
            if survol > 1:
                warnings.append(f"Grua {i + 1}: a lança sobrevoa {survol:g} m² fora do estaleiro (vizinhos / via "
                                "pública) — preveja acordo de sobrevoo ou limitador de zona; confirme as "
                                "exigências da câmara municipal.")
            for o in obstacles:
                if not sweep.intersects(o["poly"]):
                    continue
                if o["type"] == "ligne_electrique":
                    warnings.append(f"Grua {i + 1}: «{o['label']}» está na zona varrida — mantenha no mínimo "
                                    "5 m entre a linha e a grua, a carga e as lingas (regra de segurança da "
                                    "E-REDES) ou peça ao operador da rede a proteção ou a colocação fora de tensão da linha.")
                else:
                    warnings.append(f"Grua {i + 1}: «{o['label']}» está sob a lança — verifique a sua altura "
                                    "em relação à altura sob o gancho e proíba o sobrevoo com carga "
                                    "se necessário.")
            radii = sorted({round(x, 1) for x in (jib * 0.25, jib * 0.5, jib * 0.75, min(reach, jib), jib)})
            res.update({
                "key": key, "label": crane["label"], "family": FAMILIES.get(crane.get("family"), ""),
                "source": crane.get("source"), "cmax_t": crane["cmax_t"], "jib_m": jib,
                "jib_max_m": jmax, "tip_t": tip["t"], "tip_method": tip["method"],
                "capacity_at_reach_t": cap["t"], "capacity_method": cap["method"],
                "lift_radius_m": lift_r,
                "usage_pct": (round(100 * load["t"] / cap["t"], 1) if load["t"] and cap["t"] else None),
                "survol_hors_emprise_m2": survol, "checks": checks,
                "table": [{"r_m": r, "t": capacity_at(crane, jib, r)["t"]} for r in radii],
                "curve": load_curve(crane, jib),
                "ok": all(c["ok"] for c in checks if not c.get("info")) and load["t"] is not None,
            })
            elements.append(_el(site, "grue", f"Grua {i + 1}: {crane['label']} — lança de {jib:g} m"
                                if n_cranes > 1 else f"{crane['label']} — lança de {jib:g} m",
                                xy[0], xy[1], base_m, base_m, id=ident, jib_m=jib, lift_radius_m=lift_r))
            cranes.append(res)
            objs.append((crane, jib))

        live = [(crane_pos[i], objs[i]) for i in range(len(objs)) if objs[i]]
        if live:
            if any(e["type"] == "base_vie" and any(math.hypot(e["x"] - xy[0], e["y"] - xy[1]) < o[1]
                                                    for xy, o in live) for e in elements):
                warnings.append("As instalações sociais estão sob a zona de sobrevoo da grua: proíba o "
                                "sobrevoo com carga (limitador de zona) ou desloque os contentores.")

            def cover_pct(radius_of):
                discs = [Point(xy).buffer(r, 64) for xy, o in live for r in [radius_of(*o)] if r > 0]
                if not discs:
                    return 0.0
                return round(100 * b_union.intersection(unary_union(discs)).area / b_union.area, 1)

            coverage = {"portee_pct": cover_pct(lambda c, j: j)}
            if load["t"] is not None:
                coverage["charge_pct"] = cover_pct(lambda c, j: max_radius_for(c, j, load["t"]))
                if coverage["charge_pct"] < 99.5:
                    warnings.append(f"A carga de cálculo ({load['t']:g} t) só pode ser elevada em "
                                    f"{coverage['charge_pct']:g} % da implantação do edifício.")
            for row in load["rows"]:
                radii = [max_radius_for(c, j, row["t"]) for _, (c, j) in live]
                pct = cover_pct(lambda c, j, t=row["t"]: max_radius_for(c, j, t))
                loads_out.append({"label": row["label"], "t": row["t"], "radius_m": radii,
                                  "coverage_pct": pct, "ok": pct >= 99.5})
        if len(live) == 2:
            (p1, (_, j1)), (p2, (_, j2)) = live
            dist = round(math.hypot(p1[0] - p2[0], p1[1] - p2[1]), 2)
            overlap = dist < j1 + j2
            low = min(j1, j2)
            ok = (not overlap) or low + garde <= dist
            interference = {"distance_m": dist, "jib1_m": j1, "jib2_m": j2, "overlap": overlap, "ok": ok,
                            "detail": (f"distância entre torres {dist:g} m — lanças de {j1:g} m e {j2:g} m"
                                       + (": zonas de varrimento secantes" if overlap else ": sem interferência"))}
            if overlap:
                warnings.append(f"As duas gruas interferem (distância {dist:g} m < {j1:g} + {j2:g} m): "
                                "sistema anticolisão e alturas sob o gancho desniveladas obrigatórios.")
            if not ok:
                warnings.append(f"A lança da grua mais baixa ({low:g} m) atinge a torre da outra grua "
                                f"(distância {dist:g} m, folga {garde:g} m): afaste as bases ou encurte a lança.")

    # --- Base vie / clôture / matériel --------------------------------------
    base_vie = None
    if a["base_vie"]:
        eff = _num(a["effectif"])
        if eff is None:
            missing.append("Número máximo de trabalhadores em simultâneo (dimensionamento das instalações sanitárias)")
        else:
            base_vie = {"effectif": int(eff), **sanitaires(int(eff))}
    perim = round(parcel.exterior.length, 1)

    placed_ids = {e["id"] for e in elements}
    materiel: list[dict] = []

    def mat(designation, qte, unite, base=""):
        materiel.append({"designation": designation, "quantite": qte, "unite": unite, "base": base})

    for c in cranes:
        if c.get("label"):
            mat(f"Grua-torre {c['label']}", 1, "un", f"lança de {c['jib_m']:g} m")
    if a["cloture"]:
        lp = _num(a["cloture_panneau_m"]) or 3.5
        portail = min(_num(a["portail_m"]) or 0.0, perim)
        n_pan = math.ceil((perim - portail) / lp)
        mat("Vedação do estaleiro — comprimento", perim, "m", "perímetro do estaleiro")
        mat(f"Painéis de vedação móvel de {lp:g} m", n_pan, "un",
            f"({perim:g} − {portail:g} m de portão) ÷ {lp:g} m, arredondado por excesso")
        mat("Bases de vedação", n_pan + 1, "un", "uma por junção + extremidades")
        mat(f"Portão de estaleiro de {portail:g} m", 1, "un", "largura de trabalho modificável")
        hypotheses.append(f"Vedação em painéis móveis de {lp:g} m e portão de {portail:g} m: "
                          "dimensões de trabalho modificáveis.")
    if n_bennes:
        mat(benne["label"], sum(1 for i in placed_ids if i.startswith("benne_")), "un",
            f"{n_bennes} pedido(s)")
    if n_bung:
        mat("Contentor social 6,06 × 2,44 m", sum(1 for i in placed_ids if i.startswith("base_vie_")), "un",
            f"{n_bung} pedido(s)")
    if base_vie:
        mat("Retretes", base_vie["wc"], "un", "mínimo: 1 por cada 25 trabalhadores (Decreto n.º 46427, art. 7.º)")
    for e in elements:
        if e["type"] in ("livraison", "stockage", "lavage"):
            mat(e["label"], round(e["w"] * e["h"], 1), "m²", f"{e['w']:g} × {e['h']:g} m")
    if n_places and "parking" in placed_ids:
        mat("Lugares de estacionamento", n_places, "un", "5,00 × 2,50 m")
    if "silo" in placed_ids:
        mat("Silo / central de argamassa", 1, "un", "")
    if "armoire" in placed_ids:
        mat("Quadro elétrico de obra", 1, "un", "")
    if "point_eau" in placed_ids:
        mat("Ponto de água de obra", 1, "un", "")

    checklist = []
    if cranes:
        checklist += [
            "Verificação da grua após a montagem, por pessoa competente, antes da entrada em serviço "
            "(Decreto-Lei n.º 50/2005, art. 6.º).",
            "Estudo geotécnico e nota de cálculo da fundação / dos apoios da grua.",
            "Manobrador da grua com formação e habilitação adequadas (Decreto-Lei n.º 50/2005).",
            "Linhas elétricas aéreas: mantenha no mínimo 5 m entre as linhas e os equipamentos ou cargas "
            "(regra de segurança da E-REDES).",
        ]
    if len(cranes) > 1:
        checklist.append("Plano de interferência das gruas e regulação do sistema anticolisão antes da entrada em serviço.")
    checklist += ["Plano de Segurança e Saúde e, nos casos do art. 15.º, comunicação prévia da abertura do "
                  "estaleiro à ACT (Decreto-Lei n.º 273/2003).",
                  "Pedido de cadastro das infraestruturas enterradas às entidades gestoras antes de qualquer escavação.",
                  "Licença municipal de ocupação da via pública para qualquer ocupação, contentor ou descarga "
                  "no domínio público."]

    warnings, missing, hypotheses = _fr_list(warnings), _fr_list(missing), _fr_list(hypotheses)
    for e in elements:
        e["label"] = _fr_txt(e["label"])
    for m in materiel:
        m["designation"], m["base"] = _fr_txt(m["designation"]), _fr_txt(m["base"])
    for c in cranes:
        for ch in c.get("checks") or []:
            ch["detail"] = _fr_txt(ch["detail"])
        for alt in c["alternatives"]:
            alt["reasons"] = _fr_list(alt["reasons"])
        for k in ("tip_method", "capacity_method"):
            if c.get(k):
                c[k] = _fr_txt(c[k])
    if cranes:
        for row in cranes[0]["load"]["detail"]:
            row["label"] = _fr_txt(row["label"])
        for row in loads_out:
            row["label"] = _fr_txt(row["label"])
    if interference:
        interference["detail"] = _fr_txt(interference["detail"])
    cranes_ok = all(c["ok"] for c in cranes) and (interference is None or interference["ok"])
    return {
        "ok": not missing and cranes_ok,
        "site": {"parcel_m2": round(parcel.area, 1), "building_m2": round(b_union.area, 1),
                 "free_m2": round(parcel.difference(b_union).area, 1), "perimeter_ml": perim,
                 "width_m": round(float(site["img_w"]) * float(site["m_per_px"]), 2),
                 "height_m": round(float(site["img_h"]) * float(site["m_per_px"]), 2)},
        "crane": cranes[0] if cranes else None, "cranes": cranes, "interference": interference,
        "coverage": coverage, "loads": loads_out,
        "elements": elements, "base_vie": base_vie, "materiel": materiel,
        "obstacles": [{k: o[k] for k in ("type", "label", "x", "y", "w", "h")} for o in obstacles],
        "cloture_ml": perim if a["cloture"] else None,
        "warnings": list(dict.fromkeys(warnings)), "missing": list(dict.fromkeys(missing)),
        "hypotheses": list(dict.fromkeys(hypotheses)), "checklist": checklist,
        "answers": a,
    }
