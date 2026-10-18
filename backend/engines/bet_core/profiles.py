"""Profils pays : langue, normes, matériaux, TVA, bibliothèque de prix, normes MEP, séisme.

Le moteur de calcul reste unique (Eurocodes) ; le profil fixe les Annexes nationales,
les références réglementaires affichées, la langue des livrables et les prix indicatifs.
"""
from __future__ import annotations

FR = {
    "country": "FR", "lang": "fr", "currency": "EUR",
    "norms": ["NF EN 1990", "NF EN 1991-1-1/-1-3", "NF EN 1992-1-1", "NF EN 1995-1-1", "NF EN 1996-1-1", "NF EN 1997-1 + AN",
              "NF P 94-261", "NF DTU 13.11, 13.3, 20.1, 21, 31.1, 40.21", "NF C 15-100", "NF DTU 60.1 / 60.11"],
    "norms_text": "NF EN 1990, 1991-1-1/-1-3, 1992-1-1, 1995-1-1, 1996-1-1, 1997-1 + AN ; NF P 94-261 ; NF DTU 13.11, 13.3, 20.1, 21, 31.1, 40.21 ; NF C 15-100 ; NF DTU 60.1 / 60.11",
    "steel": "B500B", "concrete": "C25/30",
    "vat": 0.20, "vat_note": "TVA 20 % (construction neuve)",
    "price_ref": "IDF 2026", "price_ref_long": "Île-de-France 2026",
    "electrical": "NF C 15-100", "plumbing": "NF DTU 60.11", "electrical_short": "NF C 15-100", "plumbing_short": "DTU 60.11",
    "seismic": "Zonage sismique de la France (arrêté du 22/10/2010) — zone 1 : aucune disposition exigée pour une maison individuelle",
    "price_factor": 1.0, "prices": {},
}

# Prix indicatifs Portugal continental 2026 (Norte / Lisboa), € sem IVA, fornecido e assente.
PT_PRICES = {
    "terr_masse": 12.0, "decap": 4.0, "blindage": 90.0, "fouille_rigole": 18.0, "evac": 14.0,
    "semelle": 210.0, "proprete": 9.0, "voile20": 320.0, "coffrage": 22.0, "voile15": 420.0, "gnt": 12.0, "dallage": 160.0,
    "impermea": 45.0, "plancher": 48.0, "porotherme": 38.0, "pignon": 42.0,
    "ch_h": 22.0, "ch_v": 20.0, "ch_r": 24.0, "linteau": 60.0, "poteau": 180.0,
    "escalier": 1800.0, "enduit": 16.0, "inst_chantier": 3500.0,
    "panne": 55.0, "chevron": 8.0, "sabliere": 13.0, "sommier": 70.0, "lucarne": 1600.0,
    "couverture": 32.0, "gouttiere": 28.0, "descente": 22.0, "isol_rampant": 24.0,
    "pc": 38.0, "pl": 42.0, "inter": 28.0, "rj45": 55.0, "spec": 90.0,
    "tableau": 850.0, "gtl": 350.0, "terre": 280.0, "vmc": 650.0, "volet_circ": 70.0,
    "wc": 380.0, "lavabo": 300.0, "lave_mains": 190.0, "douche": 650.0, "baignoire": 600.0,
    "evier": 260.0, "attente": 85.0, "robinet_ext": 90.0, "cet": 1650.0,
    "nourrice": 950.0, "multicouche": 5.5, "chute": 22.0, "collecteur": 26.0,
    "relevage": 900.0, "branchement": 600.0,
    "visa_bet": 2400.0, "g2pro": 1500.0,
}

PT = {
    "country": "PT", "lang": "pt", "currency": "EUR",
    "norms": ["NP EN 1990", "NP EN 1991-1-1/-1-3/-1-4", "NP EN 1992-1-1", "NP EN 1995-1-1", "NP EN 1996-1-1", "NP EN 1997-1",
              "NP EN 1998-1 + Anexos Nacionais", "NP EN 206 + LNEC E 464", "LNEC E 460 / E 455 (A500NR)",
              "RTIEBT – Portaria 949-A/2006 + ITED", "Decreto Regulamentar 23/95 (RGSPPDADAR)"],
    "norms_text": "NP EN 1990, 1991-1-1/-1-3/-1-4, 1992-1-1, 1995-1-1, 1996-1-1, 1997-1, 1998-1 + Anexos Nacionais ; NP EN 206 + LNEC E 464 ; "
                  "LNEC E 460 (A500NR) ; RTIEBT – Portaria 949-A/2006 + ITED ; Decreto Regulamentar 23/95 (RGSPPDADAR)",
    "steel": "A500NR", "concrete": "C25/30",
    "vat": 0.23,
    "vat_note": "IVA 23 % (taxa normal ; a taxa reduzida de 6 % pode aplicar-se a certas empreitadas de habitação — confirmar com o contabilista)",
    "price_ref": "Portugal 2026", "price_ref_long": "Portugal continental 2026 (Norte / Lisboa)",
    "electrical": "RTIEBT – Portaria 949-A/2006 + ITED", "plumbing": "Decreto Regulamentar 23/95 (RGSPPDADAR)",
    "electrical_short": "RTIEBT + ITED", "plumbing_short": "DR 23/95",
    "seismic": "NP EN 1998-1 + Anexo Nacional : ações sísmicas tipo 1 (afastada) e tipo 2 (próxima), zonamento por concelho",
    "price_factor": None, "prices": PT_PRICES,
}

PROFILES = {"FR": FR, "PT": PT}


def profile(country: str | None) -> dict:
    return PROFILES.get((country or "FR").upper(), FR)


def price(country: str | None, key: str, fr_value: float) -> float:
    p = profile(country)
    if p["prices"]:
        return p["prices"].get(key, round(fr_value * 0.55, 2))
    return fr_value * (p["price_factor"] or 1.0)
