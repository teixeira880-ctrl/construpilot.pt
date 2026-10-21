"""Cross-section sheets (« Coupes ») read visually (vectorised text), then checked deterministically: printed NGF levels (B = brut, F = fini),
slab thicknesses and vertical dimension chains. Wall heights follow the user's rule AS murs = AI plancher haut; every derived height is
tied to the printed vertical chain that confirms it (or flagged)."""
import asyncio
import json
import logging
from collections import Counter
from itertools import combinations

from engines.metre.rebar_vision import NUM, STR, INT, _obj, detect_rotation, render_page_png_b64

logger = logging.getLogger("coupes_vision")

COUPE_SCHEMA = _obj({
    "page_kind": {"type": "string", "enum": ["cover", "coupes", "other"]},
    "title_block": {"anyOf": [_obj({"document_code": STR, "revision_index": STR, "revision_date": STR, "level": STR, "project_ref": STR, "scale": STR}), {"type": "null"}]},
    "coupes": {"type": "array", "items": _obj({
        "name": STR,
        "levels": {"type": "array", "items": _obj({"level_m": NUM, "finish": {"type": ["string", "null"], "enum": ["B", "F", None]}, "position": {"type": ["string", "null"], "enum": ["haut", "bas", "intermediaire", None]}, "label": STR})},
        "vertical_dims_cm": {"type": "array", "items": _obj({"value_cm": NUM, "description": STR})},
        "slab_thickness_cm": {"type": "array", "items": {"type": "number"}},
        "wall_thickness_cm": {"type": "array", "items": {"type": "number"}},
        "annotations": {"type": "array", "items": {"type": "string"}}})},
    "unreadable": {"type": "array", "items": {"type": "string"}},
})

INSTRUCTIONS = "Lês uma folha de cortes de betão armado (gabinete de projeto) apresentada em imagem. Transcreve APENAS o que está impresso.\n- page_kind: «cover» (indicações + legenda), «coupes» (um ou vários «Corte n-n»), caso contrário «other».\n- title_block: código da planta (ex.: GO-B3-R0-200), índice, data, nível (ex.: PH RDC), n.º de processo, escala — se impressos.\n- Para cada corte: name (ex.: «4-4»); levels = cada cota altimétrica escrita (ex.: «93.37 B» → level_m=93.37, finish=B ; «93.44 F» → F ; «92.340» sem letra → null),\n  position haut/bas/intermediaire segundo o seu lugar no corte, label = texto vizinho (TF, soleira, laje…);\n  vertical_dims_cm = todas as cotas verticais (cadeias de cotas verticais) com uma curta descrição (ex.: «laje», «parede entre 89.34 B e 92.34 B», «guarda-corpos»);\n  slab_thickness_cm = espessuras de laje cotadas (a cota vertical da laje); wall_thickness_cm = espessuras horizontais das paredes (ex.: 16, 20, 25);\n  annotations = textos explicativos («Pedra agrafada», «Mísula de betão 65x60ht», «a fornecer»…).\nNenhum valor inventado, nenhum valor corrigido; o que não for legível vai para unreadable."


def _chain_match(target_cm: float, dims: list[float], tol: float = 1.0):
    """A printed vertical dim or the sum of ≤ 3 printed dims equal to the target (±1 cm)."""
    vals = [d for d in dims if d and d >= 5]
    for k in (1, 2, 3):
        for combo in combinations(vals, k):
            if abs(sum(combo) - target_cm) <= tol:
                return list(combo)
    return None


MIN_WALL_M = 2.0  # levels closer than this to the slab top are parapets / bandeaux / seuils, not wall bases


def check_coupe(c: dict, expected_top_m: float | None = None) -> dict:
    """expected_top_m = AS plancher haut (brut) read on the formwork plan symbols; the coupe's top is the printed B level closest to it."""
    brut = [l for l in c.get("levels", []) if l.get("level_m") is not None and l.get("finish") in ("B", None)]
    dims = [d["value_cm"] for d in c.get("vertical_dims_cm", []) if d.get("value_cm") is not None]
    out = {"name": c.get("name"), "levels_b": sorted({l["level_m"] for l in brut}), "slab_thickness_cm": c.get("slab_thickness_cm") or [], "wall_thickness_cm": c.get("wall_thickness_cm") or [],
           "as_plancher_haut_m": None, "ai_plancher_haut_m": None, "base_levels_m": [], "heights": [], "checks": []}
    if not brut:
        out["checks"].append({"check": "níveis brutos", "state": "indeterminate", "note": "nenhum nível B legível"})
        return out
    if expected_top_m is not None:
        top = min((l["level_m"] for l in brut), key=lambda v: abs(v - expected_top_m))
        if abs(top - expected_top_m) > 0.35:
            out["checks"].append({"check": f'AS pavimento {expected_top_m:.2f} B (planta) presente no corte', "state": "to_clarify", "note": f'nível B mais próximo: {top:.2f}'})
    else:
        top = max(l["level_m"] for l in brut)
    out["as_plancher_haut_m"] = top
    out["intermediate_levels_m"] = sorted({l["level_m"] for l in brut if 0 < top - l["level_m"] < MIN_WALL_M})
    out["above_slab_levels_m"] = sorted({l["level_m"] for l in brut if l["level_m"] > top})
    thick = Counter(out["slab_thickness_cm"]).most_common(1)[0][0] if out["slab_thickness_cm"] else None
    if thick:
        out["ai_plancher_haut_m"] = round(top - thick / 100, 3)
    for lv in sorted({l["level_m"] for l in brut if l["level_m"] <= top - MIN_WALL_M}):
        delta_cm = round((top - lv) * 100, 1)
        proof = _chain_match(delta_cm, dims)
        out["checks"].append({"check": f"{top:.2f} B − {lv:.2f} B = {delta_cm:g} cm", "state": "confirmed" if proof else "to_clarify",
                              "printed_chain_cm": proof, "note": None if proof else "nenhuma cota vertical (ou soma de ≤ 3) impressa igual à diferença de níveis"})
        if thick:
            h = round(out["ai_plancher_haut_m"] - lv, 3)
            out["heights"].append({"base_level_m": lv, "h_mur_m": h, "formula": f"({top:.2f} − {thick:g}/100) − {lv:.2f} = {h:.2f} m", "rule": "AS paredes = AI pavimento superior",
                                   "chain_proof_cm": _chain_match(round(h * 100, 1), dims)})
    out["base_levels_m"] = [h["base_level_m"] for h in out["heights"]] or sorted({l["level_m"] for l in brut if l["level_m"] <= top - MIN_WALL_M})
    return out


