"""Bordereau piscine : ouvrages de la bibliothèque ConstruPilot dimensionnés depuis la surface du bassin."""
import math

# (motif de désignation bibliothèque, unité attendue, fonction quantité, variante)
# variante : None = toujours ; "beton" / "coque" / "renovation" = seulement pour ce type de projet.
_RULES = [
    ("Terrassement piscine", "m³", lambda g: g["excav_m3"], ("beton", "coque")),
    ("Évacuation des terres", "m³", lambda g: g["excav_m3"] * 0.8, ("beton", "coque")),
    ("Couche de forme compactée", "m²", lambda g: g["floor"] * 1.15, ("beton", "coque")),
    ("Béton de propreté", "m²", lambda g: g["floor"] * 1.1, ("beton",)),
    ("Radier piscine béton armé", "m²", lambda g: g["floor"], ("beton",)),
    ("Ferraillage radier", "m²", lambda g: g["floor"], ("beton",)),
    ("Mur piscine blocs à bancher", "m²", lambda g: g["walls"], ("beton",)),
    ("Escalier maçonné", "u", lambda g: 1, ("beton",)),
    ("Enduit de dressage bassin", "m²", lambda g: g["floor"] + g["walls"], ("beton",)),
    ("Étanchéité cimentaire bassin", "m²", lambda g: g["floor"] + g["walls"], ("renovation",)),
    ("Liner 75/100", "m²", lambda g: (g["floor"] + g["walls"]) * 1.05, ("beton", "renovation")),
    ("Piscine coque polyester", "forfait", lambda g: 1, ("coque",)),
    ("Margelle béton reconstitué", "ml", lambda g: g["perim"], ("beton", "coque", "renovation")),
    ("Skimmer", "u", lambda g: max(1, math.ceil(g["floor"] / 25)), ("beton", "renovation")),
    ("Buse de refoulement", "u", lambda g: max(2, math.ceil(g["floor"] / 12)), ("beton",)),
    ("Bonde de fond", "u", lambda g: 1, ("beton",)),
    ("Projecteur LED piscine", "u", lambda g: 1 if g["floor"] < 30 else 2, ("beton", "coque")),
    ("Canalisation PVC pression Ø50", "ml", lambda g: g["perim"] + 12, ("beton", "coque")),
    ("Collecteur / vannes", "forfait", lambda g: 1, ("beton", "coque", "renovation")),
    ("Pompe filtration 0,75", "u", lambda g: 1, ("beton", "coque", "renovation")),
    ("Filtre à sable", "u", lambda g: 1, ("beton", "coque", "renovation")),
    ("Coffret électrique piscine", "u", lambda g: 1, ("beton", "coque")),
    ("Local technique filtration équipé", "forfait", lambda g: 1, ("beton", "coque")),
    ("Drainage périphérique", "ml", lambda g: g["perim"] + 4, ("beton", "coque")),
    ("Remblai périphérique gravier", "m³", lambda g: g["perim"] * 0.6 * 1.5, ("beton", "coque")),
    ("Plage piscine béton", "m²", lambda g: g["floor"] * 1.0, ("beton", "coque")),
    ("Mise en eau et mise en service", "forfait", lambda g: 1, ("beton", "coque", "renovation")),
]

_KIND = {"piscine_beton": "beton", "piscine_coque": "coque", "piscine_renovation": "renovation"}


def pool_geometry(surface_m2: float, depth_m: float = 1.5) -> dict:
    """Bassin rectangulaire 2:1 : longueur, largeur, périmètre, parois, fouille."""
    s = max(4.0, float(surface_m2 or 0))
    length = math.sqrt(2 * s)
    width = s / length
    perim = 2 * (length + width)
    walls = perim * depth_m
    excav = (length + 1.2) * (width + 1.2) * (depth_m + 0.35)
    return {"floor": round(s, 2), "length": round(length, 2), "width": round(width, 2),
            "perim": round(perim, 2), "walls": round(walls, 2), "excav_m3": round(excav, 2), "depth": depth_m}


def pool_lines(project_type: str, surface_m2: float, library: list[dict], depth_m: float = 1.5) -> dict:
    """Sélectionne dans `library` ([{designation, unit, unit_price_ht, cost_price_ht}]) les ouvrages piscine
    et calcule les quantités. Retourne {geometry, lines, total_ht}."""
    kind = _KIND.get(project_type, "beton")
    geo = pool_geometry(surface_m2, depth_m)
    lower = [(it.get("designation", "").lower(), it) for it in library]
    lines, used = [], set()
    for pattern, unit, qty_fn, kinds in _RULES:
        if kind not in kinds:
            continue
        pat = pattern.lower()
        cands = [it for d, it in lower if pat in d and it.get("unit_price_ht") and d not in used]
        if not cands:
            continue
        it = cands[0]
        if pattern.startswith("Piscine coque"):
            it = min(cands, key=lambda c: abs(_coque_area(c["designation"]) - geo["floor"]))
        used.add(it["designation"].lower())
        qty = round(float(qty_fn(geo)), 2)
        lines.append({"designation": it["designation"], "unit": it.get("unit") or unit, "qty": qty,
                      "unit_price_ht": float(it["unit_price_ht"]),
                      "cost_price_ht": float(it.get("cost_price_ht") or 0),
                      "total_ht": round(qty * float(it["unit_price_ht"]), 2),
                      "vat_rate": 20.0, "category": "Piscine"})
    return {"geometry": geo, "lines": lines, "total_ht": round(sum(l["total_ht"] for l in lines), 2)}


def _coque_area(designation: str) -> float:
    import re
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)", designation)
    if not m:
        return 24.0
    return float(m.group(1).replace(",", ".")) * float(m.group(2).replace(",", "."))
