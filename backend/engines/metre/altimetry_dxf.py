"""Altimetry labels of a formwork DXF: « Ai: 92,970 m » (arase inférieure) / « As: … » (arase supérieure) and reservation sizes « 40x20ht ».

Heights of structural elements follow only when both AS and AI exist for the same element; here the export carries reservation labels,
which are listed as such — never reused as storey heights.
"""
import re

LEVEL = re.compile(r"\b(A[isS])\s*[:=]?\s*([+-]?\d{1,3}[.,]\d{2,3})\s*m?\b")
SIZE = re.compile(r"\b(\d{2,4})\s*x\s*(\d{2,4})\s*(ht|h)?\b", re.I)


def _plain(t: str) -> str:
    return re.sub(r"\\[A-Za-z][^;]*;|[{}]", "", t).replace("\\P", " ")


def altimetry_labels(dxf_bytes: bytes) -> dict:
    import os
    import tempfile
    import ezdxf
    from ezdxf.recover import readfile as recover_readfile
    with tempfile.NamedTemporaryFile(suffix=".dxf", delete=False) as tmp:
        tmp.write(dxf_bytes)
    try:
        try:
            doc = ezdxf.readfile(tmp.name)
        except Exception:  # noqa: BLE001
            doc, _ = recover_readfile(tmp.name)
    finally:
        os.unlink(tmp.name)
    u = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}.get(doc.header.get("$INSUNITS", 0), 0.01)
    texts = []
    for e in doc.modelspace():
        if e.dxftype() in ("TEXT", "MTEXT"):
            texts.append({"layer": e.dxf.layer, "text": _plain(e.text if e.dxftype() == "MTEXT" else e.dxf.text).strip(), "x": e.dxf.insert.x * u, "y": e.dxf.insert.y * u})
    levels, sizes = [], []
    for t in texts:
        for m in LEVEL.finditer(t["text"]):
            levels.append({"kind": "AI" if m.group(1).lower() == "ai" else "AS", "level_m": float(m.group(2).replace(",", ".")), "layer": t["layer"], "x": round(t["x"], 2), "y": round(t["y"], 2), "raw": t["text"]})
        for m in SIZE.finditer(t["text"]):
            sizes.append({"w_cm": int(m.group(1)), "h_cm": int(m.group(2)), "layer": t["layer"], "x": round(t["x"], 2), "y": round(t["y"], 2), "raw": t["text"]})
    reservations = []
    for s in sizes:
        near = [l for l in levels if abs(l["x"] - s["x"]) <= 0.6 and abs(l["y"] - s["y"]) <= 0.6]
        reservations.append({**s, "ai_m": next((l["level_m"] for l in near if l["kind"] == "AI"), None), "as_m": next((l["level_m"] for l in near if l["kind"] == "AS"), None)})
    from engines.metre.level_symbols import parse_level_symbols
    symbols = parse_level_symbols([(t["x"] - 0.3, t["y"] - 0.1, t["x"] + 0.3, t["y"] + 0.1, t["text"]) for t in texts], radius_pt=0.9)
    ai = [l for l in levels if l["kind"] == "AI"]
    as_ = [l for l in levels if l["kind"] == "AS"]
    pairs = []
    for a in ai:
        s = next((x for x in as_ if abs(x["x"] - a["x"]) <= 0.6 and abs(x["y"] - a["y"]) <= 0.6), None)
        if s:
            pairs.append({"ai_m": a["level_m"], "as_m": s["level_m"], "height_m": round(s["level_m"] - a["level_m"], 3), "x": a["x"], "y": a["y"]})
    layers = sorted({l["layer"] for l in levels})
    only_reservations = bool(levels) and all(re.search(r"r[ée]serv", l, re.I) for l in layers)
    findings = []
    if not levels:
        findings.append({"severity": "to_clarify", "subject": "Aucune altimétrie", "explanation": "Aucun texte AI/AS dans le DXF."})
    elif not as_:
        findings.append({"severity": "to_clarify", "subject": "Arases supérieures absentes",
                         "explanation": f"{len(ai)} étiquettes AI (arase inférieure) lues, 0 AS : aucune hauteur d'élément (AS − AI) n'est déductible de ce fichier."})
    if only_reservations:
        findings.append({"severity": "info", "subject": "Altimétries limitées aux réservations",
                         "explanation": f"Les étiquettes AI se trouvent toutes sur le calque {', '.join(layers)} (réservations {len(reservations)} avec dimensions) : "
                                        "elles datent la sous-face des trémies/réservations, pas les arases des murs/poutres/dalle. Le plan de coffrage PDF (avec AS/AI des éléments) est nécessaire pour les volumes."})
    return {"unit_to_m": u, "levels": levels, "ai_count": len(ai), "as_count": len(as_), "element_heights": pairs, "reservations": reservations,
            "ai_range_m": [min(l["level_m"] for l in ai), max(l["level_m"] for l in ai)] if ai else None, "layers": layers, "findings": findings,
            "slab_symbols": {"count": len(symbols["symbols"]), "distinct_as_plancher_m": symbols["distinct_as_plancher_m"], "distinct_epaisseur_cm": symbols["distinct_epaisseur_cm"]}}
