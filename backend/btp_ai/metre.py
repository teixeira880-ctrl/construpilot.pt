"""Traceable quantities (Phase B): identified elements built from the plan's calibrated rooms/openings, versioned metre rules,
formula + inputs + provenance per line, explicit assumptions and missing data. Deterministic code, no AI."""
import hashlib
import math
from datetime import datetime, timezone

from core.db import db

RULES_VERSION = "metre-rules v3 (2026-10)"
RULES = {
    "dalle_surface": {"lot": "Estrutura / betão", "designation": "Laje — área", "unit": "m²", "formula": "área do polígono calibrado menos as deduções da divisão", "waste_pct": 0},
    "mur_surface_nette": {"lot": "Estrutura / alvenaria", "designation": "Paredes — área líquida", "unit": "m²", "formula": "perímetro × altura − Σ áreas dos vãos", "waste_pct": 0},
    "mur_lineaire": {"lot": "Estrutura / alvenaria", "designation": "Paredes — linear", "unit": "ml", "formula": "Σ comprimentos dos lados do polígono calibrado", "waste_pct": 0},
    "mur_volume": {"lot": "Estrutura / betão", "designation": "Paredes — volume", "unit": "m³", "formula": "área líquida × espessura", "waste_pct": 0},
    "ouverture_unite": {"lot": "Menuiseries", "designation": "Carpintaria", "unit": "u", "formula": "1 unidade por vão, dimensões lidas (largura × altura)", "waste_pct": 0},
    "mur_dxf_lineaire": {"lot": "Estrutura / betão (DXF)", "designation": "Parede — linear", "unit": "ml", "formula": "comprimento do corpo da parede lido no DXF", "waste_pct": 0},
    "mur_dxf_volume": {"lot": "Estrutura / betão (DXF)", "designation": "Parede — volume de betão", "unit": "m³", "formula": "área em planta (C × e lida) × altura do piso", "waste_pct": 0},
    "poteau_volume": {"lot": "Estrutura / betão (DXF)", "designation": "Pilar — volume de betão", "unit": "m³", "formula": "secção lida (a × b) × altura do piso", "waste_pct": 0},
    "poutre_lineaire": {"lot": "Estrutura / betão (DXF)", "designation": "Viga — linear", "unit": "ml", "formula": "comprimento da viga lido no DXF (altura abaixo da laje não lida em planta)", "waste_pct": 0},
    "dalle_dxf_surface": {"lot": "Estrutura / betão (DXF)", "designation": "Laje — área líquida", "unit": "m²", "formula": "união das faces fechadas da camada laje − aberturas", "waste_pct": 0},
}
LEVEL_ELEMENT = "dxf_level"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id(*parts) -> str:
    return "el_" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:12]


def _shoelace(pts):
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))) / 2


def revision_of(plan: dict) -> str:
    return hashlib.sha1(f"{plan.get('updated_at')}|{len(plan.get('rooms') or [])}|{plan.get('calibrations')}".encode()).hexdigest()[:10]


