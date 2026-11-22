"""Medição de uma planta de cofragem por FACES ENTRE CAMADAS (lajes, paredes, vigas, pilares).

Problema (processo «RDC + GRUE», 22/11/2026): em exportações Revit/BEGT o contorno de uma laje só se fecha com as linhas das
paredes e das vigas, e as paredes são pares de linhas interrompidas pelas aberturas. Medidas camada a camada, as faces fechadas
davam 90 m² de laje num PH-1 de ~3 000 m² e ~280 ml de paredes por piso em vez de ~550 ml.

Método: todas as linhas estruturais (paredes cortadas, vigas, laje, pilares, lintéis) são unidas e poligonizadas; cada face é
classificada pela camada das arestas que a delimitam:
  - face larga (círculo inscrito ≥ 85 cm)                    → painel de laje
  - face estreita delimitada sobretudo por paredes            → corpo de parede (≥ 7,5 cm; abaixo: isolante/doublage excluído)
  - face estreita delimitada sobretudo por vigas              → viga (largura em planta)
  - face pequena delimitada por pilares                       → pilar
  - face estreita delimitada por lintéis/portas               → abertura (não é betão de parede)
Nenhuma dimensão é lida de nomes de blocos ou textos; espessura = diâmetro do maior círculo inscrito da face.
"""
from __future__ import annotations

import math
import re
from collections import Counter, defaultdict

THIN_M = 0.85            # largura abaixo da qual uma face é um corpo (parede/viga) e não um painel de laje
INSUL_M = 0.075          # corpos de parede mais finos: isolante / doublage (fora do betão)
MASONRY_RANGE = (0.075, 0.125)   # 8-12 cm: possível alvenaria de blocos (ex. boxes de parque) — a confirmar pelo utilizador


def _tag(role: str) -> str:
    return {"wall": "W", "beam": "B", "slab": "S", "column": "C", "lintel": "L"}[role]


def _segments(msp, layers: dict, u: float):
    from ezdxf import path
    from shapely.geometry import LineString
    roles = {}
    for role, names in layers.items():
        names = {n for n in names if "iden" not in n.lower()}           # camadas de etiquetas (tags Revit)
        if role in ("wall", "column") and any("coup" in n.lower() for n in names):
            # Revit/BEGT: «… coupé» = elementos cortados pelo plano; os vistos (não cortados) pertencem a outro piso.
            names = {n for n in names if "coup" in n.lower() or n.strip().upper() == "MURS"}
        roles[role] = names
    by_layer = {name: _tag(role) for role, names in roles.items() if role in ("wall", "beam", "slab", "column", "lintel") for name in names}
    segs = []

    def add(e, tag):
        try:
            pts = [(v.x * u, v.y * u) for v in path.make_path(e).flattening(0.01 / u)]
        except Exception:  # noqa: BLE001 — entidade sem caminho (texto, etc.)
            return
        for a, b in zip(pts, pts[1:]):
            if a != b:
                segs.append((LineString([a, b]), tag))

    for e in msp:
        tag = by_layer.get(e.dxf.layer)
        if not tag:
            continue
        if e.dxftype() == "INSERT" and tag != "L":
            continue                                                    # blocos = símbolos/etiquetas; só as portas (lintéis) contam
        if e.dxftype() == "INSERT":
            try:
                for x in e.virtual_entities():
                    if x.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE"):
                        add(x, tag)
            except Exception:  # noqa: BLE001
                continue
        elif e.dxftype() in ("LINE", "LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE"):
            add(e, tag)
    return segs


def measure(msp, layers: dict, u: float) -> dict:
    import shapely
    from shapely.ops import polygonize, unary_union
    from shapely.strtree import STRtree
    segs = _segments(msp, layers, u)
    if not segs:
        return {"ok": False}
    geoms = [s for s, _ in segs]
    tags = [t for _, t in segs]
    tree = STRtree(geoms)
    faces = [p for p in polygonize(unary_union(geoms)) if p.area > 0.01]
    out = {"slab": [], "wall": [], "beam": [], "column": [], "opening": [], "insulation": []}
    for p in faces:
        ring = p.exterior.buffer(0.005)
        comp = Counter()
        for i in tree.query(ring):
            ov = geoms[i].intersection(ring).length
            if ov > 0:
                comp[tags[i]] += ov
        tot = sum(comp.values()) or 1.0
        c = {k: v / tot for k, v in comp.items()}
        try:
            width = 2 * shapely.maximum_inscribed_circle(p, 0.005).length
        except Exception:  # noqa: BLE001
            width = 2 * p.area / max(p.length / 2, 1e-6)
        w, b, col, lin = c.get("W", 0), c.get("B", 0), c.get("C", 0), c.get("L", 0)
        rec = {"poly": p, "area": p.area, "width": width, "length": p.area / max(width, 1e-3)}
        if col > 0.5 and p.area < 2.5:
            out["column"].append(rec)
        elif width >= THIN_M:
            out["slab"].append(rec)
        elif lin > max(w, b) and lin >= 0.3:
            out["opening"].append(rec)
        elif w == 0 and b == 0:
            out["slab"].append(rec)                   # faixa só com arestas de laje (junta, banda)
        elif w >= b:
            (out["insulation"] if width < INSUL_M else out["wall"]).append(rec)
        else:
            out["beam"].append(rec)
    out["ok"] = True
    return out


