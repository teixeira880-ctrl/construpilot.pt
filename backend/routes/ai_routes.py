import uuid
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.db import db
from core.security import current_user, optional_user
from core.rate_limit import limiter
from engines import ai, estimation

router = APIRouter(tags=["ai"])


class ChatIn(BaseModel):
    message: str
    session_id: str | None = None
    project_id: str | None = None


@router.post("/chat")
@limiter.limit("20/minute")
async def chat(body: ChatIn, request: Request, response: Response, user=Depends(optional_user)):
    session_id = body.session_id or f"chat_{uuid.uuid4().hex[:12]}"
    history = await db.chat_messages.find({"session_id": session_id}, {"_id": 0}) \
        .sort("created_at", 1).to_list(50)
    context = ""
    if body.project_id and user:
        p = await db.projects.find_one({"project_id": body.project_id, "user_id": user["user_id"]},
                                       {"_id": 0})
        if p:
            e = p["estimation"]
            context = (f"Projeto « {p['name']} »: {e['project_type_name']}, {e['surface']} m², acabamento {e['finish_level_name']}, orçamento estimado {e['total_avg']:.0f} €. Lotes: {', '.join((l['name'] for l in e['lots']))}.")

    await db.chat_messages.insert_one({
        "session_id": session_id, "user_id": user["user_id"] if user else None,
        "role": "user", "content": body.message,
        "created_at": datetime.now(timezone.utc).isoformat()})

    async def gen() -> None:
        yield f"data: {json.dumps({'session_id': session_id})}\n\n"
        chunks = []
        async for delta in ai.stream_chat(history, body.message, session_id, context):
            chunks.append(delta)
            yield f"data: {json.dumps({'delta': delta})}\n\n"
        full = "".join(chunks)
        await db.chat_messages.insert_one({
            "session_id": session_id, "user_id": user["user_id"] if user else None,
            "role": "assistant", "content": full,
            "created_at": datetime.now(timezone.utc).isoformat()})
        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/chat/{session_id}")
async def chat_history(session_id: str):
    return await db.chat_messages.find({"session_id": session_id}, {"_id": 0}) \
        .sort("created_at", 1).to_list(200)


class PhotoIn(BaseModel):
    image_base64: str
    note: str = ""
    project_id: str | None = None


@router.post("/vision/photo")
async def analyse_photo(body: PhotoIn, user=Depends(optional_user)) -> dict:
    b64 = body.image_base64.split(",")[-1]
    result = await ai.analyse_photo(b64, body.note)
    dims = result.get("estimated_dimensions") or {}
    area = float(dims.get("floor_area_m2") or 9)
    lots = [w.get("lot") for w in result.get("recommended_works", []) if w.get("lot")]
    room = (result.get("room_type") or "").lower()
    ptype = "salle_de_bain" if "bain" in room or "eau" in room else (
        "cuisine" if "cuisine" in room else "renovation_appartement")
    est = estimation.estimate(ptype, area, "standard", "FR", None, "maison",
                              result.get("general_condition", "moyen"), None, lots or None)
    est["planning"] = estimation.planning(est["lots"])
    est["diy_vs_pro"] = estimation.diy_vs_pro(est)
    est["safety_alerts"] = estimation.safety_check(
        " ".join(result.get("risks", [])), [l["key"] for l in est["lots"]])
    if user:
        await db.photo_analyses.insert_one({
            "analysis_id": f"pa_{uuid.uuid4().hex[:10]}", "user_id": user["user_id"],
            "project_id": body.project_id, "result": result,
            "created_at": datetime.now(timezone.utc).isoformat()})
    return {"analysis": result, "estimation": est}


class QuoteIn(BaseModel):
    text: str = ""
    image_base64: str | None = None
    pdf_base64: str | None = None
    project_id: str | None = None
    company: str | None = None


def _extract_pdf_text(b64: str) -> str:
    import base64, io
    from pypdf import PdfReader
    raw = base64.b64decode(b64.split(",")[-1])
    reader = PdfReader(io.BytesIO(raw))
    parts = []
    for page in reader.pages[:15]:  # limite à 15 pages
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts).strip()


@router.post("/quotes/analyse")
async def analyse_quote(body: QuoteIn, user=Depends(optional_user)):
    reference = None
    if body.project_id and user:
        p = await db.projects.find_one({"project_id": body.project_id, "user_id": user["user_id"]},
                                       {"_id": 0})
        if p:
            reference = {"total_avg": p["estimation"]["total_avg"],
                         "lots": [{"nom": l["name"], "total": l["total"]}
                                  for l in p["estimation"]["lots"]]}
    text = body.text or ""
    b64 = body.image_base64.split(",")[-1] if body.image_base64 else None
    if body.pdf_base64:
        try:
            extracted = _extract_pdf_text(body.pdf_base64)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f'PDF ilegível: {e}')
        if not extracted or len(extracted) < 30:
            raise HTTPException(status_code=422,
                                detail="O PDF não contém texto extraível (digitalização em imagem?). Utilize uma captura JPEG/PNG.")
        text = (text + "\n\n" + extracted).strip() if text else extracted
    if not text and not b64:
        raise HTTPException(status_code=400, detail="Forneça um texto, uma imagem ou um PDF")
    result = await ai.analyse_quote(text, b64, reference)
    doc = {"quote_id": f"qt_{uuid.uuid4().hex[:10]}",
           "user_id": user["user_id"] if user else None, "project_id": body.project_id,
           "company": body.company or result.get("company"), "analysis": result,
           "created_at": datetime.now(timezone.utc).isoformat()}
    await db.quote_analyses.insert_one(doc)
    doc.pop("_id", None)
    return doc


@router.get("/quotes")
async def list_quotes(user=Depends(current_user)):
    return await db.quote_analyses.find({"user_id": user["user_id"]}, {"_id": 0}) \
        .sort("created_at", -1).to_list(100)


class CompareIn(BaseModel):
    quote_ids: list[str] | None = None
    quotes: list[dict] | None = None


@router.post("/quotes/compare")
async def compare(body: CompareIn, user=Depends(current_user)):
    quotes = body.quotes or []
    if body.quote_ids:
        docs = await db.quote_analyses.find(
            {"quote_id": {"$in": body.quote_ids}, "user_id": user["user_id"]}, {"_id": 0}).to_list(20)
        quotes = [{"company": d.get("company") or "Empresa",
                   "total": d["analysis"].get("total_ttc") or d["analysis"].get("total_ht"),
                   "lines": d["analysis"].get("lines", []),
                   "exclusions": d["analysis"].get("exclusions", []),
                   "warranties": d["analysis"].get("warranties", [])} for d in docs]
    if len(quotes) < 2:
        raise HTTPException(status_code=400, detail="São necessários pelo menos 2 orçamentos")
    return await ai.compare_quotes(quotes)
