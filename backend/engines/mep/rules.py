"""Tables de règles par pays — séparées du code pour être relues et ajustées par un BET.

FR : NF C 15-100 (logement, partie 7-771) et NF DTU 60.11 (P1-1 alimentation, P1-2 évacuation).
PT : RTIEBT (Portaria 949-A/2006) et Decreto Regulamentar 23/95 (redes prediais).

Chaque valeur porte sa provenance dans `source`. Les valeurs marquées `practice=True`
sont des règles de l'art courantes (pas des minima normatifs) : elles sont signalées
comme telles dans les contrôles. Le moteur produit une PRÉ-ÉTUDE : la validation
finale reste de la responsabilité d'un professionnel qualifié.
"""
from __future__ import annotations

import math
import re
import unicodedata

# --------------------------------------------------------------------------------------
# Typologie des pièces (FR + PT)
# --------------------------------------------------------------------------------------
ROOM_TYPES = (
    "sejour", "cuisine", "chambre", "bureau", "salle_de_bain", "salle_d_eau", "wc",
    "entree", "circulation", "cellier", "buanderie", "garage", "dressing", "escalier",
    "exterieur", "autre",
)

_ROOM_PATTERNS = [
    ("salle_de_bain", r"salle de bains?|sdb\b|casa de banho completa|banheira"),
    ("salle_d_eau", r"salle d.?eau|sde\b|casa de banho|wc ?/ ?ch|i\.?s\.?\b|instala..o sanit"),
    ("wc", r"^wc\b|toilet|lavabos?\b|retrete|sanita"),
    ("cuisine", r"cuisine|kitchen|cozinha|kitchenette"),
    ("sejour", r"s[eé]jour|salon|sam\b|salle . manger|living|sala|estar|jantar"),
    ("chambre", r"chambre|quarto|suite|su[ií]te"),
    ("bureau", r"bureau|escrit[oó]rio|office"),
    ("entree", r"entr[eé]e|hall|vestibule|entrada"),
    ("circulation", r"circu|d[eé]gagement|couloir|palier|corredor|patamar"),
    ("cellier", r"c[eé]lier|cellier|arri[eè]re.cuisine|despensa|arrumos|cave\b"),
    ("buanderie", r"buanderie|lavandaria|laundry"),
    ("garage", r"garage|garagem"),
    ("dressing", r"dressing|placard|closet|roupeiro"),
    ("escalier", r"escalier|escada"),
    ("exterieur", r"terrasse|balcon|varanda|terra[cç]o|jardin|quintal"),
]


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower().strip()


def classify_room(name: str) -> str:
    n = _fold(name)
    for kind, pat in _ROOM_PATTERNS:
        if re.search(_fold(pat), n):
            return kind
    return "autre"


HABITABLE = {"sejour", "cuisine", "chambre", "bureau", "salle_de_bain", "salle_d_eau", "wc",
             "entree", "circulation", "dressing", "buanderie", "cellier"}
WET_ROOMS = {"salle_de_bain", "salle_d_eau"}

# --------------------------------------------------------------------------------------
# ÉLECTRICITÉ
# --------------------------------------------------------------------------------------
# Équipement minimal par pièce. `sockets(surface)` renvoie le nombre de socles 16 A
# hors plan de travail et hors circuits spécialisés.

def _fr_sockets(kind: str, s: float) -> int:
    if kind == "sejour":
        # NF C 15-100 : 1 socle par tranche de 4 m², minimum 5 ; 7 au-delà de 28 m².
        return max(5 if s <= 28 else 7, math.ceil(s / 4))
    if kind in ("chambre", "bureau"):
        return 3
    if kind == "cuisine":
        return 2 if s > 4 else 0          # + 4 au-dessus du plan de travail (6 au total)
    if kind in ("salle_de_bain", "salle_d_eau"):
        return 1
    if kind in ("entree", "circulation"):
        return 1 if s > 4 else 0
    if kind in ("cellier", "buanderie", "garage", "dressing"):
        return 1 if s > 4 else 0
    return 1 if s > 4 else 0


def _fr_worktop(kind: str, s: float) -> int:
    if kind != "cuisine":
        return 0
    return 4 if s > 4 else 3


def _fr_rj45(kind: str, s: float) -> int:
    if kind == "sejour":
        return 2
    if kind in ("chambre", "bureau"):
        return 1
    return 0