def build_elements(plan: dict) -> tuple[list[dict], list[dict]]:
    """Elements + missing-information notices. Lengths come from calibrated pixels; heights/thickness only if provided (never defaulted silently)."""
    elements, missing = [], []
    cals = plan.get("calibrations") or {}
    for room in plan.get("rooms") or []:
        page = str(room.get("page_index", 0))
        cal = cals.get(page) or {}
        ppm = cal.get("pixels_per_meter")
        pts = room.get("points") or []
        base = {"plan_id": plan["plan_id"], "page_index": room.get("page_index", 0), "room_id": room["room_id"], "room_name": room.get("name") or room["room_id"]}
        if not ppm or len(pts) < 3:
            missing.append({"kind": "calibration" if not ppm else "geometry", "room_id": room["room_id"], "page_index": room.get("page_index", 0),
                            "message": f"{base['room_name']} : {('página não calibrada — comprimentos indetermináveis' if not ppm else 'polígono incompleto')}", "blocks": ["dalle_surface", "mur_surface_nette", "mur_lineaire", "mur_volume"]})
            continue
        area = _shoelace(pts) / (ppm ** 2)
        deductions = room.get("deductions") or []
        deducted_area = sum(_shoelace(d["points"]) / (ppm ** 2)
                            if len(d.get("points") or []) >= 3 else float(d.get("area_m2") or 0)
                            for d in deductions)
        area = max(0.0, area - deducted_area)
        sides = [math.dist(pts[i], pts[(i + 1) % len(pts)]) / ppm for i in range(len(pts))]
        prov_len = {"source": "mesuré", "detail": f"polígono calibrado ({cal.get('method')}, {ppm:.2f} px/m, confiança {cal.get('confidence')})"}
        height = room.get("ceiling_height_m")
        h_dim = {"value": height, "unit": "m", "source": "saisi" if height else "manquant", "detail": "pé-direito indicado na divisão" if height else "altura não indicada"}
        elements.append({**base, "element_id": _id(plan["plan_id"], room["room_id"], "dalle"), "type": "dalle", "label": f"Laje {base['room_name']}", "geometry": {"points_px": pts},
                         "dimensions": {"surface_m2": {"value": round(area, 3), "unit": "m²", **prov_len}}, "status": "to_verify", "evidence": {"page_index": base["page_index"], "points_px": pts}})
        openings = room.get("openings") or []
        elements.append({**base, "element_id": _id(plan["plan_id"], room["room_id"], "murs"), "type": "mur", "label": f"Paredes {base['room_name']}", "geometry": {"points_px": pts},
                         "dimensions": {"perimetre_m": {"value": round(sum(sides), 3), "unit": "m", **prov_len, "sides_m": [round(s, 3) for s in sides]}, "hauteur_m": h_dim,
                                        "epaisseur_m": {"value": room.get("wall_thickness_m"), "unit": "m", "source": "saisi" if room.get("wall_thickness_m") else "manquant", "detail": "espessura ilegível numa planta de divisões — a confirmar"}},
                         "openings": [o.get("kind") or o.get("type") for o in openings], "status": "to_verify", "evidence": {"page_index": base["page_index"], "points_px": pts}})
        if not height:
            missing.append({"kind": "height", "room_id": room["room_id"], "element_id": _id(plan["plan_id"], room["room_id"], "murs"), "message": f"{base['room_name']} : pé-direito em falta — áreas de paredes provisórias", "blocks": ["mur_surface_nette", "mur_volume"]})
        if not room.get("wall_thickness_m"):
            missing.append({"kind": "thickness", "room_id": room["room_id"], "element_id": _id(plan["plan_id"], room["room_id"], "murs"), "message": f"{base['room_name']} : espessura das paredes em falta — volume não determinado", "blocks": ["mur_volume"]})
        for i, o in enumerate(openings):
            w, h = o.get("width_m"), o.get("height_m")
            count = max(1, int(o.get("count", 1)))
            elements.append({**base, "element_id": _id(plan["plan_id"], room["room_id"], "ouv", i), "type": "ouverture", "count": count, "subtype": o.get("kind") or o.get("type") or "ouverture", "label": f"{(o.get('kind') or o.get('type') or 'ouverture').capitalize()} {i + 1} — {base['room_name']}",
                             "dimensions": {"largeur_m": {"value": w, "unit": "m", "source": "saisi" if w else "manquant", "detail": "dimensão introduzida no vão"}, "hauteur_m": {"value": h, "unit": "m", "source": "saisi" if h else "manquant", "detail": "dimensão introduzida no vão"}},
                             "status": "to_verify", "evidence": {"page_index": base["page_index"], "points_px": pts, "opening_index": i}})
    return elements, missing


