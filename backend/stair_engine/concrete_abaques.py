"""Abaques indicatifs DTU 21 pour pré-dimensionnement de la paillasse.

Table simplifiée épaisseur paillasse minimale (mm) selon portée (mm) et charge totale (kN/m²).
Basé sur DTU 21 + retour d'expérience, béton C25/30 armature B500B.

⚠️ Pré-dimensionnement uniquement — validation BE requise pour exécution.
"""
from __future__ import annotations
from typing import Dict, Tuple

# portée_mm : { charge_totale_kN_m2 : épaisseur_min_mm }
PAILLASSE_THICKNESS_ABAQUE: Dict[int, Dict[int, int]] = {
    2000: {5: 120, 7: 140, 10: 160},
    2500: {5: 140, 7: 160, 10: 180},
    3000: {5: 160, 7: 180, 10: 200},
    3500: {5: 180, 7: 200, 10: 220},
    4000: {5: 200, 7: 220, 10: 240},
    4500: {5: 220, 7: 240, 10: 260},
    5000: {5: 240, 7: 260, 10: 280},
}

CONCRETE_CLASSES = {"C20/25", "C25/30", "C30/37"}
STEEL_GRADES = {"B500A", "B500B"}
EXPOSURE_CLASSES = {"XC1", "XC2", "XC3", "XC4"}

# Enrobage minimum en fonction de l'exposition (DTU 21 / EC2)
COVER_MM_BY_EXPOSURE = {"XC1": 20, "XC2": 25, "XC3": 30, "XC4": 35}


def lookup_paillasse_thickness(span_mm: float, load_total_kN_m2: float) -> Tuple[float, str, bool]:
    """Retourne (épaisseur_recommandée_mm, abaque_ligne_utilisée, out_of_abaque)."""
    if span_mm > 5000 or load_total_kN_m2 > 10:
        return (0, "out_of_range", True)

    spans = sorted(PAILLASSE_THICKNESS_ABAQUE.keys())
    # Trouver les 2 portées encadrant span_mm
    if span_mm <= spans[0]:
        lo_span, hi_span = spans[0], spans[0]
    elif span_mm >= spans[-1]:
        lo_span, hi_span = spans[-1], spans[-1]
    else:
        lo_span = max(s for s in spans if s <= span_mm)
        hi_span = min(s for s in spans if s >= span_mm)

    def _thickness_at(span_key: int, load: float) -> float:
        row = PAILLASSE_THICKNESS_ABAQUE[span_key]
        loads = sorted(row.keys())
        if load <= loads[0]:
            return float(row[loads[0]])
        if load >= loads[-1]:
            return float(row[loads[-1]])
        lo_l = max(l for l in loads if l <= load)
        hi_l = min(l for l in loads if l >= load)
        if lo_l == hi_l:
            return float(row[lo_l])
        t_lo = row[lo_l]
        t_hi = row[hi_l]
        return t_lo + (t_hi - t_lo) * (load - lo_l) / (hi_l - lo_l)

    t_lo = _thickness_at(lo_span, load_total_kN_m2)
    if hi_span == lo_span:
        t = t_lo
    else:
        t_hi = _thickness_at(hi_span, load_total_kN_m2)
        t = t_lo + (t_hi - t_lo) * (span_mm - lo_span) / (hi_span - lo_span)

    # Arrondi 10mm supérieur (sécurité)
    thickness = int(-(-t // 10)) * 10
    return (float(thickness), f"span={lo_span}-{hi_span}mm, load={load_total_kN_m2:.1f}kN/m²", False)