def recheck(result: dict, expected_top_m: float | None) -> dict:
    """Re-run the deterministic checks on stored transcriptions (no new AI call)."""
    for s in result["sheets"]:
        if s.get("coupes"):
            s["coupes_checked"] = [check_coupe(c, expected_top_m) for c in s["coupes"]]
    result["summary"] = summarize(result["sheets"])
    result["summary"]["expected_top_m"] = expected_top_m
    return result


def summarize(sheets: list[dict]) -> dict:
    coupes = [c for s in sheets if s.get("page_kind") == "coupes" for c in s.get("coupes_checked", [])]
    tops = Counter(c["as_plancher_haut_m"] for c in coupes if c["as_plancher_haut_m"])
    thick = Counter(t for c in coupes for t in c["slab_thickness_cm"])
    bases = Counter(b for c in coupes for b in c["base_levels_m"])
    walls = Counter(t for c in coupes for t in c["wall_thickness_cm"])
    tb = next((s["title_block"] for s in sheets if s.get("title_block")), None)
    heights = [h for c in coupes for h in c["heights"]]
    return {"title_block": tb, "coupes": [c["name"] for c in coupes], "as_plancher_haut_m": dict(tops), "slab_thickness_cm": dict(thick), "base_levels_m": dict(bases),
            "wall_thickness_cm": dict(walls), "heights": heights,
            "dominant": {"as_plancher_haut_m": tops.most_common(1)[0][0] if tops else None, "epaisseur_dalle_cm": thick.most_common(1)[0][0] if thick else None,
                         "niveau_base_murs_m": bases.most_common(1)[0][0] if bases else None},
            "confirmed_level_gaps": sum(1 for c in coupes for k in c["checks"] if k["state"] == "confirmed"),
            "unconfirmed_level_gaps": sum(1 for c in coupes for k in c["checks"] if k["state"] != "confirmed"),
            "note": "Níveis e espessuras lidos nos cortes (transcrição visual); cada diferença de níveis é confrontada com a cadeia de cotas vertical impressa. Alturas das paredes = AI pavimento superior − nível de base (regra do utilizador), por zona de nível de base."}


async def analyze_coupes_pdf(pdf_bytes: bytes, *, user_id: str, plan_id: str | None, pages: list[int] | None = None, log_usage=None, concurrency: int = 4) -> dict:
    import pymupdf
    from jsonschema import validate
    from engines.openai_studies import MODEL_ANALYSIS, _client
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        n = len(doc)
    pages = pages if pages is not None else list(range(n))
    rot = detect_rotation(pdf_bytes, pages[0]) if pages else 0
    client, sem, sheets = _client(), asyncio.Semaphore(concurrency), {}

    async def one(idx):
        async with sem:
            png = await asyncio.to_thread(render_page_png_b64, pdf_bytes, idx, dpi=180, rotate_deg=rot)
            try:
                r = await client.responses.create(model=MODEL_ANALYSIS, reasoning={"effort": "low"}, instructions=INSTRUCTIONS,
                                                  input=[{"role": "user", "content": [{"type": "input_text", "text": "Transcreve esta folha de cortes segundo o esquema."},
                                                                                       {"type": "input_image", "image_url": f"data:image/png;base64,{png}", "detail": "high"}]}],
                                                  text={"format": {"type": "json_schema", "name": "coupes_sheet", "strict": True, "schema": COUPE_SCHEMA}})
                data = json.loads(r.output_text)
                validate(data, COUPE_SCHEMA)
            except Exception as e:  # noqa: BLE001
                logger.warning("coupes vision page %s failed: %s", idx, type(e).__name__)
                sheets[idx] = {"page": idx, "page_kind": "other", "title_block": None, "coupes": [], "unreadable": [f'Leitura IA falhada: {type(e).__name__}'], "error": True}
                return
            if log_usage:
                await log_usage(user_id, None, "coupes_vision", MODEL_ANALYSIS, r.usage, plan_id)
            sheets[idx] = {"page": idx, **data, "coupes_checked": [check_coupe(c) for c in data.get("coupes", [])], "origin": "vision_reading", "model": MODEL_ANALYSIS}

    await asyncio.gather(*(one(i) for i in pages))
    ordered = [sheets[i] for i in pages]
    return {"pages": len(pages), "rotation_deg": rot, "model": MODEL_ANALYSIS, "sheets": ordered, "summary": summarize(ordered)}