def compute_quantities(elements: list[dict], overrides: dict) -> list[dict]:
    """One line per (element, rule). Assumptions come only from explicit overrides (visible, revisable)."""
    lines = []
    by_room = {}
    for e in elements:
        by_room.setdefault(e["room_id"], []).append(e)
    for e in elements:
        ov = overrides.get(e["element_id"]) or {}

        def line(rule_key, value, inputs, deductions=None, assumptions=None, status="to_verify", note=""):
            r = RULES[rule_key]
            net = round(value, 3) if value is not None else None
            waste = r["waste_pct"]
            lines.append({"quantity_id": "q_" + hashlib.sha1(f"{e['element_id']}|{rule_key}".encode()).hexdigest()[:12], "element_id": e["element_id"], "room_id": e["room_id"], "room_name": e["room_name"], "page_index": e["page_index"],
                          "rule": rule_key, "rule_version": RULES_VERSION, "lot": r["lot"], "designation": f"{r['designation']} — {e['room_name']}" if rule_key != "ouverture_unite" else e["label"], "unit": r["unit"], "formula": r["formula"],
                          "inputs": inputs, "deductions": deductions or [], "assumptions": assumptions or [], "quantity_net": net, "waste_pct": waste,
                          "quantity_to_order": round(net * (1 + waste / 100), 3) if net is not None else None, "status": "undetermined" if net is None else status, "note": note})
        d = e["dimensions"]
        if e["type"] == "dalle":
            line("dalle_surface", d["surface_m2"]["value"], [{"name": "surface", **d["surface_m2"]}])
        elif e["type"] == "mur":
            per = d["perimetre_m"]
            line("mur_lineaire", per["value"], [{"name": "perímetro", **{k: v for k, v in per.items() if k != "sides_m"}}])
            h = d["hauteur_m"]["value"]
            assumptions, h_src = [], d["hauteur_m"]
            if h is None and ov.get("hauteur_m"):
                h = ov["hauteur_m"]; h_src = {"value": h, "unit": "m", "source": "hypothèse", "detail": ov.get("reason") or "hipótese do utilizador"}; assumptions.append({"name": "altura", "value": h, "unit": "m", "reason": ov.get("reason") or "hipótese do utilizador", "by": ov.get("by")})
            openings = [o for o in by_room[e["room_id"]] if o["type"] == "ouverture"]
            ded = [{"name": o["label"], "value": round((o["dimensions"]["largeur_m"]["value"] or 0) * (o["dimensions"]["hauteur_m"]["value"] or 0) * o.get("count", 1), 3), "unit": "m²", "element_id": o["element_id"]} for o in openings]
            if h is None:
                line("mur_surface_nette", None, [{"name": "perímetro", **{k: v for k, v in per.items() if k != "sides_m"}}, {"name": "altura", **h_src}], ded, note="altura em falta: indique-a ou declare uma hipótese")
                line("mur_volume", None, [], note="altura e/ou espessura em falta")
                continue
            gross = per["value"] * h
            net = max(0.0, gross - sum(x["value"] for x in ded))
            line("mur_surface_nette", net, [{"name": "perímetro", **{k: v for k, v in per.items() if k != "sides_m"}}, {"name": "altura", **h_src}, {"name": "área bruta", "value": round(gross, 3), "unit": "m²", "source": "calculé"}], ded, assumptions, status="provisional" if assumptions else "to_verify")
            th = d["epaisseur_m"]["value"] or ov.get("epaisseur_m")
            if th:
                th_src = d["epaisseur_m"] if d["epaisseur_m"]["value"] else {"value": th, "unit": "m", "source": "hypothèse", "detail": ov.get("reason") or "hipótese do utilizador"}
                a2 = list(assumptions) + ([{"name": "espessura", "value": th, "unit": "m", "reason": ov.get("reason") or "hipótese do utilizador", "by": ov.get("by")}] if not d["epaisseur_m"]["value"] else [])
                line("mur_volume", net * th, [{"name": "área líquida", "value": round(net, 3), "unit": "m²", "source": "calculé"}, {"name": "espessura", **th_src}], [], a2, status="provisional" if a2 else "to_verify")
            else:
                line("mur_volume", None, [{"name": "área líquida", "value": round(net, 3), "unit": "m²", "source": "calculé"}, {"name": "espessura", **d["epaisseur_m"]}], note="espessura em falta: volume não determinado")
        elif e["type"] == "ouverture":
            w, h = d["largeur_m"]["value"], d["hauteur_m"]["value"]
            line("ouverture_unite", e.get("count", 1) if (w and h) else None, [{"name": "largura", **d["largeur_m"]}, {"name": "altura", **d["hauteur_m"]}], note="" if (w and h) else "dimensões incompletas")
    return lines


