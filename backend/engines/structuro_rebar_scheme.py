"""Plans d'exécution / ferraillage : du A_s (Lot 2 EN 1992) au schéma d'armatures.

Déterministe : choix du nombre de barres et de la cadence des cadres pour COUVRIR
l'acier nécessaire. Ne vérifie pas les dispositions constructives (recouvrements,
ancrages, espacements mini/maxi, enrobage) : à vérifier par l'ingénieur.
"""
from __future__ import annotations

import math

VERSION = "rebar-scheme-0.1.0"
BARS = [8, 10, 12, 14, 16, 20, 25, 32]  # diamètres courants (mm)
SOURCE = "Choix d'armatures couvrant l'As calculé (EN 1992 Lot 2) — dispositions constructives à vérifier."


def _area_cm2(phi_mm: float, n: int = 1) -> float:
    return n * math.pi * phi_mm * phi_mm / 4 / 100.0


def scheme(as_req_cm2: float, asw_s_req_cm2_m: float = 0.0, *, bar_mm: int = 16,
           stirrup_mm: int = 8, legs: int = 2, s_max_m: float = 0.30) -> dict:
    if bar_mm not in BARS or stirrup_mm not in BARS:
        raise ValueError("Diamètre non catalogué")
    as_bar = _area_cm2(bar_mm)
    n = max(2, math.ceil(as_req_cm2 / as_bar)) if as_req_cm2 > 0 else 2
    longitudinal = {"bar_mm": bar_mm, "count": n, "as_provided_cm2": round(n * as_bar, 2),
                    "as_req_cm2": round(as_req_cm2, 2), "label": f"{n}Ø{bar_mm}",
                    "note": "As,prov ≥ As,req ; recouvrements/ancrages/espacements à vérifier."}
    stirrups = None
    if asw_s_req_cm2_m and asw_s_req_cm2_m > 0:
        asw_one = _area_cm2(stirrup_mm, legs)
        s_calc = asw_one / asw_s_req_cm2_m
        s_adopt = min(math.floor(s_calc / 0.025) * 0.025, s_max_m) if s_calc > 0 else s_max_m
        s_adopt = max(s_adopt, 0.05)
        stirrups = {"stirrup_mm": stirrup_mm, "legs": legs, "s_calc_m": round(s_calc, 3),
                    "s_adopt_m": round(s_adopt, 3), "s_max_m": round(s_max_m, 3),
                    "asw_s_req_cm2_m": round(asw_s_req_cm2_m, 2),
                    "asw_s_prov_cm2_m": round(asw_one / s_adopt, 2) if s_adopt > 0 else None,
                    "label": f"Ø{stirrup_mm} ({legs} brins) e={round(s_adopt, 3)} m"}
    return {"version": VERSION, "longitudinal": longitudinal, "stirrups": stirrups,
            "bars_catalog": BARS, "source": SOURCE, "execution_ready": False}
