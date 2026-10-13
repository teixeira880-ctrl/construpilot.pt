"""Visual reading of reinforcement sheets whose text is vectorised (no native text): one strict JSON per page, then the
same deterministic checks as the native reader (count × length × kg/m vs printed Lg/Poids and « Acier = … kg »)."""
import asyncio
import base64
import io
import json
import logging
import os
from collections import defaultdict

from engines.rebar import STEEL_KG_PER_M

logger = logging.getLogger("rebar_vision")

NUM = {"type": ["number", "null"]}
STR = {"type": ["string", "null"]}
INT = {"type": ["integer", "null"]}


def _obj(props):
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


SHEET_SCHEMA = _obj({
    "page_kind": {"type": "string", "enum": ["cover", "element_sheet", "schedule_sheet", "other"]},
    "elements": {"type": "array", "items": _obj({"label": STR, "units": INT})},
    "schedule_rows": {"type": "array", "items": _obj({"mark": INT, "diameter_mm": INT, "per_element": INT, "elements": INT, "total_count": INT,
                                                      "spacing_cm": NUM, "unit_length_cm": NUM, "mandrel_cm": NUM, "total_length_cm": NUM})},
    "schedule_partial": {"type": "boolean"},
    "element": {"anyOf": [_obj({"label": STR, "level": STR, "concrete_m3": NUM, "steel_kg": NUM, "ratio_kg_m3": NUM,
                                "width_cm": NUM, "height_cm": NUM, "span_cm": NUM, "fire_resistance": STR, "concrete_class": STR}), {"type": "null"}]},
    "bars": {"type": "array", "items": _obj({"mark": INT, "count": INT, "diameter_mm": INT, "length_cm": NUM, "shape": STR})},
    "by_diameter": {"type": "array", "items": _obj({"diameter_mm": INT, "length_m": NUM, "mass_kg": NUM})},
    "recap": {"anyOf": [_obj({"ha_shaped_kg": NUM, "ha_straight_kg": NUM,
                              "mesh": {"type": "array", "items": _obj({"panel": STR, "count": INT, "width_cm": NUM, "height_cm": NUM, "mass_kg": NUM})},
                              "mesh_total_kg": NUM, "mesh_laid_kg": NUM}), {"type": "null"}]},
    "title_block": {"anyOf": [_obj({"document_code": STR, "revision_index": STR, "revision_date": STR, "project": STR, "project_ref": STR,
                                    "level": STR, "author": STR, "title": STR}), {"type": "null"}]},
    "notes": {"type": "array", "items": {"type": "string"}},
    "unreadable": {"type": "array", "items": {"type": "string"}},
})

INSTRUCTIONS = "Lês uma folha de armaduras de betão armado (gabinete de projeto) apresentada em imagem. Transcreve APENAS o que está impresso, sem nada\ncalcular nem completar: se um valor não for legível, põe null e descreve-o em «unreadable».\n- page_kind : «cover» pour la page d\'indications/récap générale (RECAP DES ACIERS, RECAPITULATIF TREILLIS) ; «element_sheet» pour une feuille d\'élément\n  unique (poutre, linteau…) avec cartouche «Béton=… m3 / Acier=… kg / d=… kg/m3» et tableau Barre / Lg / Forme ; «schedule_sheet» pour une feuille\n  à plusieurs éléments (BN, PV, attentes…) avec un tableau «Nomenclature des aciers» (N°, Type, ∅, Nombre par élément / d\'éléments / TOTAL, Esp,\n  Long. unitaire, Façonnage, Mandrin, Long. TOTALE) ; sinon «other».\n- elements : tous les repères d\'éléments dessinés sur la page (ex. BN3.2 «1 unités» → label=BN3.2, units=1 ; PV3.45 ; Attente PV3.7 (x1u.) → units=1).\n- schedule_rows : chaque ligne du tableau Nomenclature des aciers, valeurs en cm telles qu\'imprimées (mark = N°, ∅ en mm) ; schedule_partial=true si «(partielle)».\n- element : uniquement pour element_sheet : label (ex. T3.11), niveau (ex. PH RDC), Béton m3, Acier kg, d kg/m3, section b×h en cm (coupe), portée en cm si cotée, tenue au feu, classe béton.\n- bars : chaque ligne du tableau Barre/Lg/Forme : numéro de repère, «4HA12» → count=4, diameter_mm=12 ; Lg en cm ; forme = cotes du croquis telles qu\'écrites.\n- by_diameter : lignes «Barre | Lg/Poids» : «HA8 67.8/26.8» → diameter_mm=8, length_m=67.8, mass_kg=26.8.\n- title_block : cartouche s\'il est imprimé (code plan ex. GO-B3-R0-301, indice, date jj/mm/aaaa, nom d\'affaire, n° d\'affaire, niveau, auteur/BET, titre) ; sinon null.\n- recap : uniquement sur la page cover : Poids HA façonnés / non façonnés, tableau treillis (panneau, nombre, dimensions, masse), masse totale, masse posée.\nNenhum valor inventado; nenhuma tolerância aplicada; nunca corrijas um valor impresso."


