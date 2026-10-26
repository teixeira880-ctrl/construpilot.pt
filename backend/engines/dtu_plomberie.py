"""Règles chiffrées de plomberie sanitaire (France), relevées dans les textes fournis par le client.

Une valeur = une source. Chaque table porte sa référence ; les rares hypothèses (épaisseur des tubes PVC,
capacité de baignoire par défaut, lecture du graphique) sont nommées comme telles dans `HYPOTHESES`.

Textes : NF DTU 60.11 (diamètres et débits), NF DTU 60.33 P1-1 (PVC évacuation, oct. 2007),
NF DTU 60.1 P1-1-3 (appareils sanitaires et production d'ECS, déc. 2012).
Partagé par le moteur de plans (`engines.mep`) et la note de calcul (`engines.calc_lots.plomberie`).
"""
from __future__ import annotations

import math

SOURCES = {
    "debits": "NF DTU 60.11 §2.1.1, Tableau I — débits de base et Ø intérieurs mini d'alimentation",
    "coefficients": "NF DTU 60.11 §2.1.2 — coefficients par appareil et graphique du Ø intérieur mini (installation individuelle)",
    "simultaneite": "NF DTU 60.11 §2.2 — y = 0,8/√(x − 1) (x > 5), une seule machine à laver comptée",
    "flamant": "NF DTU 60.11 §2.1.3 — au-delà de 15 coefficients : calcul collectif, 2 m/s en sous-sol, 1,5 m/s en colonne montante",
    "vidanges": "NF DTU 60.11 §3.1 et Tableau 2 — Ø intérieurs mini des évacuations individuelles, pente recommandée 1 cm/m",
    "siphons": "NF DTU 60.1 P1-1-3 §4.3.3 — garde d'eau 50 mm, Ø intérieur mini 30 mm (lavabo, bidet) et 40 mm (évier, baignoire, douche)",
    "chutes": "NF DTU 60.11 §3.2.3 et Tableau 4 — Ø intérieurs mini des chutes, ventilation primaire au même diamètre",
    "collecteur": "NF DTU 60.11 §3.3 et Tableau 5 — débits de vidange, Bazin à demi-plein (γ = 0,16), collecteur ≥ chute",
    "colliers": "NF DTU 60.33 P1-1 §4.3.2.1.1, Tableau 1 — espacement maximal des colliers",
    "points_fixes": "NF DTU 60.33 P1-1 §4.3.2.1.2 — points fixes, assemblages coulissants, dilatation 0,8 mm/m pour 10 °C",
    "chauffe_eau": "NF DTU 60.1 P1-1-3 §5.2 — fixation, espaces libres, vidange, groupe de sécurité, raccordement",
}

HYPOTHESES = {
    "pvc_wall": "Épaisseur des tubes PVC prise à 3,0 mm pour passer du Ø intérieur exigé au Ø extérieur commercial "
                "(cohérent avec les Ø intérieurs 69, 84, 94, 104 mm des tableaux 6 et 7 du DTU 60.11 ; "
                "à confirmer sur la fiche du fabricant)",
    "baignoire": "Baignoire supposée ≤ 150 l (coefficient 3) faute de capacité indiquée",
    "graphique": "Ø intérieur mini lu sur le graphique du §2.1.2 (lecture à ±0,3 mm)",
    "petite_installation": "Jusqu'à 5 appareils, le Ø vient de la méthode des coefficients ; la formule de simultanéité "
                           "ne sert alors qu'à estimer le débit (pertes de charge, vitesse)",
    "machines": "Lave-linge et lave-vaisselle comptés comme « machines à laver » : seule la plus forte est retenue dans le débit",
}

