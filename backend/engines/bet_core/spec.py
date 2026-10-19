"""Désignations des ouvrages (matériaux) — valeurs par défaut quand le client ne précise rien.

Défauts France (demande du fondateur, 19/10/2026) quand un PC est joint sans autre précision :
  - dallage du sous-sol (s'il existe) : béton armé C25/30 20 cm ;
  - semelles : béton armé C25/30, classe d'exposition XC2 ;
  - murs porteurs du sous-sol : blocs à bancher 20 cm remplis de béton armé ;
  - murs à partir du RDC : brique terre cuite Isobric 20 cm (joint mince) ;
  - planchers : poutrelles-hourdis ;
  - charpente : traditionnelle.
Toute précision du client (user_hypotheses) l'emporte. Les propriétés mécaniques de la brique (f_k, f_b) restent les
valeurs prudentes communes aux briques de 20 cm à perforations verticales, à confirmer par la DoP du fabricant.
"""
from __future__ import annotations

BRICKS = {
    "brique_isobric_20": {"short": "Isobric 20", "name": "Brique terre cuite Isobric 20 (joint mince)"},
    "brique_porotherme_20": {"short": "Porotherme 20", "name": "Brique terre cuite Porotherme 20 (R20 / Th+), joint mince"},
    "brique_20": {"short": "brique 20", "name": "Brique terre cuite 20 cm à perforations verticales, joint mince"},
}
BASEMENT_WALLS = {
    "bloc_a_bancher_20": {"short": "blocs à bancher 20", "core": 0.15, "buried": "Murs en blocs à bancher 20 enterrés",
                          "name": "Murs en blocs à bancher 20 cm remplis de béton C25/30 armé hydrofugé"},
    "voile_ba_20": {"short": "voile BA 20", "core": 0.20, "buried": "Voiles BA 20 enterrés",
                    "name": "Voiles périphériques BA 20 C25/30 hydrofugé"},
}
DEFAULTS = {
    "FR": {"masonry": "brique_isobric_20", "basement_wall": "bloc_a_bancher_20", "floor_system": "poutrelles_hourdis",
           "roof_structure": "charpente_traditionnelle", "foundation_exposure": "XC2", "basement_slab_cm": 20},
    "PT": {"masonry": "brique_20", "basement_wall": "voile_ba_20", "floor_system": "poutrelles_hourdis",
           "roof_structure": "charpente_traditionnelle", "foundation_exposure": "XC2", "basement_slab_cm": 20},
}


def apply_defaults(raw: dict) -> dict:
    """Complète user_hypotheses avec les défauts du pays, sans écraser ce que le client a précisé."""
    country = ((raw.get("project") or {}).get("country") or "FR").upper()
    uh = raw.setdefault("user_hypotheses", {})
    for k, v in DEFAULTS.get(country, DEFAULTS["FR"]).items():
        uh.setdefault(k, v)
    if uh.get("masonry") not in BRICKS:
        uh["masonry"] = DEFAULTS.get(country, DEFAULTS["FR"])["masonry"]
    if uh.get("basement_wall") not in BASEMENT_WALLS:
        uh["basement_wall"] = DEFAULTS.get(country, DEFAULTS["FR"])["basement_wall"]
    return raw


def of(m) -> dict:
    uh = m.raw.get("user_hypotheses") or {}
    brick = BRICKS.get(uh.get("masonry"), BRICKS["brique_isobric_20"])
    bw = BASEMENT_WALLS.get(uh.get("basement_wall"), BASEMENT_WALLS["bloc_a_bancher_20"])
    exp = uh.get("foundation_exposure") or "XC2"
    return {"masonry": uh.get("masonry", "brique_isobric_20"), "brick": brick["short"], "brick_name": brick["name"],
            "basement_wall": uh.get("basement_wall", "bloc_a_bancher_20"), "bw": bw["short"], "bw_name": bw["name"],
            "bw_buried": bw["buried"],
            "bw_core": bw["core"], "bw_blocks": uh.get("basement_wall", "bloc_a_bancher_20") == "bloc_a_bancher_20",
            "exposure": exp, "slab_cm": int(uh.get("basement_slab_cm") or 20)}