async def rebuild(plan: dict, user_id: str) -> dict:
    """Recompute for the current plan revision; previous lines are superseded, user validations kept when inputs are unchanged."""
    rev = revision_of(plan)
    elements, missing = build_elements(plan)
    overrides = {o["element_id"]: o async for o in db.btp_overrides.find({"plan_id": plan["plan_id"]}, {"_id": 0})}
    lines = compute_quantities(elements, overrides)
    if overrides:
        rev = hashlib.sha1((rev + "|" + "|".join(f"{k}:{v.get('hauteur_m')}:{v.get('epaisseur_m')}" for k, v in sorted(overrides.items()))).encode()).hexdigest()[:10]
    cad = await load_cad_takeoff(plan, user_id)
    if cad is not None:
        if cad.get("error"):
            missing.append({"kind": "dxf_error", "room_id": "dxf", "message": f"Leitura DXF impossível: {cad['error']}", "blocks": []})
        else:
            dxf_els, dxf_missing = build_dxf_elements(plan, cad)
            elements += dxf_els
            missing += dxf_missing
            lines += compute_dxf_quantities(dxf_els, overrides)
            rev = hashlib.sha1(f"{rev}|{(await db.btp_cad_cache.find_one({'plan_id': plan['plan_id']}, {'key': 1}) or {}).get('key')}".encode()).hexdigest()[:10]
    for m in missing:
        ov = overrides.get(m.get("element_id") or "")
        if ov and ov.get({"height": "hauteur_m", "thickness": "epaisseur_m"}.get(m["kind"], "")):
            m.update({"covered_by_assumption": True, "assumption": ov, "message": m["message"] + " — hipótese declarada: " + str(ov.get({"height": "hauteur_m", "thickness": "epaisseur_m"}[m["kind"]])) + " m (" + (ov.get("reason") or "") + ")"})
    prev = {q["quantity_id"]: q async for q in db.btp_quantities.find({"plan_id": plan["plan_id"], "superseded": {"$ne": True}}, {"_id": 0})}
    conflicts = []
    for q in lines:
        q.update({"plan_id": plan["plan_id"], "user_id": user_id, "revision": rev, "computed_at": _now()})
        p = prev.get(q["quantity_id"])
        if p and p.get("status") == "validated":
            if p.get("quantity_net") == q["quantity_net"] and p.get("inputs") == q["inputs"]:
                q.update({"status": "validated", "validated_by": p.get("validated_by"), "validated_at": p.get("validated_at")})
            else:
                conflicts.append({"quantity_id": q["quantity_id"], "designation": q["designation"], "previous": p.get("quantity_net"), "new": q["quantity_net"], "validated_by": p.get("validated_by")})
                q["conflict"] = {"previous": p.get("quantity_net"), "validated_by": p.get("validated_by")}
    if prev:
        await db.btp_quantities.update_many({"plan_id": plan["plan_id"], "superseded": {"$ne": True}}, {"$set": {"superseded": True, "superseded_at": _now()}})
    await db.btp_elements.delete_many({"plan_id": plan["plan_id"]})
    if elements:
        await db.btp_elements.insert_many([{**e, "user_id": user_id, "revision": rev} for e in elements])
    if lines:
        await db.btp_quantities.insert_many([dict(q) for q in lines])
    await db.btp_analyses.update_one({"plan_id": plan["plan_id"]}, {"$set": {"plan_id": plan["plan_id"], "user_id": user_id, "revision": rev, "built_at": _now(), "missing": missing, "conflicts": conflicts,
                                                                             "rules_version": RULES_VERSION, "elements": len(elements), "lines": len(lines), "has_dxf": cad is not None and not cad.get("error")}}, upsert=True)
    snap = [{k: q.get(k) for k in ("quantity_id", "designation", "lot", "unit", "quantity_net", "quantity_to_order", "status", "rule", "element_id")} for q in lines]
    await db.btp_revisions.update_one({"plan_id": plan["plan_id"], "revision": rev}, {"$set": {"plan_id": plan["plan_id"], "user_id": user_id, "revision": rev, "at": _now(), "plan_updated_at": plan.get("updated_at"), "lines": snap, "count": len(snap)},
                                                                                     "$setOnInsert": {"first_at": _now()}}, upsert=True)
    return {"revision": rev, "elements": len(elements), "lines": len(lines), "missing": missing, "conflicts": conflicts}


