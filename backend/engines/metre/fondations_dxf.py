"""Fundações a partir do DWG/DXF de cofragem (plantas Revit «Fondations / Etiquettes de fondations» e norma AES «AES-Semelle»):

- junta os fragmentos de etiqueta (MTEXT) em rótulos completos por proximidade: «S 9 | 250 x 420 x 65 ht | (As: 50.92)»,
  «SF 06 | 50 x 40 ht | (As: 50.92)»;
- fecha os contornos desenhados (LINE/LWPOLYLINE + blocos de sapata) em polígonos e casa cada polígono com o rótulo mais próximo;
- sapata isolada (S, 3 dimensões): volume = A × B × ht do rótulo, confirmado se o polígono tiver a mesma área (±15 %);
- sapata contínua (SF, secção L×ht): volume = área do polígono × ht; comprimento = área / largura;
- nada é inventado: sem rótulo, sem altura ou com rótulo ilegível, a linha fica «indeterminate» com o texto cru no finding.
"""
from __future__ import annotations

import io
import math
import re
from collections import Counter

_LABEL_LAYER = re.compile(r"etiquette.*fond|fond.*txt|semelle[-_ ]?txt", re.I)
_GEOM_LAYER = re.compile(r"^fondations?$|semelle(?![-_ ]?txt)|^AES-Semelle$", re.I)
_BACKGROUND = re.compile(r"plan de charge|_dwg$|gabarit|fond de plan", re.I)
_REF = re.compile(r"\b(SF|S|LS|R)\s*-?\s*(\d{1,2})\b")
_DIMS3 = re.compile(r"(\d{2,3})\s*[xX]\s*(\d{2,3})\s*[xX]\s*(\d{2,3})\s*ht?")
_DIMS2 = re.compile(r"(\d{2,3})\s*[xX]\s*(\d{2,3})\s*ht\b")
_AS = re.compile(r"As\s*[: ]\s*(\d{2,3}[.,]\d{1,3})")

_UNITS = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}


def _read(dxf_bytes: bytes):
    import ezdxf
    from ezdxf import recover
    try:
        return ezdxf.read(io.StringIO(dxf_bytes.decode("utf-8", "ignore")))
    except Exception:  # noqa: BLE001
        doc, _ = recover.read(io.BytesIO(dxf_bytes))
        return doc


def _clusters(texts: list[tuple[float, float, str]], radius: float) -> list[dict]:
    used = [False] * len(texts)
    out = []
    for i, (x, y, t) in enumerate(texts):
        if used[i]:
            continue
        grp = [(x, y, t)]
        used[i] = True
        changed = True
        while changed:
            changed = False
            for j, (x2, y2, t2) in enumerate(texts):
                if not used[j] and any((x2 - a) ** 2 + (y2 - b) ** 2 < radius ** 2 for a, b, _ in grp):
                    grp.append((x2, y2, t2))
                    used[j] = True
                    changed = True
        grp.sort(key=lambda g: (-round(g[1], 1), g[0]))
        out.append({"x": sum(g[0] for g in grp) / len(grp), "y": sum(g[1] for g in grp) / len(grp),
                    "text": " ".join(g[2] for g in grp)})
    return out


def _parse(cl: dict) -> dict:
    t = cl["text"]
    ref = _REF.search(t)
    d3, d2 = _DIMS3.search(t), _DIMS2.search(t)
    as_m = _AS.search(t)
    out = {"ref": f"{ref.group(1)}{int(ref.group(2)):02d}" if ref else None, "kind": (ref.group(1) if ref else None),
           "as_ngf": float(as_m.group(1).replace(",", ".")) if as_m else None, "raw": t[:90], "x": cl["x"], "y": cl["y"]}
    if d3:
        a, b, h = (int(d3.group(k)) for k in (1, 2, 3))
        out.update(a_cm=a, b_cm=b, ht_cm=h, kind=out["kind"] or "S")
    elif d2:
        w, h = int(d2.group(1)), int(d2.group(2))
        out.update(a_cm=w, b_cm=None, ht_cm=h, kind=out["kind"] or "SF")
    return out


