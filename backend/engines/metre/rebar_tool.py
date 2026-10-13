"""Assistant tool « read_rebar_schedule » : native reading first, optional visual reading, one persisted record for chat card + PDF report."""
import base64
import uuid

from engines.metre.rebar_schedule import extract_from_pdf_bytes
from engines.metre.rebar_vision import analyze_pdf, is_vision_needed
from engines.plan_sources import load_plan_source


def _report_payload(native: dict | None, sheet: dict | None) -> dict:
    """Shape the reading as calculation / comparison / findings / lines so the unified PDF report renders it unchanged."""
    out = {"calculation": None, "comparison": None, "findings": [], "lines": []}
    if native:
        ha, mesh, recap = native.get("ha_bars"), native.get("mesh"), native.get("mesh_recap")
        if ha:
            out["calculation"] = {"kind": "rebar_mass_ha", "formula": f"Σ({ha['count']} repères HA) longueur totale × kg/m (EN 10080)",
                                  "result": ha["total_mass_kg"], "unit": "kg", "state": "to_clarify" if ha["inconsistencies"] else "confirmed", "inputs": []}
            for dia, v in ha["by_diameter"].items():
                out["lines"].append({"element": f"Aciers {dia}", "location": "nomenclature", "formula": f"{v['length_m']:g} m × {v['mass_kg'] / v['length_m'] if v['length_m'] else 0:.3f} kg/m",
                                     "net": v["mass_kg"], "unit": "kg", "state": "confirmed"})
            if ha.get("comparison"):
                c = ha["comparison"]
                out["comparison"] = {"kind": "rebar_vs_recap", "formula": f"{c['a']} {c['a_kg']:g} kg − {c['b']} {c['b_kg']:g} kg", "result": c["difference_kg"], "unit": "kg",
                                     "state": "confirmed" if abs(c["difference_kg"]) <= max(1.0, 0.01 * c["b_kg"]) else "to_clarify", "inputs": []}
        if mesh:
            out["lines"].append({"element": "Treillis soudés (nomenclature)", "location": f"{mesh['count']} panneaux", "formula": "Σ masses imprimées",
                                 "net": mesh["rows_mass_kg"], "unit": "kg", "state": "confirmed"})
            for cmp in mesh.get("comparisons", []):
                if not cmp.get("expect_equal"):
                    out["findings"].append({"severity": "info", "subject": f"{cmp['a']} − {cmp['b']}",
                                            "explanation": f"{cmp['a_kg']:g} kg − {cmp['b_kg']:g} kg = {cmp['difference_kg']:+g} kg : {cmp.get('meaning', '')}"})
                    continue
                state = "confirmed" if abs(cmp["difference_kg"]) <= max(3.0, 0.005 * (cmp["b_kg"] or 1)) else "to_clarify"
                out["findings"].append({"severity": "info" if state == "confirmed" else "to_clarify", "subject": f"{cmp['a']} vs {cmp['b']}",
                                        "explanation": f"{cmp['a_kg']:g} kg vs {cmp['b_kg']:g} kg (écart {cmp['difference_kg']:+g} kg)."})
        if recap and recap.get("mass_laid_kg") is not None:
            out["lines"].append({"element": "Treillis — masse posée (cartouche)", "location": None, "formula": "valeur imprimée", "net": recap["mass_laid_kg"], "unit": "kg", "state": "confirmed"})
        out["findings"].extend(native.get("findings", []))
    if sheet:
        el, chk = sheet.get("element") or {}, sheet.get("checks") or {}
        if el.get("steel_kg") is not None:
            out["calculation"] = {"kind": "rebar_sheet_mass", "formula": f"Feuille {el.get('label') or '?'} : Σ Lg × kg/m = {chk.get('calc_mass_kg')} kg",
                                  "result": el["steel_kg"], "unit": "kg", "state": "to_clarify" if chk.get("inconsistencies") else "confirmed", "inputs": []}
        for c in chk.get("inconsistencies", []):
            out["findings"].append({"severity": "to_clarify", "subject": f"{el.get('label') or 'Feuille'} · HA{c.get('diameter_mm', '')}".rstrip(" ·HA"),
                                    "explanation": f"{c['check']} : {c.get('formula')} vs {c.get('declared')} imprimé.", "action": "Vérifier la ligne sur la feuille (recadrage)."})
        for u in sheet.get("unreadable") or []:
            out["findings"].append({"severity": "to_clarify", "subject": "Valeur illisible", "explanation": u})
    return out


