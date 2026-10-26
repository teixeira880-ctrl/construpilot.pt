# Copie embarquée de engines/calc_lots/climat.py (site .fr) pour que le moteur ossature soit identique sur .fr et .pt.
"""Données climatiques : zone réglementaire H1/H2/H3 par département (découpage RT2012 / CEE) et températures extérieures de base."""
from __future__ import annotations

ZONE_H1 = {"01", "02", "03", "05", "08", "10", "14", "15", "19", "21", "23", "25", "27", "28",
           "38", "39", "42", "43", "45", "51", "52", "54", "55", "57", "58", "59", "60", "61",
           "62", "63", "67", "68", "69", "70", "71", "73", "74", "75", "76", "77", "78", "80",
           "87", "88", "89", "90", "91", "92", "93", "94", "95", "975"}
ZONE_H2 = {"04", "07", "09", "12", "16", "17", "18", "22", "24", "26", "29", "31", "32", "33",
           "35", "36", "37", "40", "41", "44", "46", "47", "48", "49", "50", "53", "56", "64",
           "65", "72", "79", "81", "82", "84", "85", "86"}
ZONE_H3 = {"06", "11", "13", "20", "30", "34", "66", "83", "971", "972", "973", "974", "976"}


def departement(code_postal: str | None) -> str | None:
    c = (code_postal or "").strip().upper()
    if not c:
        return None
    if c.startswith(("97", "98")):
        return c[:3]
    if c[:2] in ("2A", "2B", "20"):
        return "20"
    return c[:2] if c[:2].isdigit() else None


def zone(code_postal: str | None) -> str | None:
    d = departement(code_postal)
    if not d:
        return None
    return "H3" if d in ZONE_H3 else "H2" if d in ZONE_H2 else "H1" if d in ZONE_H1 else None


# Température extérieure de base au niveau de la mer par département (°C) — table usuelle dérivée de la carte des zones
# NF P52-612/CN (zones A à I). Contrôles : 29 Brest −4, 67 Strasbourg −15, 76 Le Havre −7, 86 Poitiers −7, 05 −10 (Briançon −19 à 1 200 m).
TB_DEPT = {"01": -10, "02": -7, "03": -8, "04": -8, "05": -10, "06": -5, "07": -6, "08": -10, "09": -5, "10": -10, "11": -5, "12": -8,
           "13": -5, "14": -7, "15": -8, "16": -5, "17": -5, "18": -7, "19": -8, "20": -2, "21": -10, "22": -4, "23": -8, "24": -5,
           "25": -12, "26": -6, "27": -7, "28": -7, "29": -4, "30": -5, "31": -5, "32": -5, "33": -5, "34": -5, "35": -4, "36": -7,
           "37": -7, "38": -10, "39": -10, "40": -5, "41": -7, "42": -10, "43": -8, "44": -5, "45": -7, "46": -6, "47": -5, "48": -8,
           "49": -7, "50": -4, "51": -10, "52": -12, "53": -7, "54": -15, "55": -12, "56": -4, "57": -15, "58": -10, "59": -9, "60": -7,
           "61": -7, "62": -9, "63": -8, "64": -5, "65": -5, "66": -5, "67": -15, "68": -15, "69": -10, "70": -10, "71": -10, "72": -7,
           "73": -10, "74": -10, "75": -5, "76": -7, "77": -7, "78": -7, "79": -7, "80": -9, "81": -5, "82": -5, "83": -5, "84": -6,
           "85": -5, "86": -7, "87": -8, "88": -15, "89": -10, "90": -15, "91": -7, "92": -7, "93": -7, "94": -7, "95": -7}
ZONE_DE_TB = {-2: "A", -4: "B", -5: "C", -7: "D", -8: "E", -9: "F", -10: "G", -12: "H", -15: "I"}
# θe de base par zone et tranche d'altitude (NF EN 12831, tableau national) — None = hors domaine
_ALT = [200, 400, 600, 800, 1000, 1200, 1400, 1600, 1800, 2000, 2200]
TB_ALT = {"A": [-2, -4, -6, -8, -10, -12, -14, -16, -18, -20, None], "B": [-4, -5, -6, -7, -8, -9, -10, None, None, None, None],
          "C": [-5, -6, -7, -8, -9, -10, -11, -12, -13, -14, -15], "D": [-7, -8, -9, -11, -13, -14, -15, None, None, None, None],
          "E": [-8, -9, -11, -13, -15, -17, -19, -21, -23, -25, -27], "F": [-9, -10, -11, -12, -13, None, None, None, None, None, None],
          "G": [-10, -11, -13, -14, -17, -19, -21, -23, -24, -25, -29], "H": [-12, -13, -15, -17, -19, -21, -23, -24, None, None, None],
          "I": [-15, -15, -19, -21, -23, -24, -25, None, None, None, None]}
DOM_TB = {"971": 20, "972": 20, "973": 20, "974": 15, "976": 20}


def temperature_base(code_postal: str | None, altitude_m: float = 0.0) -> tuple[float, str]:
    """→ (θe de base °C, origine). Hors table : −10 °C par défaut (signalé)."""
    d = departement(code_postal)
    if d in DOM_TB:
        return float(DOM_TB[d]), f"DOM {d} (climat tropical : déperditions de chauffage non pertinentes)"
    if not d or d not in TB_DEPT:
        return -10.0, "défaut (département inconnu)"
    z = ZONE_DE_TB[TB_DEPT[d]]
    i = next((k for k, a in enumerate(_ALT) if altitude_m <= a), None)
    if i is None or TB_ALT[z][i] is None:
        raise ValueError(f"altitude {altitude_m:g} m hors du tableau pour la zone {z} : fournissez theta_e")
    return float(TB_ALT[z][i]), f"département {d}, zone {z}, altitude {altitude_m:g} m (table départementale usuelle, correction d’altitude NF EN 12831)"