def render_page_png_b64(pdf_bytes: bytes, page_index: int, *, dpi: int = 170, rotate_deg: int = 0) -> str:
    import pymupdf
    from PIL import Image
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        pix = doc[page_index].get_pixmap(dpi=dpi, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    if rotate_deg:
        img = img.rotate(rotate_deg, expand=True)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def detect_rotation(pdf_bytes: bytes, page_index: int = 0) -> int:
    """Landscape drawing printed on a portrait page → rotate 90° so the title block reads upright (heuristic on page size only)."""
    import pymupdf
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        r = doc[page_index].rect
    return 90 if r.height > r.width else 0


def check_sheet(sheet: dict) -> dict:
    """Deterministic reconciliation of the printed values; states, never corrections."""
    checks, by_dia = [], defaultdict(lambda: {"count": 0, "length_m": 0.0, "mass_kg": 0.0})
    if sheet.get("schedule_rows"):
        from engines.metre.rebar_schedule import check_ha_rows
        rows = [{**r, "type": "HA", "origin": "vision_reading"} for r in sheet["schedule_rows"]]
        sched = check_ha_rows(rows)
        return {"schedule": {"rows": len(rows), **sched}, "calc_mass_kg": sched["total_mass_kg"], "printed_mass_kg": None,
                "checks": sched["checks"], "inconsistencies": sched["inconsistencies"], "indeterminate": []}
    for b in sheet.get("bars") or []:
        if b.get("count") is None or b.get("diameter_mm") is None or b.get("length_cm") is None:
            checks.append({"mark": b.get("mark"), "check": "varão incompleto", "state": "indeterminate", "formula": None, "declared": None})
            continue
        kg_m = STEEL_KG_PER_M.get(f"HA{b['diameter_mm']}")
        length_m = b["count"] * b["length_cm"] / 100
        d = by_dia[b["diameter_mm"]]
        d["count"] += b["count"]
        d["length_m"] += length_m
        if kg_m:
            d["mass_kg"] += length_m * kg_m
    for row in sheet.get("by_diameter") or []:
        dia = row.get("diameter_mm")
        calc = by_dia.get(dia)
        if not calc or dia is None:
            checks.append({"diameter_mm": dia, "check": "Comp./Peso sem varão correspondente na tabela", "state": "to_clarify", "formula": None, "declared": row})
            continue
        if row.get("length_m") is not None:
            ok = abs(calc["length_m"] - row["length_m"]) <= max(0.15, 0.01 * row["length_m"])
            checks.append({"diameter_mm": dia, "check": "Σ count × Comp. = Comp. total", "formula": f"Σ = {calc['length_m']:.2f} m", "declared": row["length_m"],
                           "difference_m": round(calc["length_m"] - row["length_m"], 2), "state": "confirmed" if ok else "to_clarify"})
        if row.get("mass_kg") is not None:
            ok = abs(calc["mass_kg"] - row["mass_kg"]) <= max(0.3, 0.02 * row["mass_kg"])
            checks.append({"diameter_mm": dia, "check": "Σ Comp. × kg/m = Peso", "formula": f"Σ = {calc['mass_kg']:.1f} kg", "declared": row["mass_kg"],
                           "difference_kg": round(calc["mass_kg"] - row["mass_kg"], 1), "state": "confirmed" if ok else "to_clarify"})
    total_calc = round(sum(d["mass_kg"] for d in by_dia.values()), 1)
    printed = sum(r["mass_kg"] for r in (sheet.get("by_diameter") or []) if r.get("mass_kg") is not None)
    el = sheet.get("element") or {}
    if el.get("steel_kg") is not None and printed:
        checks.append({"check": "Σ Peso por diâmetro = Aço (legenda)", "formula": f"Σ = {printed:.1f} kg", "declared": el["steel_kg"],
                       "difference_kg": round(printed - el["steel_kg"], 1), "state": "confirmed" if abs(printed - el["steel_kg"]) <= max(0.5, 0.02 * el["steel_kg"]) else "to_clarify"})
    if el.get("steel_kg") and el.get("concrete_m3") and el.get("ratio_kg_m3"):
        ratio = el["steel_kg"] / el["concrete_m3"]
        checks.append({"check": "Aço / Betão = d", "formula": f"{el['steel_kg']:g} / {el['concrete_m3']:g} = {ratio:.1f} kg/m3", "declared": el["ratio_kg_m3"],
                       "state": "confirmed" if abs(ratio - el["ratio_kg_m3"]) <= max(0.6, 0.01 * el["ratio_kg_m3"]) else "to_clarify"})
    return {"by_diameter_calc": {f"HA{k}": {kk: round(vv, 2) for kk, vv in v.items()} for k, v in sorted(by_dia.items())},
            "calc_mass_kg": total_calc, "printed_mass_kg": round(printed, 1) if printed else None, "checks": checks,
            "inconsistencies": [c for c in checks if c["state"] == "to_clarify"], "indeterminate": [c for c in checks if c["state"] == "indeterminate"]}


def summarize(sheets: list[dict]) -> dict:
    """Project-level reconciliation: Σ Acier of every element sheet vs the cover recap (when printed)."""
    elements = [s for s in sheets if s.get("page_kind") == "element_sheet" and s.get("element")]
    schedules = [s for s in sheets if s.get("page_kind") == "schedule_sheet" and s.get("schedule_rows")]
    cover = next((s for s in sheets if s.get("page_kind") == "cover" and s.get("recap")), None)
    total_steel = round(sum(e["element"]["steel_kg"] or 0 for e in elements), 1)
    schedule_steel = round(sum((s.get("checks") or {}).get("calc_mass_kg") or 0 for s in schedules), 1)
    total_concrete = round(sum(e["element"]["concrete_m3"] or 0 for e in elements), 2)
    labels = [e["element"].get("label") for e in elements]
    other_labels = [el.get("label") for s in schedules for el in (s.get("elements") or []) if el.get("label")]
    dupes = sorted({x for x in labels + other_labels if x and (labels + other_labels).count(x) > 1})
    title_blocks = [s["title_block"] for s in sheets if s.get("title_block")]
    out = {"title_block": next((tb for tb in title_blocks if tb.get("document_code") or tb.get("revision_date")), title_blocks[0] if title_blocks else None),
           "elements": len(elements), "labels": labels, "schedule_sheets": len(schedules), "schedule_elements": other_labels,
           "schedule_rows": sum(len(s["schedule_rows"]) for s in schedules), "schedule_steel_kg": schedule_steel,
           "duplicate_labels": dupes, "total_steel_kg": total_steel, "total_concrete_m3": total_concrete,
           "sheets_with_inconsistencies": [e["element"].get("label") for e in elements if e.get("checks", {}).get("inconsistencies")]
           + [f"p.{s['page'] + 1}" for s in schedules if s.get("checks", {}).get("inconsistencies")],
           "sheets_with_missing_values": [e["element"].get("label") for e in elements if e.get("unreadable") or e.get("checks", {}).get("indeterminate")]}
    if cover:
        rc = cover["recap"]
        recap_total = (rc.get("ha_shaped_kg") or 0) + (rc.get("ha_straight_kg") or 0)
        out["cover_recap"] = rc
        out["comparison"] = {"a": "Σ Aço das folhas de elementos + Σ listas (massa teórica)", "a_kg": round(total_steel + schedule_steel, 1),
                             "b": "RESUMO DE AÇOS (A500 moldados + não moldados)",
                             "b_kg": round(recap_total, 1), "difference_kg": round(total_steel + schedule_steel - recap_total, 1),
                             "note": "O resumo pode cobrir elementos ausentes das folhas lidas (ou o inverso): diferença a esclarecer, não um erro demonstrado."}
    return out


async def read_sheet(client, model: str, png_b64: str, *, effort: str = "low") -> dict:
    response = await client.responses.create(
        model=model, reasoning={"effort": effort}, instructions=INSTRUCTIONS,
        input=[{"role": "user", "content": [{"type": "input_text", "text": "Transcreve esta folha segundo o esquema."},
                                            {"type": "input_image", "image_url": f"data:image/png;base64,{png_b64}", "detail": "high"}]}],
        text={"format": {"type": "json_schema", "name": "rebar_sheet", "strict": True, "schema": SHEET_SCHEMA}})
    if getattr(response, "status", "completed") != "completed" or not response.output_text:
        raise RuntimeError("Resposta IA incompleta")
    from jsonschema import validate
    data = json.loads(response.output_text)
    validate(data, SHEET_SCHEMA)
    return data, response.usage


async def analyze_pdf(pdf_bytes: bytes, *, user_id: str, plan_id: str | None, pages: list[int] | None = None, concurrency: int = 4,
                      dpi: int = 170, log_usage=None) -> dict:
    """Reads every requested page (default: all) with the configured analysis model; each page is one billed call."""
    import pymupdf
    from engines.openai_studies import MODEL_ANALYSIS, _client
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        n = len(doc)
    pages = pages if pages is not None else list(range(n))
    rot = detect_rotation(pdf_bytes, pages[0]) if pages else 0
    client, sem, sheets = _client(), asyncio.Semaphore(concurrency), {}

    async def one(idx):
        async with sem:
            png = await asyncio.to_thread(render_page_png_b64, pdf_bytes, idx, dpi=dpi, rotate_deg=rot)
            try:
                data, usage = await read_sheet(client, MODEL_ANALYSIS, png)
            except Exception as e:  # noqa: BLE001 — one unreadable page must not lose the others
                logger.warning("rebar vision page %s failed: %s", idx, type(e).__name__)
                sheets[idx] = {"page": idx, "page_kind": "other", "element": None, "elements": [], "schedule_rows": [], "schedule_partial": False, "bars": [], "by_diameter": [], "recap": None, "title_block": None, "notes": [],
                               "unreadable": [f'Leitura IA falhada: {type(e).__name__}'], "error": True}
                return
            if log_usage:
                await log_usage(user_id, None, "rebar_vision", MODEL_ANALYSIS, usage, plan_id)
            sheets[idx] = {"page": idx, **data, "checks": check_sheet(data), "origin": "vision_reading", "model": MODEL_ANALYSIS}

    await asyncio.gather(*(one(i) for i in pages))
    ordered = [sheets[i] for i in pages]
    return {"pages": len(pages), "rotation_deg": rot, "model": MODEL_ANALYSIS, "sheets": ordered, "summary": summarize(ordered),
            "note": ("Leitura visual (texto vetorizado, sem texto nativo): cada valor é uma transcrição a verificar no recorte; os controlos aritméticos assinalam as diferenças sem as corrigir.")}


def is_vision_needed(pdf_bytes: bytes, page_index: int = 0) -> bool:
    import pymupdf
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        return len(doc[page_index].get_text().strip()) < 20


MAX_VISION_PAGES = int(os.environ.get("REBAR_VISION_MAX_PAGES", "40"))