def _drawn_dimensions(pdf: bytes, page: int, native: dict) -> dict | None:
    """Oblique/dashed dimension labels of the drawing itself, matched to their lines at the real print scale (tables excluded)."""
    import pymupdf
    from engines.metre.oblique_dims import match_labels
    from engines.plan_identity import identify_document
    from engines.plan_vector_pdf import pt_per_m_from_scale
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pg = doc[page]
        scale = identify_document(pg.get_text(), pg.get_text("words")).get("declared_scale") or ""
        denom = int(scale.split("/")[1]) if "/" in scale else None
        if not denom:
            return {"error": "Échelle non lue dans le cartouche : cotes dessinées non vérifiables."}
        tables = [r["bbox_pt"] for tbl in ("ha_bars", "mesh") for r in ((native.get(tbl) or {}).get("rows") or [])]
        res = match_labels(pg, pt_per_m_from_scale(denom), exclude_rects=[(b[0] - 6, b[1] - 4, b[2] + 6, b[3] + 4) for b in tables])
    counts = {}
    for u in res["unmatched"]:
        counts[u["raw_text"]] = counts.get(u["raw_text"], 0) + 1
    return {"confirmed": len(res["dimensions"]), "labels": res["labels"], "calibration": res["calibration"],
            "unmatched_by_text": dict(sorted(counts.items(), key=lambda kv: -kv[1])[:8]), "sample": res["dimensions"][:12], "note": res["note"]}


async def run_read_rebar_schedule(db, *, user_id: str, conversation_id: str, plan_id: str, page: int, allow_vision: bool, now: str) -> dict:
    src = await load_plan_source(db, plan_id, user_id)
    if not src:
        return {"error": "Source du plan indisponible : réimportez le document."}
    if src.get("source_kind") == "cad_render":
        return {"error": "Document CAO (DWG/DXF) : pas de nomenclature imprimée à lire ; utilisez read_native_dimensions pour les cotes natives et le métré structurel."}
    pdf = base64.b64decode(src["data_b64"])
    if not pdf.startswith(b"%PDF"):
        return {"error": "La lecture des nomenclatures s'applique aux PDF."}
    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page_count = len(doc)
    note = None
    if page == page_count and page > 0:
        page, note = page - 1, "Numéro de page interprété comme 1-based (première page = index 0)."
    if not 0 <= page < page_count:
        return {"error": f"Page {page} absente : le document compte {page_count} page(s) (index 0 = première page)."}
    mode, native, sheet, vision = "native_text", None, None, None
    if is_vision_needed(pdf, page):
        if not allow_vision:
            return {"error": "Cette page n'a pas de texte natif (texte vectorisé). Relancez avec allow_vision=true pour une lecture visuelle IA (appel facturé).",
                    "requires_vision": True, "plan_id": plan_id, "page": page}
        from engines.openai_studies import _log_usage
        vision = await analyze_pdf(pdf, user_id=user_id, plan_id=plan_id, pages=[page], log_usage=_log_usage)
        sheet, mode = vision["sheets"][0], "vision_reading"
    else:
        native = extract_from_pdf_bytes(pdf, page)
        native["drawn_dimensions"] = _drawn_dimensions(pdf, page, native)
    result = {"plan_id": plan_id, "page": page, "mode": mode, "native": native, "sheet": sheet, "page_note": note, **_report_payload(native, sheet)}
    rec = {"calc_ref": f"mc_{uuid.uuid4().hex[:10]}", "user_id": user_id, "conversation_id": conversation_id, "tool": "read_rebar_schedule",
           "args": {"plan_id": plan_id, "page": page, "allow_vision": allow_vision}, "result": result, "created_at": now}
    await db.assistant_calculations.insert_one(rec)
    return {"calc_ref": rec["calc_ref"], **result}