def build_dxf_elements(plan: dict, cad: dict) -> tuple[list[dict], list[dict]]:
    """Elements read by the existing coffrage_dxf engine (walls with thickness, columns, beams, slab). Level height is never inferred."""
    els, missing = [], []
    pid = plan["plan_id"]
    layers = cad.get("layers") or {}
    base = {"plan_id": pid, "page_index": 0, "room_id": "dxf", "room_name": "DXF", "source": "dxf"}
    els.append({**base, "element_id": _id(pid, LEVEL_ELEMENT), "type": "niveau", "label": "Piso — altura sob a laje", "dimensions": {"hauteur_m": {"value": None, "unit": "m", "source": "manquant", "detail": "altura do piso ilegível numa planta de cofragem: a declarar (hipótese visível)"}},
                "status": "to_verify", "evidence": {"detail": "planta de cofragem: altura a ler no corte ou a declarar"}})
    missing.append({"kind": "height", "element_id": _id(pid, LEVEL_ELEMENT), "room_id": "dxf", "message": "Piso: altura sob a laje em falta — volumes das paredes e pilares DXF não determinados", "blocks": ["mur_dxf_volume", "poteau_volume"]})
    prov = lambda role: f"lido no DXF (camada {', '.join(layers.get(role) or ['?'])})"
    for w in ((cad.get("elements") or {}).get("walls") or {}).get("rows") or []:
        els.append({**base, "element_id": _id(pid, "dxfwall", w["ref"]), "type": "mur", "ref": w["ref"], "label": f"Parede {w['ref']}",
                    "dimensions": {"longueur_m": {"value": w["length_m"], "unit": "m", "source": "mesuré", "detail": prov("wall")}, "epaisseur_m": {"value": w["thickness_m"], "unit": "m", "source": "mesuré", "detail": prov("wall")},
                                   "aire_plan_m2": {"value": w["plan_area_m2"], "unit": "m²", "source": "calculé", "detail": w.get("formula")}},
                    "status": "to_verify", "evidence": {"detail": prov("wall"), "centroid_m": w.get("centroid_m"), "formula": w.get("formula")}})
    for c in ((cad.get("elements") or {}).get("columns") or {}).get("rows") or []:
        els.append({**base, "element_id": _id(pid, "dxfcol", c["ref"]), "type": "poteau", "ref": c["ref"], "label": f"Pilar {c['ref']}",
                    "dimensions": {"section_m2": {"value": c["section_m2"], "unit": "m²", "source": "mesuré", "detail": c.get("source")}, "a_cm": {"value": c["w_cm"], "unit": "cm", "source": "mesuré"}, "b_cm": {"value": c["h_cm"], "unit": "cm", "source": "mesuré"}},
                    "status": "to_verify", "evidence": {"detail": prov("column"), "centroid_m": c.get("centroid_m"), "formula": c.get("formula")}})
    for b in ((cad.get("elements") or {}).get("beams") or {}).get("rows") or []:
        els.append({**base, "element_id": _id(pid, "dxfbeam", b["ref"]), "type": "poutre", "ref": b["ref"], "label": f"Viga {b['ref']}",
                    "dimensions": {"longueur_m": {"value": b["length_m"], "unit": "m", "source": "mesuré", "detail": prov("beam")}, "largeur_m": {"value": b["width_m"], "unit": "m", "source": "mesuré", "detail": prov("beam")},
                                   "retombee_m": {"value": None, "unit": "m", "source": "manquant", "detail": "altura abaixo da laje ilegível em planta"}},
                    "status": "to_verify", "evidence": {"detail": prov("beam"), "centroid_m": b.get("centroid_m"), "formula": b.get("formula")}})
    slab = (cad.get("elements") or {}).get("slab")
    if slab:
        els.append({**base, "element_id": _id(pid, "dxfslab"), "type": "dalle", "label": "Laje (DXF)", "dimensions": {"surface_m2": {"value": slab["net_area_m2"], "unit": "m²", "source": "mesuré", "detail": prov("slab") + f" ; brute {slab['gross_area_m2']} m², {slab['openings_count']} abertura(s) = {slab['openings_area_m2']} m²"}},
                    "status": "to_verify", "evidence": {"detail": slab.get("formula")}})
    excl = (((cad.get("elements") or {}).get("walls") or {}).get("thin_layers_excluded") or {})
    if excl.get("count"):
        missing.append({"kind": "thin_layers", "room_id": "dxf", "message": f"{excl['count']} corps < 8 cm ({excl['length_m']} ml) excluídos das paredes de betão — {excl.get('note')}", "blocks": []})
    return els, missing