# --------------------------------------------------------------------------------------
# Appareils
#   q          : débit de base EF ou mélangée (l/s)                        — 60.11 Tableau I
#   q_ecs      : débit de base eau chaude (l/s)                            — 60.11 Tableau I
#   d_alim     : Ø intérieur mini d'alimentation (mm)                      — 60.11 Tableau I
#   coef       : coefficient installation individuelle                    — 60.11 §2.1.2
#   evac_int   : Ø intérieur mini de l'évacuation individuelle (mm)        — 60.11 Tableau 2
#   siphon_int : Ø intérieur mini du siphon (mm)                           — 60.1 P1-1-3 §4.3.3
#   q_evac     : débit de base de vidange (l/s)                            — 60.11 Tableau 5
# None : le texte ne donne pas de valeur pour cet appareil.
# --------------------------------------------------------------------------------------
APPAREILS = {
    "evier": {"q": 0.20, "q_ecs": 0.20, "d_alim": 12, "coef": 2.5, "evac_int": 33, "siphon_int": 40, "q_evac": 0.75},
    "lavabo": {"q": 0.20, "q_ecs": 0.20, "d_alim": 10, "coef": 1.5, "evac_int": 30, "siphon_int": 30, "q_evac": 0.75},
    "lave_mains": {"q": 0.10, "q_ecs": 0.0, "d_alim": 10, "coef": 0.5, "evac_int": 30, "siphon_int": 30, "q_evac": 0.5},
    "bidet": {"q": 0.20, "q_ecs": 0.20, "d_alim": 10, "coef": 1.0, "evac_int": 30, "siphon_int": 30, "q_evac": 0.5},
    "douche": {"q": 0.20, "q_ecs": 0.20, "d_alim": 12, "coef": 2.0, "evac_int": 33, "siphon_int": 40, "q_evac": 0.5},
    "baignoire": {"q": 0.33, "q_ecs": 0.33, "d_alim": 13, "coef": 3.0, "evac_int": 33, "siphon_int": 40, "q_evac": 1.2},
    "wc": {"q": 0.12, "q_ecs": 0.0, "d_alim": 10, "coef": 0.5, "evac_int": 80, "siphon_int": None, "q_evac": 1.5},
    "lave_linge": {"q": 0.20, "q_ecs": 0.0, "d_alim": 10, "coef": 1.0, "evac_int": 33, "siphon_int": None, "q_evac": 0.65},
    "lave_vaisselle": {"q": 0.10, "q_ecs": 0.0, "d_alim": 10, "coef": 1.0, "evac_int": 33, "siphon_int": None, "q_evac": 0.40},
    "bac_laver": {"q": 0.33, "q_ecs": 0.33, "d_alim": 13, "coef": None, "evac_int": None, "siphon_int": None, "q_evac": 0.75},
    "poste_eau_12": {"q": 0.33, "q_ecs": 0.0, "d_alim": 12, "coef": 2.0, "evac_int": 33, "siphon_int": None, "q_evac": None},
    "poste_eau_34": {"q": 0.42, "q_ecs": 0.0, "d_alim": 13, "coef": 2.0, "evac_int": 33, "siphon_int": None, "q_evac": None},
}
MACHINES = ("lave_linge", "lave_vaisselle")
BAIGNOIRE_LONGUE_M = 1.0          # 60.11 Tableau 2 : baignoire, Ø 33 si L ≤ 1 m, 38 si L > 1 m
BAIGNOIRE_LONGUE_INT = 38
COEF_MAX_INDIVIDUEL = 15          # 60.11 §2.1.2 : au-delà, calcul collectif (Flamant)
V_SOUS_SOL = 2.0                  # 60.11 §2.1.3 : vitesse de calcul en sous-sol / vide sanitaire (m/s)
V_COLONNE = 1.5                   # 60.11 §2.1.3 : vitesse de calcul en colonne montante (m/s)
PENTE_RECOMMANDEE = 0.01          # 60.11 §3.2.1 et §3.2.2
PENTE_TABLEAUX = (0.01, 0.03)     # 60.11 Tableaux 2 et 3 : établis pour 1 à 3 cm/m
BAZIN_GAMMA = 0.16                # 60.11 §3.3
GARDE_EAU_MM = 50                 # 60.1 P1-1-3 §4.3.3

# 60.11 §2.1.2 — graphique « Ø intérieur mini en fonction du coefficient » (points relevés, interpolation linéaire)
GRAPHIQUE_D = [(2, 10.8), (3, 12.0), (4, 13.3), (5, 14.6), (6, 15.4), (7, 16.2), (8, 16.9), (9, 17.4),
               (10, 18.0), (11, 18.4), (12, 19.0), (13, 19.5), (14, 20.0), (15, 20.0)]

# 60.11 Tableau 4 — chutes d'eaux usées / eaux-vannes (Ø intérieur mini, mm)
CHUTE_WC = 90
CHUTE_EU = [(3, 1, 50), (10, 2, 65), (math.inf, math.inf, 90)]   # (nb appareils max, nb baignoires max, Ø)