def summary(m: dict) -> dict:
    """Quantidades em planta, no formato de coffrage_takeoff."""
    def by_width(items):
        d = defaultdict(float)
        for r in items:
            d[f"{round(r['width'] * 100)} cm"] += r["length"]
        return {k: round(v, 2) for k, v in sorted(d.items(), key=lambda kv: int(kv[0].split()[0])) if v >= 0.3}
    walls, beams, slab = m["wall"], m["beam"], m["slab"]
    masonry = [r for r in walls if MASONRY_RANGE[0] <= r["width"] < MASONRY_RANGE[1]]
    return {
        "slab": {"net_area_m2": round(sum(r["area"] for k in ("slab", "wall", "beam", "column", "opening") for r in m[k]), 2), "panels": len(slab),
                 "panels_area_m2": round(sum(r["area"] for r in slab), 2),
                 "formula": "Σ painéis de laje + topos de paredes, vigas, pilares e aberturas (a laje cobre-os até à AI); isolante exterior excluído"},
        "walls": {"count": len(walls), "plan_area_m2": round(sum(r["area"] for r in walls), 2), "length_total_m": round(sum(r["length"] for r in walls), 2),
                  "length_by_thickness_m": by_width(walls),
                  "thin_layers_excluded": {"count": len(m["insulation"]), "plan_area_m2": round(sum(r["area"] for r in m["insulation"]), 2),
                                           "note": "corpos < 7,5 cm (isolante / doublage) excluídos do betão"},
                  "possible_masonry_8_12cm": {"length_m": round(sum(r["length"] for r in masonry), 2), "plan_area_m2": round(sum(r["area"] for r in masonry), 2),
                                              "note": "paredes de 8-12 cm: podem ser alvenaria de blocos (ex. boxes de parque de 10 cm) — confirmar antes de contar como betão"}},
        "beams": {"count": len(beams), "length_total_m": round(sum(r["length"] for r in beams), 2), "plan_area_m2": round(sum(r["area"] for r in beams), 2),
                  "width_by_cm_m": by_width(beams)},
        "columns": {"count": len(m["column"]), "section_total_m2": round(sum(r["area"] for r in m["column"]), 3)},
        "method": "faces entre camadas (paredes + vigas + laje + pilares + lintéis)",
    }


_NGF = re.compile(r"(\d{2,3}[.,]\d{1,3})\s*(?:NGF|m\b)?", re.I)


def level_labels(msp, u: float) -> dict:
    """Etiquetas impressas na planta: laje «B / espessura / cota NGF» (camada *FLOR-IDEN*) e textos «Ai: …» / «As: …».
    Regra do utilizador: parede = AS da laje de baixo → AI da laje de cima; os valores vêm sempre das etiquetas, nunca de uma altura típica."""
    thick, lv, ai, as_ = [], [], [], []
    for e in msp.query("TEXT MTEXT"):
        t = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).replace("\n", " ").strip()
        p = e.dxf.insert
        xy = (round(p.x * u, 2), round(p.y * u, 2))
        lay = e.dxf.layer.upper()
        if "FLOR-IDEN" in lay and re.fullmatch(r"\d{2}", t):
            thick.append({"cm": int(t), "xy": xy})
        elif "FLOR-IDEN" in lay and "NGF" in t.upper() and (m := _NGF.search(t)):
            lv.append({"ngf": float(m.group(1).replace(",", ".")), "xy": xy})
        elif re.match(r"^A[iI]\s*:", t) and "fini" not in t.lower() and (m := _NGF.search(t)):
            ai.append({"ngf": float(m.group(1).replace(",", ".")), "xy": xy, "layer": e.dxf.layer})
        elif re.match(r"^\(?A[sS]\s*:", t) and (m := _NGF.search(t)):
            as_.append({"ngf": float(m.group(1).replace(",", ".")), "xy": xy})
    slabs = []
    for th in thick:
        near = min(lv, key=lambda v: (v["xy"][0] - th["xy"][0]) ** 2 + (v["xy"][1] - th["xy"][1]) ** 2, default=None)
        if near and math.dist(near["xy"], th["xy"]) < 2.0:
            slabs.append({"as_ngf": near["ngf"], "thickness_cm": th["cm"], "ai_ngf": round(near["ngf"] - th["cm"] / 100, 3), "xy": th["xy"]})
    dom = Counter((s["as_ngf"], s["thickness_cm"]) for s in slabs).most_common(1)
    return {"slab_tags": slabs, "ai_texts": ai, "as_texts": as_,
            "dominant": {"as_plancher_haut_m": dom[0][0][0], "epaisseur_dalle_m": dom[0][0][1] / 100} if dom else None,
            "note": "Etiquetas lidas na planta. AI laje = AS − espessura. A base das paredes é a AS da laje do piso inferior (planta de baixo)."}