def _pt_sockets(kind: str, s: float) -> int:
    # RTIEBT ne fixe pas de nombre minimal par pièce : règles de l'art (practice=True).
    if kind == "sejour":
        return max(4, math.ceil(s / 6))
    if kind in ("chambre", "bureau"):
        return 3
    if kind == "cuisine":
        return 2
    if kind in ("salle_de_bain", "salle_d_eau"):
        return 1
    if kind in ("entree", "circulation", "cellier", "buanderie", "garage", "dressing"):
        return 1 if s > 4 else 0
    return 1 if s > 4 else 0


def _pt_worktop(kind: str, s: float) -> int:
    return 4 if kind == "cuisine" else 0


def _pt_rj45(kind: str, s: float) -> int:
    # ITED : tomadas de telecomunicações — sala 2, quartos 1 (prática corrente).
    if kind == "sejour":
        return 2
    if kind in ("chambre", "bureau"):
        return 1
    return 0


RULES = {
    "fr": {
        "label": "NF C 15-100 / NF DTU 60.11",
        "elec": {
            "sockets": _fr_sockets,
            "worktop": _fr_worktop,
            "rj45": _fr_rj45,
            "sockets_practice": False,
            "light_per_room": 1,
            "light_large_room_m2": 28.0,      # au-delà : 2 points (règle de l'art)
            "lighting_circuit": {"max_points": 8, "section": 1.5, "breaker": 16},
            "socket_circuit": {"max_points": 8, "section": 2.5, "breaker": 20},
            "worktop_circuit": {"max_points": 6, "section": 2.5, "breaker": 20, "dedicated": True},
            "specialised": {
                "plaque": {"section": 6.0, "breaker": 32, "rcd_type": "A", "label": "Plaque de cuisson"},
                "four": {"section": 2.5, "breaker": 20, "rcd_type": "A", "label": "Four"},
                "lave_vaisselle": {"section": 2.5, "breaker": 20, "rcd_type": "A", "label": "Lave-vaisselle"},
                "lave_linge": {"section": 2.5, "breaker": 20, "rcd_type": "A", "label": "Lave-linge"},
                "seche_linge": {"section": 2.5, "breaker": 20, "rcd_type": "A", "label": "Sèche-linge"},
                "chauffe_eau": {"section": 2.5, "breaker": 20, "rcd_type": "A", "label": "Chauffe-eau (contacteur HC)"},
                "congelateur": {"section": 2.5, "breaker": 20, "rcd_type": "A", "label": "Congélateur"},
                "vmc": {"section": 1.5, "breaker": 2, "rcd_type": "A", "label": "VMC"},
                "irve": {"section": 6.0, "breaker": 32, "rcd_type": "F", "label": "Borne de recharge (IRVE)"},
            },
            # Nombre et calibre des interrupteurs différentiels 30 mA selon la surface habitable.
            "rcd_by_surface": [(35, [25, 40]), (100, [40, 40, 40]), (1e9, [40, 40, 40, 40])],
            "rcd_max_circuits": 8,
            "rcd_default_type": "A",
            "reserve_ratio": 0.20,
            "smoke_detector_per_level": 1,
            "heights": {"prise": 0.30, "prise_plan_travail": 1.10, "interrupteur": 1.10,
                        "rj45": 0.30, "sortie_cable": 0.30, "tableau": 1.40},
            "bathroom_clearance_m": 0.60,
            "sources": {
                "sockets": "NF C 15-100 partie 7-771 — équipement minimal des pièces",
                "circuits": "NF C 15-100 partie 7-771 — sections, calibres et nombre de points par circuit",
                "rcd": "NF C 15-100 — DDR 30 mA selon surface, 8 circuits max par DDR",
                "bathroom": "NF C 15-100 partie 7-701 — volumes 0, 1, 2 (pas de socle dans le volume 2)",
                "reserve": "NF C 15-100 — 20 % de réserve au tableau",
                "smoke": "Loi n° 2010-238 et CCH — DAAF obligatoire (1 minimum par logement, 1 par niveau recommandé)",
            },
        },
        "plumbing": {
            # Débit de base (l/s), diamètre intérieur mini alimentation (mm), Ø évacuation PVC (mm).
            # `drain` = Ø extérieur PVC courant (règle de l'art) : le moteur le relève si le Ø intérieur
            # exigé par NF DTU 60.11 Tableau 2 / NF DTU 60.1 P1-1-3 (siphons) n'est pas atteint.
            # Toutes les autres valeurs DTU sont dans engines/dtu_plomberie.py.
            "dtu": True,
            "fixtures": {
                "evier": {"q": 0.20, "d_supply": 12, "drain": 40, "hot": True, "label": "Évier"},
                "lavabo": {"q": 0.20, "d_supply": 10, "drain": 32, "hot": True, "label": "Lavabo"},
                "lave_mains": {"q": 0.10, "d_supply": 10, "drain": 32, "hot": False, "label": "Lave-mains"},
                "douche": {"q": 0.20, "d_supply": 12, "drain": 40, "hot": True, "label": "Douche"},
                "baignoire": {"q": 0.33, "d_supply": 13, "drain": 40, "hot": True, "label": "Baignoire"},
                "wc": {"q": 0.12, "d_supply": 10, "drain": 100, "hot": False, "label": "WC"},
                "bidet": {"q": 0.20, "d_supply": 10, "drain": 32, "hot": True, "label": "Bidet"},
                "lave_linge": {"q": 0.20, "d_supply": 10, "drain": 40, "hot": False, "label": "Lave-linge"},
                "lave_vaisselle": {"q": 0.10, "d_supply": 10, "drain": 40, "hot": False, "label": "Lave-vaisselle"},
            },
            # Tubes PER disponibles : (Ø ext, Ø int) — la nourrice dessert chaque point en pieuvre.
            "pipes": [(12, 9.8), (16, 13.0), (20, 16.2), (25, 20.4), (32, 26.2)],
            "pipe_tolerance_mm": 0.3,
            "max_velocity": 2.0,
            "simultaneity": "dtu",           # y = 0,8 / sqrt(x - 1)
            "slope_min": 0.01, "slope_max": 0.03,
            "wc_slope_min": 0.01,
            "pipe_material": "PER",
            "drain_material": "PVC",
            "sources": {
                "supply": "NF DTU 60.11 §2.1 — débits de base (Tableau I), coefficients et Ø mini des groupes (§2.1.2)",
                "drain": "NF DTU 60.11 §3 — Ø intérieurs mini (Tableaux 2 et 4), pente recommandée 1 cm/m (tableaux de 1 à 3 cm/m)",
                "velocity": "NF DTU 60.11 §2.1.3 — 2 m/s en sous-sol / vide sanitaire, 1,5 m/s en colonne montante",
                "siphon": "NF DTU 60.1 P1-1-3 §4.3.3 — Ø intérieur des siphons ; NF DTU 60.11 §3.1 — branchement ≥ siphon",
                "collector": "NF DTU 60.11 §3.3 — Tableau 5 et Bazin à demi-plein, collecteur ≥ chute",
                "supports": "NF DTU 60.33 P1-1 §4.3.2.1 — colliers (Tableau 1), points fixes, assemblages coulissants",
                "heater": "NF DTU 60.1 P1-1-3 §5.2 — chauffe-eau individuel",
            },
        },
    },
    "pt": {
        "label": "RTIEBT / DR 23/95",
        "elec": {
            "sockets": _pt_sockets,
            "worktop": _pt_worktop,
            "rj45": _pt_rj45,
            "sockets_practice": True,
            "light_per_room": 1,
            "light_large_room_m2": 28.0,
            "lighting_circuit": {"max_points": 8, "section": 1.5, "breaker": 10},
            "socket_circuit": {"max_points": 8, "section": 2.5, "breaker": 16},
            "worktop_circuit": {"max_points": 6, "section": 2.5, "breaker": 16, "dedicated": True},
            "specialised": {
                "plaque": {"section": 6.0, "breaker": 32, "rcd_type": "A", "label": "Placa de cozinha"},
                "four": {"section": 2.5, "breaker": 16, "rcd_type": "A", "label": "Forno"},
                "lave_vaisselle": {"section": 2.5, "breaker": 16, "rcd_type": "A", "label": "Máquina de lavar loiça"},
                "lave_linge": {"section": 2.5, "breaker": 16, "rcd_type": "A", "label": "Máquina de lavar roupa"},
                "seche_linge": {"section": 2.5, "breaker": 16, "rcd_type": "A", "label": "Máquina de secar"},
                "chauffe_eau": {"section": 2.5, "breaker": 16, "rcd_type": "A", "label": "Termoacumulador"},
                "congelateur": {"section": 2.5, "breaker": 16, "rcd_type": "A", "label": "Arca congeladora"},
                "vmc": {"section": 1.5, "breaker": 6, "rcd_type": "A", "label": "Ventilação"},
                "irve": {"section": 6.0, "breaker": 32, "rcd_type": "A", "label": "Carregador VE"},
            },
            "rcd_by_surface": [(1e9, [40, 40])],
            "rcd_max_circuits": 8,
            "rcd_default_type": "A",
            "reserve_ratio": 0.20,
            "smoke_detector_per_level": 0,
            "heights": {"prise": 0.30, "prise_plan_travail": 1.10, "interrupteur": 1.10,
                        "rj45": 0.30, "sortie_cable": 0.30, "tableau": 1.40},
            "bathroom_clearance_m": 0.60,
            "sources": {
                "sockets": "Prática corrente (o RTIEBT não fixa um número mínimo de tomadas por compartimento)",
                "circuits": "RTIEBT secção 801 — circuitos de iluminação 1,5 mm² / tomadas 2,5 mm²",
                "rcd": "RTIEBT — proteção diferencial 30 mA obrigatória nos circuitos de tomadas",
                "bathroom": "RTIEBT secção 701 — volumes 0, 1, 2 das casas de banho",
                "reserve": "Prática corrente — 20 % de reserva no quadro",
                "smoke": "—",
            },
        },
        "plumbing": {
            # Caudais instantâneos (l/s) — DR 23/95, Anexo III ; diâmetros mínimos dos ramais de descarga (mm)
            "fixtures": {
                "evier": {"q": 0.20, "d_supply": 12, "drain": 50, "hot": True, "label": "Lava-loiça"},
                "lavabo": {"q": 0.10, "d_supply": 10, "drain": 40, "hot": True, "label": "Lavatório"},
                "lave_mains": {"q": 0.10, "d_supply": 10, "drain": 40, "hot": False, "label": "Lavatório de mãos"},
                "douche": {"q": 0.15, "d_supply": 12, "drain": 40, "hot": True, "label": "Base de duche"},
                "baignoire": {"q": 0.25, "d_supply": 13, "drain": 40, "hot": True, "label": "Banheira"},
                "wc": {"q": 0.10, "d_supply": 10, "drain": 110, "hot": False, "label": "Sanita"},
                "bidet": {"q": 0.10, "d_supply": 10, "drain": 40, "hot": True, "label": "Bidé"},
                "lave_linge": {"q": 0.20, "d_supply": 10, "drain": 50, "hot": False, "label": "Máquina de lavar roupa"},
                "lave_vaisselle": {"q": 0.15, "d_supply": 10, "drain": 50, "hot": False, "label": "Máquina de lavar loiça"},
            },
            "pipes": [(12, 9.8), (16, 12.0), (20, 16.0), (25, 20.0), (32, 26.0)],
            "pipe_tolerance_mm": 0.3,
            "max_velocity": 2.0,
            "simultaneity": "dtu",
            "slope_min": 0.01, "slope_max": 0.04,
            "wc_slope_min": 0.01,
            "pipe_material": "PEX / multicamada",
            "drain_material": "PVC",
            "sources": {
                "supply": "DR 23/95 — caudais instantâneos e velocidades (0,5 a 2 m/s)",
                "drain": "DR 23/95 — diâmetros mínimos dos ramais e inclinações (10 a 40 mm/m)",
                "velocity": "DR 23/95 — velocidade máxima 2 m/s",
            },
        },
    },
}


def rules_for(country: str) -> dict:
    return RULES.get((country or "fr").lower(), RULES["fr"])


def simultaneity(n: int) -> float:
    """Coefficient de simultanéité NF DTU 60.11 : y = 0,8 / √(x − 1), borné à [0,2 ; 1]."""
    if n <= 1:
        return 1.0
    return max(0.2, min(1.0, 0.8 / math.sqrt(n - 1)))


def pipe_for(inner_min_mm: float, pipes: list, tol: float = 0.0):
    for ext, inner in pipes:
        if inner + tol >= inner_min_mm:
            return ext, inner
    return pipes[-1]


def pipe_for_flow(q_ls: float, vmax: float, pipes: list):
    """Plus petit tube dont la vitesse reste ≤ vmax pour le débit probable."""
    for ext, inner in pipes:
        sec = math.pi * (inner / 1000) ** 2 / 4
        if q_ls / 1000 / sec <= vmax:
            return ext, inner
    return pipes[-1]


def velocity(q_ls: float, inner_mm: float) -> float:
    sec = math.pi * (inner_mm / 1000) ** 2 / 4
    return q_ls / 1000 / sec if sec else 0.0