# 60.33 Tableau 1 — Ø extérieurs des tubes PVC et espacement maximal des colliers (m)
PVC_EXT = (32, 40, 50, 63, 75, 90, 100, 110, 125, 140, 160, 200, 250)
COLLIERS_HORIZ = [(63, 0.50), (140, 0.80), (250, 1.00)]          # (Ø ext max, espacement)
COLLIERS_VERT = 2.70
POINTS_FIXES_M = {"vidange": 3.0, "verticale": 4.0, "collecteur": 8.0}   # distance maximale entre points fixes
COULISSANT_AU_DELA_M = 1.0        # toute longueur droite > 1 m entre points fixes : un assemblage coulissant
DILATATION_MM_M_10K = 0.8
PVC_WALL_MM = 3.0                 # hypothèse — voir HYPOTHESES["pvc_wall"]

# 60.1 P1-1-3 §5.2 — appareils individuels de production d'ECS
CHAUFFE_EAU = {
    "espace_dessus_cm": 10, "espace_dessous_cm": 40, "espace_lateral_cm": 12,
    "mural_vertical_max_l": 200, "horizontal_max_l": 200, "cloison_legere_max_l": 30, "cloison_traversee_cm": 12,
    "vidange_dn_min": 32, "gs_distance_max_m": 3.0, "manchette_cuivre_cm": 50, "seuil_synthese_c": 80,
    "gs_evac_int": {"vertical_1m": 20, "autre": 25},          # 60.11 Tableau 2 : groupe de sécurité
}


# --------------------------------------------------------------------------------------
# Alimentation
# --------------------------------------------------------------------------------------
def coefficient(kind: str, baignoire_l: float | None = None) -> float | None:
    a = APPAREILS.get(kind)
    if not a or a["coef"] is None:
        return None
    if kind == "baignoire" and baignoire_l and baignoire_l > 150:
        return 3.0 + 0.1 * math.ceil((baignoire_l - 150) / 10)
    return a["coef"]


def d_graphique(coef_total: float) -> float | None:
    """Ø intérieur mini (mm) du groupe d'appareils, installation individuelle. None au-delà de 15."""
    if coef_total > COEF_MAX_INDIVIDUEL:
        return None
    if coef_total <= GRAPHIQUE_D[0][0]:
        return GRAPHIQUE_D[0][1]
    for (x0, d0), (x1, d1) in zip(GRAPHIQUE_D, GRAPHIQUE_D[1:]):
        if coef_total <= x1:
            return round(d0 + (d1 - d0) * (coef_total - x0) / (x1 - x0), 1)
    return GRAPHIQUE_D[-1][1]


def simultaneite(x: int) -> float:
    """y = 0,8/√(x − 1), sans plancher (la courbe du DTU descend sous 0,1 vers 150 appareils)."""
    return 1.0 if x <= 1 else min(1.0, 0.8 / math.sqrt(x - 1))


def debits_retenus(kinds: list[str], eau: str = "q") -> list[float]:
    """Débits de base à sommer : une seule machine à laver (la plus forte), les autres appareils tous."""
    qs = [APPAREILS[k][eau] for k in kinds if k in APPAREILS and k not in MACHINES and APPAREILS[k][eau]]
    machines = [APPAREILS[k][eau] for k in kinds if k in MACHINES and APPAREILS[k][eau]]
    return qs + ([max(machines)] if machines else [])


def groupe_alimentation(kinds: list[str], eau: str = "q", colonne: bool = False,
                        baignoire_l: float | None = None) -> dict:
    """Dimensionnement d'une conduite desservant un groupe d'appareils (60.11 §2.1.2 à §2.2).

    Renvoie la méthode, le Ø intérieur mini (graphique) si installation individuelle, le débit probable
    estimé et la vitesse de calcul."""
    served = [k for k in kinds if k in APPAREILS and APPAREILS[k][eau]]
    coefs = [coefficient(k, baignoire_l) for k in served]
    total = round(sum(c for c in coefs if c is not None), 2)
    individuelle = bool(served) and None not in coefs and total <= COEF_MAX_INDIVIDUEL
    qs = debits_retenus(served, eau)
    y = simultaneite(len(qs))
    q = sum(qs) * y
    if qs:
        q = max(q, max(qs))       # jamais moins que l'appareil le plus fort
    return {"methode": "individuelle" if individuelle else "collective", "coef_total": total,
            "d_int_min": max(d_graphique(total), max(APPAREILS[k]["d_alim"] for k in served)) if individuelle else None,
            "x": len(qs), "y": y, "q_probable": q,
            "v_calcul": V_COLONNE if colonne else V_SOUS_SOL,
            "source": SOURCES["coefficients"] if individuelle else SOURCES["flamant"]}


