"""Routes StructuroPilot — Lecture de plan structure (métré fiable, zéro hallucination)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from engines.access import require_level
from engines import plan_structure_reader as reader
from engines.structuro_plan_pdf import build_structure_report

router = APIRouter(prefix="/structuro/plan", tags=["structuro-plan"],
                   dependencies=[Depends(require_level("pro"))])

from routes.auth import current_user  # noqa: E402


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _nid() -> str:
    return "plan_" + uuid.uuid4().hex[:12]


def _parse_ratios(raw: str | None) -> dict | None:
    """'semelle_isolee:45,poteau:110' ou JSON → {type: ratio}. None si vide."""
    if not raw:
        return None
    import json
    try:
        d = json.loads(raw)
        if isinstance(d, dict):
            return {k: float(v) for k, v in d.items() if v not in (None, "")}
    except Exception:
        pass
    out: dict = {}
    for part in raw.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            try:
                out[k.strip()] = float(v.strip())
            except ValueError:
                continue
    return out or None


@router.get("/list")
async def list_reads(user=Depends(current_user)) -> dict:
    rows = await db.structuro_plan_reads.find(
        {"user_id": user["user_id"]}, {"_id": 0, "fondations": 0, "murs": 0, "texts": 0}
    ).sort("created_at", -1).to_list(100)
    return {"reads": rows}


@router.post("/read")
async def read_plan(file: UploadFile = File(...), title: str = Form(""),
                    steel_ratios: str = Form(""), user=Depends(current_user)) -> dict:
    ext = (file.filename.rsplit(".", 1)[-1] if "." in (file.filename or "") else "").lower()
    if ext != "pdf":
        raise HTTPException(400, "Fournissez un PDF (idéalement vectoriel, exporté de la CAO).")
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(400, "PDF trop volumineux (max 25 Mo).")
    try:
        result = await reader.read_plan(data, steel_ratios=_parse_ratios(steel_ratios))
    except reader.PlanVisionError:
        raise HTTPException(503, "Service de lecture IA momentanément indisponible. Réessayez dans un instant.")
    doc = {
        "read_id": _nid(), "user_id": user["user_id"],
        "title": (title or file.filename or "Plan structure")[:160],
        "filename": file.filename, "created_at": _now(), "updated_at": _now(),
        "steel_ratios_input": steel_ratios or "",
        **result,
    }
    await db.structuro_plan_reads.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.get("/{read_id}")
async def get_read(read_id: str, user=Depends(current_user)) -> dict:
    doc = await db.structuro_plan_reads.find_one(
        {"read_id": read_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture introuvable")
    return doc


class SaveBody(BaseModel):
    title: str | None = None
    fondations: list[dict] = Field(default_factory=list)
    murs: list[dict] = Field(default_factory=list)
    steel_ratios: dict | None = None


@router.put("/{read_id}")
async def update_read(read_id: str, body: SaveBody, user=Depends(current_user)) -> dict:
    doc = await db.structuro_plan_reads.find_one(
        {"read_id": read_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture introuvable")
    recomputed = await reader.recompute(body.fondations, body.murs, body.steel_ratios)
    patch = {"updated_at": _now(), **recomputed}
    if body.title is not None:
        patch["title"] = body.title[:160]
    if body.steel_ratios is not None:
        patch["steel_ratios_input"] = ",".join(f"{k}:{v}" for k, v in body.steel_ratios.items())
    await db.structuro_plan_reads.update_one({"read_id": read_id}, {"$set": patch})
    return {**doc, **patch}


@router.delete("/{read_id}")
async def delete_read(read_id: str, user=Depends(current_user)) -> dict:
    r = await db.structuro_plan_reads.delete_one({"read_id": read_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Lecture introuvable")
    return {"ok": True}


@router.get("/{read_id}/pdf")
async def export_pdf(read_id: str, user=Depends(current_user)) -> Response:
    doc = await db.structuro_plan_reads.find_one(
        {"read_id": read_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Lecture introuvable")
    pdf = build_structure_report(doc, title=doc.get("title") or "Métré structure")
    return Response(content=pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="metre-{read_id}.pdf"'})
