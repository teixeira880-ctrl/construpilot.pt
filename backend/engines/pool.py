"""Bordereau piscine : ouvrages de la bibliothèque ConstruPilot dimensionnés depuis la surface du bassin."""
import math

# (motif de désignation bibliothèque, unité attendue, fonction quantité, variante)
# variante : None = toujours ; "beton" / "coque" / "renovation" = seulement pour ce type de projet.
_RULES = [
    ("Movimento de terras da piscina", "m³", lambda g: g["excav_m3"], ("beton", "coque")),
    ("Remoção de terras", "m³", lambda g: g["excav_m3"] * 0.8, ("beton", "coque")),
    ("Camada de forma compactada", "m²", lambda g: g["floor"] * 1.15, ("beton", "coque")),
    ("Betão de limpeza", "m²", lambda g: g["floor"] * 1.1, ("beton",)),
    ("Laje de piscina em betão armado", "m²", lambda g: g["floor"], ("beton",)),
    ("Armaduras do ensoleiramento", "m²", lambda g: g["floor"], ("beton",)),
    ("Parede de piscina em blocos de cofragem", "m²", lambda g: g["walls"], ("beton",)),
    ("Escada de alvenaria", "u", lambda g: 1, ("beton",)),
    ("Reboco de regularização do tanque", "m²", lambda g: g["floor"] + g["walls"], ("beton",)),
    ("Impermeabilização cimentícia tanque", "m²", lambda g: g["floor"] + g["walls"], ("renovation",)),
    ("Liner 75/100", "m²", lambda g: (g["floor"] + g["walls"]) * 1.05, ("beton", "renovation")),
    ("Piscina monobloco em poliéster", "forfait", lambda g: 1, ("coque",)),
    ("Borda de betão reconstituído", "ml", lambda g: g["perim"], ("beton", "coque", "renovation")),
    ("Skimmer", "u", lambda g: max(1, math.ceil(g["floor"] / 25)), ("beton", "renovation")),
    ("Bico de retorno", "u", lambda g: max(2, math.ceil(g["floor"] / 12)), ("beton",)),
    ("Ralo de fundo", "u", lambda g: 1, ("beton",)),
    ("Projecteur LED piscine", "u", lambda g: 1 if g["floor"] < 30 else 2, ("beton", "coque")),
    ("Canalisation PVC pression Ø50", "ml", lambda g: g["perim"] + 12, ("beton", "coque")),
    ("Collecteur / vannes", "forfait", lambda g: 1, ("beton", "coque", "renovation")),
    ("Pompe filtration 0,75", "u", lambda g: 1, ("beton", "coque", "renovation")),
    ("Filtro de areia", "u", lambda g: 1, ("beton", "coque", "renovation")),
    ("Quadro elétrico piscina", "u", lambda g: 1, ("beton", "coque")),
    ("Casa técnica de filtração equipada", "forfait", lambda g: 1, ("beton", "coque")),
    ("Drenagem periférica", "ml", lambda g: g["perim"] + 4, ("beton", "coque")),
    ("Aterro periférico gravilha", "m³", lambda g: g["perim"] * 0.6 * 1.5, ("beton", "coque")),
    ("Praia de piscina em betão", "m²", lambda g: g["floor"] * 1.0, ("beton", "coque")),
    ("Enchimento e colocação em serviço", "forfait", lambda g: 1, ("beton", "coque", "renovation")),
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
                      "vat_rate": 23.0, "category": "Piscina"})
    return {"geometry": geo, "lines": lines, "total_ht": round(sum(l["total_ht"] for l in lines), 2)}


def _coque_area(designation: str) -> float:
    import re
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*x\s*(\d+(?:[.,]\d+)?)", designation)
    if not m:
        return 24.0
    return float(m.group(1).replace(",", ".")) * float(m.group(2).replace(",", "."))