def compute_dxf_quantities(elements: list[dict], overrides: dict) -> list[dict]:
    lines = []
    level = next((e for e in elements if e["type"] == "niveau"), None)
    ov = overrides.get(level["element_id"]) if level else None
    h = ov.get("hauteur_m") if ov else None
    h_input = {"name": "altura do piso", "value": h, "unit": "m", "source": "hypothèse" if h else "manquant", "detail": (ov or {}).get("reason") or "a declarar"}
    assum = [{"name": "altura do piso", "value": h, "unit": "m", "reason": ov.get("reason") or "hipótese do utilizador", "by": ov.get("by")}] if h else []

    def line(e, rule_key, value, inputs, assumptions=None, note=""):
        r = RULES[rule_key]
        net = round(value, 3) if value is not None else None
        lines.append({"quantity_id": "q_" + hashlib.sha1(f"{e['element_id']}|{rule_key}".encode()).hexdigest()[:12], "element_id": e["element_id"], "room_id": "dxf", "room_name": "DXF", "page_index": 0, "source": "dxf",
                      "rule": rule_key, "rule_version": RULES_VERSION, "lot": r["lot"], "designation": f"{r['designation']} — {e.get('ref') or e['label']}", "unit": r["unit"], "formula": r["formula"], "inputs": inputs, "deductions": [],
                      "assumptions": assumptions or [], "quantity_net": net, "waste_pct": r["waste_pct"], "quantity_to_order": round(net * (1 + r["waste_pct"] / 100), 3) if net is not None else None,
                      "status": "undetermined" if net is None else ("provisional" if assumptions else "to_verify"), "note": note})
    for e in elements:
        d = e["dimensions"]
        if e["type"] == "mur" and e.get("source") == "dxf":
            line(e, "mur_dxf_lineaire", d["longueur_m"]["value"], [{"name": "comprimento", **d["longueur_m"]}, {"name": "espessura", **d["epaisseur_m"]}])
            line(e, "mur_dxf_volume", d["aire_plan_m2"]["value"] * h if h else None, [{"name": "área em planta", **d["aire_plan_m2"]}, h_input], assum, "" if h else "altura do piso a declarar")
        elif e["type"] == "poteau":
            line(e, "poteau_volume", d["section_m2"]["value"] * h if h else None, [{"name": "section", **d["section_m2"]}, h_input], assum, "" if h else "altura do piso a declarar")
        elif e["type"] == "poutre":
            line(e, "poutre_lineaire", d["longueur_m"]["value"], [{"name": "comprimento", **d["longueur_m"]}, {"name": "largura", **d["largeur_m"]}, {"name": "altura abaixo da laje", **d["retombee_m"]}], note="volume não determinado: altura abaixo da laje não lida em planta")
        elif e["type"] == "dalle" and e.get("source") == "dxf":
            line(e, "dalle_dxf_surface", d["surface_m2"]["value"], [{"name": "área líquida", **d["surface_m2"]}])
    return lines


async def load_cad_takeoff(plan: dict, user_id: str) -> dict | None:
    """DXF takeoff via the existing engine, cached per source in btp_cad_cache."""
    import asyncio
    from engines.plan_sources import load_cad_source
    from engines.metre.coffrage_dxf import coffrage_takeoff
    data = None
    for kind in ("converted_dxf", "original"):
        try:
            data = await load_cad_source(db, plan["plan_id"], user_id, kind)
        except Exception:
            data = None
        if data and (kind == "converted_dxf" or (plan.get("filename") or "").lower().endswith(".dxf")):
            break
        data = None
    if not data:
        return None
    key = hashlib.sha1(data).hexdigest()
    cached = await db.btp_cad_cache.find_one({"plan_id": plan["plan_id"], "key": key}, {"_id": 0})
    if cached:
        return cached["cad"]
    try:
        cad = await asyncio.get_event_loop().run_in_executor(None, lambda: coffrage_takeoff(data))
    except Exception as e:
        return {"error": f"{type(e).__name__}: {str(e)[:120]}", "elements": {}, "layers": {}}
    cad.pop("geometry", None)
    await db.btp_cad_cache.update_one({"plan_id": plan["plan_id"]}, {"$set": {"plan_id": plan["plan_id"], "key": key, "cad": cad, "at": _now()}}, upsert=True)
    return cad

