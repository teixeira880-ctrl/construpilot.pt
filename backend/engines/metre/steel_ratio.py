"""Steel/concrete ratios: Arche beam sheets (b, h, span, béton, acier) paired with DXF beam bodies by section width and length.

Pairing is purely dimensional (the Revit export carries no beam labels): |b − width| ≤ 5 cm and |span − length| ≤ 10 cm, one DXF body per
sheet, nearest first. Ratios come from the printed sheets; the DXF only adds an independent volume L × b × h for comparison.
"""


def _sheets(vision: dict) -> list[dict]:
    return [s for s in vision.get("sheets", []) if s.get("page_kind") == "element_sheet" and s.get("element")]


def pair_beams(vision: dict, dxf_beams: list[dict], *, tol_w_m: float = 0.05, tol_l_m: float = 0.10) -> dict:
    used, rows = set(), []
    for s in sorted(_sheets(vision), key=lambda s: -(s["element"].get("span_cm") or 0)):
        el = s["element"]
        b, h, span = el.get("width_cm"), el.get("height_cm"), el.get("span_cm")
        row = {"label": el.get("label"), "page": s["page"] + 1, "b_cm": b, "h_cm": h, "span_cm": span, "concrete_m3": el.get("concrete_m3"), "steel_kg": el.get("steel_kg"),
               "ratio_kg_m3_printed": el.get("ratio_kg_m3"), "dxf": None, "state": "unpaired"}
        if el.get("steel_kg") and el.get("concrete_m3"):
            row["ratio_kg_m3_calc"] = round(el["steel_kg"] / el["concrete_m3"], 1)
        if b and h and el.get("concrete_m3"):
            row["arche_length_m"] = round(el["concrete_m3"] / (b / 100 * h / 100), 2)
        if b and span:
            cands = [(abs(d["length_m"] - span / 100) + abs(d["width_m"] - b / 100), i, d) for i, d in enumerate(dxf_beams)
                     if i not in used and abs(d["width_m"] - b / 100) <= tol_w_m and abs(d["length_m"] - span / 100) <= tol_l_m]
            if cands:
                _, i, d = min(cands, key=lambda c: c[0])
                used.add(i)
                vol = d["length_m"] * (b / 100) * (h / 100) if h else None
                row["dxf"] = {"ref": d.get("ref"), "length_m": d["length_m"], "width_m": d["width_m"], "centroid_m": d.get("centroid_m"),
                              "volume_m3_with_arche_h": round(vol, 3) if vol else None,
                              "formula": f"{d['length_m']:.2f} m × {b / 100:.2f} × {h / 100:.2f} = {vol:.3f} m³" if vol else None}
                if vol and el.get("concrete_m3"):
                    row["dxf"]["difference_m3"] = round(vol - el["concrete_m3"], 3)
                    row["dxf"]["note"] = "Betão Arche = b × h × comprimento total (apoios incluídos); volume DXF = comprimento entre faces de apoio: diferença esperada = apoios."
                row["state"] = "paired"
                if vol and el.get("steel_kg"):
                    row["ratio_kg_m3_dxf_volume"] = round(el["steel_kg"] / vol, 1)
        rows.append(row)
    same_section = {}
    for d in dxf_beams:
        same_section.setdefault((round(d["width_m"], 2), round(d["length_m"], 1)), 0)
        same_section[(round(d["width_m"], 2), round(d["length_m"], 1))] += 1
    unpaired_dxf = [d for i, d in enumerate(dxf_beams) if i not in used]
    paired = [r for r in rows if r["state"] == "paired"]
    steel = sum(r["steel_kg"] or 0 for r in rows if r["concrete_m3"])
    concrete = sum(r["concrete_m3"] or 0 for r in rows if r["concrete_m3"])
    return {"rows": rows, "paired": len(paired), "unpaired_sheets": [r["label"] for r in rows if r["state"] != "paired"],
            "unpaired_dxf_beams": len(unpaired_dxf), "dxf_beams": len(dxf_beams),
            "aggregate": {"steel_kg": round(steel, 1), "concrete_m3": round(concrete, 2), "ratio_kg_m3": round(steel / concrete, 1) if concrete else None,
                          "formula": f'Σ aço {steel:.1f} kg / Σ betão {concrete:.2f} m³ (folhas Arche do piso)'},
            "note": ("Emparelhamento por largura de secção e comprimento (±5 cm / ±10 cm), sem nome: vários corpos DXF da mesma secção (ex.: 3 × 70 cm / 6,80 m) não podem ser distinguidos; as folhas BN/PV (massa teórica, sem betão impresso) ficam fora da razão.")}


def ratio_lines(pairing: dict, schedule_steel_kg: float | None) -> list[dict]:
    lines = []
    for r in pairing["rows"]:
        if r.get("ratio_kg_m3_calc") is not None:
            printed = r.get("ratio_kg_m3_printed")
            rounding = r["ratio_kg_m3_calc"] * (0.005 / r["concrete_m3"] + 0.05 / r["steel_kg"])  # béton imprimé au cl, acier au 0,1 kg
            state = "confirmed" if printed is None or abs(r["ratio_kg_m3_calc"] - printed) <= max(0.6, rounding) else "to_clarify"
            lines.append({"element": f"Viga {r['label']} — razão aço/betão", "location": f"p.{r['page']}" + (f" ↔ DXF {r['dxf']['ref']}" if r["dxf"] else " (sem par DXF)"),
                          "formula": f"{r['steel_kg']:g} kg / {r['concrete_m3']:g} m³", "net": r["ratio_kg_m3_calc"], "unit": "kg/m³", "state": state})
    agg = pairing["aggregate"]
    if agg["ratio_kg_m3"]:
        lines.append({"element": "Vigas do piso — razão agregada", "location": None, "formula": agg["formula"], "net": agg["ratio_kg_m3"], "unit": "kg/m³", "state": "confirmed"})
    if schedule_steel_kg:
        lines.append({"element": "BN / PV / esperas — aço (massa teórica)", "location": "folhas com lista", "formula": "Σ comp. total × kg/m", "net": schedule_steel_kg, "unit": "kg",
                      "state": "indeterminate", "missing": ["betão das BN/PV (não impresso)"]})
    return lines