# --------------------------------------------------------------------------------------
# Évacuation
# --------------------------------------------------------------------------------------
def vidange_int_min(kind: str, longueur_m: float | None = None) -> int | None:
    """Ø intérieur mini du branchement : ≥ Tableau 2 et ≥ Ø du siphon reçu (60.11 §3.1, 60.1 P1-1-3 §4.3.3)."""
    a = APPAREILS.get(kind)
    if not a or a["evac_int"] is None:
        return None
    d = a["evac_int"]
    if kind == "baignoire" and longueur_m is not None and longueur_m > BAIGNOIRE_LONGUE_M:
        d = BAIGNOIRE_LONGUE_INT
    return max(d, a["siphon_int"] or 0)


def pvc_pour(d_int_min: float, plancher: int = 0, wall: float = PVC_WALL_MM) -> int:
    """Plus petit Ø extérieur PVC (60.33 Tableau 1) dont le Ø intérieur estimé couvre d_int_min."""
    for ext in PVC_EXT:
        if ext >= plancher and ext - 2 * wall >= d_int_min:
            return ext
    return PVC_EXT[-1]


def pvc_int(ext: int, wall: float = PVC_WALL_MM) -> float:
    return ext - 2 * wall


def chute_int_min(kinds: list[str]) -> int:
    """60.11 Tableau 4. WC : 90 mm quel que soit le nombre ; autres appareils selon leur nombre et les baignoires."""
    d = CHUTE_WC if "wc" in kinds else 0
    others = [k for k in kinds if k != "wc"]
    if others:
        bains = sum(1 for k in others if k == "baignoire")
        d = max(d, next(v for n, b, v in CHUTE_EU if len(others) <= n and bains <= b))
    return d


def bazin_demi_plein(d_int_mm: float, pente: float, gamma: float = BAZIN_GAMMA) -> float:
    """Débit (l/s) d'un tuyau coulant à demi-plein (60.11 §3.3) : Q = 87·RH·√i / (γ + √RH) · SM."""
    d = d_int_mm / 1000
    sm = math.pi * d ** 2 / 8
    rh = d / 4
    return 87 * rh * math.sqrt(pente) / (gamma + math.sqrt(rh)) * sm * 1000


def collecteur(kinds: list[str], pente: float, d_chute_ext: int = 0, plancher: int = 0) -> dict:
    """Collecteur principal (60.11 §3.3) : Σ débits Tableau 5 × y, Bazin à demi-plein, jamais sous la chute."""
    qs = [APPAREILS[k]["q_evac"] for k in kinds if k in APPAREILS and APPAREILS[k]["q_evac"]]
    y = simultaneite(len(qs))
    q = round(sum(qs) * y, 3)
    ext = next((e for e in PVC_EXT if e >= max(plancher, d_chute_ext) and bazin_demi_plein(pvc_int(e), pente) >= q),
               PVC_EXT[-1])
    return {"q_probable": q, "x": len(qs), "y": round(y, 3), "diametre": ext,
            "capacite": round(bazin_demi_plein(pvc_int(ext), pente), 3), "pente": pente}


def colliers(ext: int, longueur_m: float, vertical: bool = False) -> dict:
    """Colliers, points fixes et assemblages coulissants d'une canalisation PVC apparente (60.33 §4.3.2.1)."""
    if vertical:
        esp, fixe = COLLIERS_VERT, POINTS_FIXES_M["verticale"]
    else:
        esp = next((e for dmax, e in COLLIERS_HORIZ if ext <= dmax), COLLIERS_HORIZ[-1][1])
        fixe = POINTS_FIXES_M["vidange"]
    n = math.ceil(longueur_m / esp) + 1 if longueur_m > 0 else 0
    troncons = max(1, math.ceil(longueur_m / fixe)) if longueur_m > 0 else 0
    coulissants = troncons if longueur_m / max(troncons, 1) > COULISSANT_AU_DELA_M else 0
    return {"colliers": n, "espacement_m": esp, "points_fixes": troncons + 1 if longueur_m > 0 else 0,
            "coulissants": coulissants}
