"""Assistant tool « compute_concrete_volumes » : loads the attached sources (DXF, formwork PDF, section sheets), reuses the stored section
transcription when it exists (one paid vision reading per document, then cached on the plan), assembles the volumes deterministically."""
import asyncio
import base64
import json
import uuid

from engines.metre.coupes_vision import analyze_coupes_pdf, recheck
from engines.metre.level_symbols import parse_level_symbols, words_from_pdf_page
from engines.metre.volumes_tool import compact_for_llm, compute_volumes
from engines.plan_sources import load_cad_source, load_plan_source


async def _pdf(db, plan_id, user_id) -> bytes | None:
    src = await load_plan_source(db, plan_id, user_id)
    if not src or src.get("source_kind") == "cad_render":
        return None
    data = base64.b64decode(src["data_b64"])
    return data if data.startswith(b"%PDF") else None


def _expected_top(pdf: bytes | None) -> float | None:
    if not pdf:
        return None
    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return (parse_level_symbols(words_from_pdf_page(doc[0]))["dominant"] or {}).get("as_plancher_m")


async def coupes_for_plan(db, *, user_id: str, plan_id: str, allow_vision: bool, expected_top_m: float | None, log_usage=None) -> tuple[dict | None, dict]:
    """Stored transcription first (plans_takeoff.coupes_analysis) ; vision only when allowed. Returns (result, status)."""
    plan = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user_id}, {"_id": 0, "coupes_analysis": 1, "filename": 1})
    if not plan:
        return None, {"error": "planta de cortes não encontrada para esta conta"}
    stored = plan.get("coupes_analysis")
    if stored:
        return recheck(stored, expected_top_m), {"origin": "stored_transcription", "pages": stored.get("pages"), "model": stored.get("model")}
    pdf = await _pdf(db, plan_id, user_id)
    if not pdf:
        return None, {"error": "fonte PDF dos cortes indisponível"}
    if not allow_vision:
        return None, {"requires_vision": True, "error": "Caderno de cortes sem leitura registada: volte a lançar com allow_vision=true (uma página = uma chamada faturada, resultado conservado na planta)."}
    res = await analyze_coupes_pdf(pdf, user_id=user_id, plan_id=plan_id, log_usage=log_usage)
    res = recheck(res, expected_top_m)
    await db.plans_takeoff.update_one({"plan_id": plan_id, "user_id": user_id}, {"$set": {"coupes_analysis": res}})
    return res, {"origin": "vision_reading", "pages": res["pages"], "model": res["model"]}


async def run_compute_concrete_volumes(db, *, user_id: str, conversation_id: str, dxf_plan_id: str, formwork_plan_id: str | None, coupes_plan_id: str | None,
                                       allow_vision: bool, levels: dict | None, now: str, log_usage=None) -> dict:
    dxf = await load_cad_source(db, dxf_plan_id, user_id, "converted_dxf") or await load_cad_source(db, dxf_plan_id, user_id, "original")
    if not dxf:
        return {"ok": False, "error": "Nenhum ficheiro DXF/DWG convertido para esta planta: as quantidades em planta (paredes, pilares, laje) vêm do DXF."}
    raw = dxf if isinstance(dxf, (bytes, bytearray)) else base64.b64decode(dxf["data_b64"])
    if raw[:4] == b"AC10":
        return {"ok": False, "error": "DWG não convertido em DXF (conversão Autodesk pendente ou indisponível)."}
    formwork = await _pdf(db, formwork_plan_id, user_id) if formwork_plan_id else None
    status = {"formwork_pdf": bool(formwork), "coupes": None}
    coupes = None
    if coupes_plan_id:
        coupes, status["coupes"] = await coupes_for_plan(db, user_id=user_id, plan_id=coupes_plan_id, allow_vision=allow_vision, expected_top_m=_expected_top(formwork), log_usage=log_usage)
        if status["coupes"].get("requires_vision"):
            return {"ok": False, **status["coupes"], "plan_id": coupes_plan_id}
    res = await asyncio.to_thread(compute_volumes, raw, formwork, coupes, levels)
    compact = json.loads(json.dumps(compact_for_llm(res)))  # string keys only (Mongo)
    rec = {"calc_ref": f"mc_{uuid.uuid4().hex[:10]}", "user_id": user_id, "conversation_id": conversation_id, "tool": "compute_concrete_volumes",
           "args": {"dxf_plan_id": dxf_plan_id, "formwork_plan_id": formwork_plan_id, "coupes_plan_id": coupes_plan_id, "levels": levels},
           "result": {"ok": True, "lines": compact["lines"], "total_m3": compact["total_m3"], "levels": compact["levels"], "heights": compact["heights"], "scope": compact["scope"],
                      "findings": compact["findings"], "walls_by_zone": compact["walls_by_zone"], "sources": compact["sources"]}, "created_at": now}
    await db.assistant_calculations.insert_one(rec)
    return {"ok": True, "calc_ref": rec["calc_ref"], "status": status, **compact}
