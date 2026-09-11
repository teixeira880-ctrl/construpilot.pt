"""Contrôle des cotes d'un plan : lecture (IA ou DXF) → mesure à l'échelle → rapport + PDF."""
from __future__ import annotations

from fastapi import Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import plan_cotes as C
from engines import plan_texts as T
from engines.plan_ai import read_dimension_lines
from engines.plan_cotes_pdf import build_cotes_pdf, render_cotes_overlay
from routes.plans_analysis import _apply_new_calibration
from routes.plans_common import _now, _resolve_branding, _snapshot, router


class CotesCheckIn(BaseModel):
    page_index: int = Field(default=0, ge=0)
    tol_pct: float = Field(default=2.0, ge=0.1, le=20)
    tol_cm: float = Field(default=3.0, ge=0, le=100)


async def _plan_page(plan_id: str, user_id: str, page_index: int, with_image: bool):
    proj = {"_id": 0, "plan_id": 1, "filename": 1, "kind": 1, "calibrations": 1,
            "ai_analysis": 1, "rooms": 1, "cotes_checks": 1,
            "pages.width_px": 1, "pages.height_px": 1, "pages.dxf_dimensions": 1,
            "pages.dxf_ratio": 1, "pages.unit_to_m": 1}
    if with_image:
        proj["pages.image_png_b64"] = 1
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user_id}, proj)
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    return p, pages[page_index]


async def _ensure_calibration(p: dict, page: dict, plan_id: str, page_index: int,
                              dims: list[dict], w: int, h: int) -> tuple[dict, bool]:
    calib = (p.get("calibrations") or {}).get(str(page_index))
    if calib:
        return calib, False
    if page.get("dxf_dimensions") and page.get("dxf_ratio") and page.get("unit_to_m"):
        ppm = float(page["dxf_ratio"]) / float(page["unit_to_m"])
        payload = {"pixels_per_meter": round(ppm, 4), "meters_per_pixel": round(1 / ppm, 8),
                   "method": "dxf_units", "confidence": 0.99, "created_at": _now()}
    else:
        auto = T.calibration_from_dimension_lines(
            [{"value_m": d["value_m"], "confidence": d.get("confidence", 0.5),
              "bbox_norm": [d["x1"] / w, d["y1"] / h, d["x2"] / w, d["y2"] / h]} for d in dims], w, h)
        if not auto:
            raise HTTPException(422, "Plan non calibré et cotes insuffisantes pour calibrer automatiquement")
        payload = {"pixels_per_meter": auto["pixels_per_meter"], "meters_per_pixel": auto["meters_per_pixel"],
                   "method": "auto_cotes", "confidence": auto["confidence"],
                   "samples_used": auto["samples_used"], "samples_total": auto["samples_total"],
                   "spread_pct": auto["spread_pct"], "created_at": _now()}
    await _apply_new_calibration(p, plan_id, page_index, payload)
    return payload, True


@router.post("/{plan_id}/cotes/check")
async def cotes_check(plan_id: str, body: CotesCheckIn, user=Depends(current_user)) -> dict:
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=True)
    w, h = int(page.get("width_px") or 0), int(page.get("height_px") or 0)
    if not w or not h:
        raise HTTPException(500, "Dimensions de page manquantes")
    reading: dict = {}
    if page.get("dxf_dimensions"):
        dims = C.dims_from_dxf(page["dxf_dimensions"])
        reading = {"source": "dxf", "count": len(dims)}
    else:
        img = page.get("image_png_b64")
        if not img:
            raise HTTPException(500, "Image manquante")
        res = await read_dimension_lines(img)
        if res.get("error"):
            raise HTTPException(502, res["error"])
        dims = C.dims_from_ai(res["dimension_lines"], w, h)
        snapped = C.snap_dims_to_image(img, dims)
        reading = {"source": "ai", "count": len(dims), "scale_text": res.get("scale_text"),
                   "units_hint": res.get("units_hint"), "snapped_endpoints": snapped}
    if not dims:
        raise HTTPException(422, "Aucune cote lisible sur cette page")
    calib, auto = await _ensure_calibration(p, page, plan_id, body.page_index, dims, w, h)
    report = C.check_dimensions(dims, float(calib["pixels_per_meter"]), body.tol_pct, body.tol_cm, w, h)
    ai_rooms = ((p.get("ai_analysis") or {}).get("rooms") or []) \
        if (p.get("ai_analysis") or {}).get("page_index") in (None, body.page_index) else []
    page_rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == body.page_index]
    if ai_rooms and page_rooms:
        report["surfaces"] = T.reconcile_written_surfaces(page_rooms, ai_rooms, float(calib["pixels_per_meter"]))
    report.update({"page_index": body.page_index, "calibration": calib, "auto_calibrated": auto,
                   "reading": reading, "created_at": _now()})
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id}, {"$set": {f"cotes_checks.{body.page_index}": report, "updated_at": _now()}})
    await _snapshot(plan_id, user["user_id"], "cotes_check",
                    {"page": body.page_index, **report["summary"]})
    return report


@router.get("/{plan_id}/cotes")
async def cotes_last(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)) -> dict:
    p, _ = await _plan_page(plan_id, user["user_id"], page_index, with_image=False)
    report = (p.get("cotes_checks") or {}).get(str(page_index))
    if not report:
        raise HTTPException(404, "Aucun contrôle des cotes pour cette page")
    return report


async def _report_and_overlay(plan_id: str, user_id: str, page_index: int):
    p, page = await _plan_page(plan_id, user_id, page_index, with_image=True)
    report = (p.get("cotes_checks") or {}).get(str(page_index))
    if not report:
        raise HTTPException(404, "Lancez d'abord le contrôle des cotes")
    return p, report, render_cotes_overlay(page["image_png_b64"], report)


@router.get("/{plan_id}/cotes/overlay.png")
async def cotes_overlay(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    _, _, png = await _report_and_overlay(plan_id, user["user_id"], page_index)
    return Response(content=png, media_type="image/png")


@router.get("/{plan_id}/cotes/report.pdf")
async def cotes_pdf(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    p, report, png = await _report_and_overlay(plan_id, user["user_id"], page_index)
    branding = await _resolve_branding(user["user_id"])
    pdf = build_cotes_pdf(p, page_index, report, png, branding)
    fname = f"controle-cotes-{plan_id}-p{page_index + 1}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