def fondations_takeoff(dxf_bytes: bytes) -> dict:
    from shapely.geometry import LineString
    from shapely.ops import polygonize, unary_union
    doc = _read(dxf_bytes)
    msp = doc.modelspace()
    u = _UNITS.get(doc.header.get("$INSUNITS", 0), 0.01)
    layers = {e.dxf.layer for e in msp}
    label_layers = {l for l in layers if _LABEL_LAYER.search(l)}
    geom_layers = {l for l in layers if _GEOM_LAYER.search(l) and not _BACKGROUND.search(l)}
    out = {"unit_to_m": u, "label_layers": sorted(label_layers), "geometry_layers": sorted(geom_layers),
           "rows": [], "unmatched_polygons": 0, "findings": [], "totals": {}}
    if not geom_layers:
        out["findings"].append({"severity": "warning", "subject": "Sem camada de fundações",
                                "explanation": "Nenhuma camada «Fondations» / «AES-Semelle» nesta planta."})
        return out

    texts = []
    for e in msp:
        if e.dxf.layer in label_layers and e.dxftype() in ("TEXT", "MTEXT"):
            t = (e.plain_text() if e.dxftype() == "MTEXT" else e.dxf.text).strip()
            if t:
                texts.append((e.dxf.insert.x * u, e.dxf.insert.y * u, t))
    labels = [_parse(c) for c in _clusters(texts, radius=1.2)]

    segs = []
    for e in msp:
        if e.dxf.layer not in geom_layers:
            continue
        k = e.dxftype()
        if k == "LINE":
            segs.append(LineString([(e.dxf.start.x * u, e.dxf.start.y * u), (e.dxf.end.x * u, e.dxf.end.y * u)]))
        elif k == "LWPOLYLINE":
            pts = [(p[0] * u, p[1] * u) for p in e.get_points()]
            if len(pts) >= 2:
                segs.append(LineString(pts + ([pts[0]] if e.closed else [])))
        elif k == "INSERT" and not _BACKGROUND.search(e.dxf.name or ""):
            try:
                for v in e.virtual_entities():
                    if v.dxftype() == "LINE":
                        segs.append(LineString([(v.dxf.start.x * u, v.dxf.start.y * u), (v.dxf.end.x * u, v.dxf.end.y * u)]))
            except Exception:  # noqa: BLE001
                pass
    polys = [p for p in polygonize(unary_union(segs)) if 0.04 <= p.area <= 2000]

    conf, clar, indet = 0.0, 0.0, 0
    used_lbl = set()
    for p in sorted(polys, key=lambda q: -q.area):
        c = p.centroid
        cand = sorted(labels, key=lambda l: (l["x"] - c.x) ** 2 + (l["y"] - c.y) ** 2)
        lbl = next((l for l in cand if l.get("ht_cm") and math.dist((l["x"], l["y"]), (c.x, c.y)) < 6.0), None)
        row = {"area_m2": round(p.area, 2), "xy": (round(c.x, 1), round(c.y, 1))}
        if not lbl:
            out["unmatched_polygons"] += 1
            continue
        ht = lbl["ht_cm"] / 100
        row.update(ref=lbl["ref"], kind=lbl["kind"], ht_m=ht, as_ngf=lbl["as_ngf"],
                   fond_ngf=round(lbl["as_ngf"] - ht, 3) if lbl["as_ngf"] is not None else None, label=lbl["raw"])
        if lbl["kind"] == "S" and lbl.get("b_cm"):
            v_lbl = lbl["a_cm"] / 100 * lbl["b_cm"] / 100 * ht
            ok = abs(p.area - lbl["a_cm"] / 100 * lbl["b_cm"] / 100) <= 0.15 * max(p.area, 0.01)
            row.update(volume_m3=round(v_lbl, 3), formula=f"{lbl['a_cm']}×{lbl['b_cm']}×{lbl['ht_cm']} cm (rótulo)",
                       state="confirmed" if ok else "to_clarify")
            if not ok:
                row["note"] = f"área desenhada {p.area:.2f} m² ≠ rótulo {lbl['a_cm'] / 100 * lbl['b_cm'] / 100:.2f} m²"
        else:
            w = lbl["a_cm"] / 100
            row.update(volume_m3=round(p.area * ht, 3), length_m=round(p.area / w, 2) if w else None,
                       formula=f"área desenhada {p.area:.2f} m² × ht {lbl['ht_cm']} cm (secção {lbl['a_cm']}×{lbl['ht_cm']})",
                       state="confirmed")
        used_lbl.add(id(lbl))
        (conf, clar) = (conf + row["volume_m3"], clar) if row["state"] == "confirmed" else (conf, clar + row["volume_m3"])
        out["rows"].append(row)
    for l in labels:
        if id(l) not in used_lbl and l.get("ht_cm") and l.get("kind") == "S" and l.get("b_cm"):
            # sapata com rótulo completo mas contorno não fechado no desenho: o rótulo basta (dimensões explícitas)
            ht = l["ht_cm"] / 100
            v = l["a_cm"] / 100 * l["b_cm"] / 100 * ht
            out["rows"].append({"ref": l["ref"], "kind": "S", "ht_m": ht, "as_ngf": l["as_ngf"],
                                "fond_ngf": round(l["as_ngf"] - ht, 3) if l["as_ngf"] is not None else None,
                                "volume_m3": round(v, 3), "formula": f"{l['a_cm']}×{l['b_cm']}×{l['ht_cm']} cm (rótulo, contorno não fechado)",
                                "state": "to_clarify", "label": l["raw"]})
            clar += v
        elif id(l) not in used_lbl and l.get("ref") and not l.get("ht_cm"):
            indet += 1
            out["findings"].append({"severity": "to_clarify", "subject": f"Rótulo de fundação ilegível ({l['ref'] or '?'})",
                                    "explanation": f"Texto lido: «{l['raw']}» — dimensões/altura não reconhecidas; medir à mão ou corrigir o desenho."})
    as_vals = Counter(r["as_ngf"] for r in out["rows"] if r.get("as_ngf") is not None)
    out["totals"] = {"betao_confirmado_m3": round(conf, 2), "betao_a_esclarecer_m3": round(clar, 2),
                     "betao_total_m3": round(conf + clar, 2), "sapatas_isoladas": sum(1 for r in out["rows"] if r.get("kind") == "S"),
                     "trocos_continuos": sum(1 for r in out["rows"] if r.get("kind") != "S"),
                     "rotulos_ilegiveis": indet, "as_dominante_ngf": as_vals.most_common(1)[0][0] if as_vals else None}
    if out["unmatched_polygons"]:
        out["findings"].append({"severity": "info", "subject": "Contornos sem rótulo",
                                "explanation": f"{out['unmatched_polygons']} contornos fechados na camada de fundações sem rótulo a menos de 6 m: não medidos."})
    out["findings"].append({"severity": "info", "subject": "Escavação não calculada",
                            "explanation": "O fundo de cada sapata é As − ht (coluna fond_ngf); a escavação precisa da cota do terreno/arranque, que não está nesta planta."})
    return out


def compact(res: dict) -> dict:
    rows = sorted(res["rows"], key=lambda r: (r.get("kind") or "", r.get("ref") or ""))
    return {"totals": res["totals"], "rows": rows[:80], "findings": res["findings"],
            "label_layers": res["label_layers"], "geometry_layers": res["geometry_layers"],
            "note": "Volumes por rótulo impresso (S: A×B×ht; SF: área desenhada × ht). fond_ngf = As − ht. Nada estimado."}
