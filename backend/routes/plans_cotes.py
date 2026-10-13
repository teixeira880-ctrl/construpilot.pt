"""Contrôle des cotes d'un plan : lecture (IA ou DXF) → mesure à l'échelle → rapport + PDF."""
from __future__ import annotations

import re
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user
from engines import plan_cotes as C
from engines import plan_texts as T
from engines.plan_ai import read_dimension_lines
from engines.plan_cotes_pdf import (
    build_cotes_pdf,
    build_cotes_pdf_multi,
    render_cotes_overlay,
)
from engines.plan_pdf_i18n import LANG as PDF_LANG
from engines.plan_pdf_i18n import disclaimer, tr
from routes.plans_common import _apply_new_calibration
from routes.plans_common import _now, _resolve_branding, _snapshot, router


class CotesCheckIn(BaseModel):
    page_index: int = Field(default=0, ge=0)
    tol_pct: float = Field(default=2.0, ge=0.1, le=20)
    tol_cm: float = Field(default=3.0, ge=0, le=100)


async def _plan_page(plan_id: str, user_id: str, page_index: int, with_image: bool):
    proj = {"_id": 0, "plan_id": 1, "user_id": 1, "filename": 1, "kind": 1, "calibrations": 1, "detected_scale_denominator": 1, "page_count": 1,
            "ai_analysis": 1, "rooms": 1, "cotes_checks": 1,
            "pages.width_px": 1, "pages.height_px": 1, "pages.dxf_dimensions": 1,
            "pages.dxf_ratio": 1, "pages.unit_to_m": 1, "pages.dpi": 1,
            "pages.pdf_dimensions": 1, "pages.pdf_vector_scale": 1, "pages.pdf_elements": 1, "pages.pdf_auto_spans": 1,
            "pages.vectors": 1, "pages.text_blocks": 1, "pages.walls_analysis": 1,
            "pages.geometry_version": 1, "pages.vectors_truncated": 1,
            "pages.auto_calibration_blocked": 1, "pages.interior_analysis_blocked": 1,
            "pages.reading_warnings": 1, "pages.detected_scale_denominator": 1,
            "pages.geometry_coordinate_space": 1, "pages.cad_import": 1}
    if with_image:
        proj["pages.image_png_b64"] = 1
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user_id}, proj)
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    for index, report in list((p.get("cotes_checks") or {}).items()):
        if report.get("calibration_stale") and 0 <= int(index) < len(pages):
            p["cotes_checks"][index] = await _recompute(
                p, pages[int(index)], plan_id, int(index), report, report.get("items") or [], 2.0, 3.0)
    return p, pages[page_index]


def _vector_dims(page: dict) -> dict:
    """Cotes vectorielles d'une page PDF : stockées à l'import, sinon recalculées depuis vecteurs/textes stockés."""
    if page.get("pdf_dimensions") is not None and page.get("pdf_vector_scale") is not None:
        return {"dimensions": page["pdf_dimensions"], **page["pdf_vector_scale"]}
    if not page.get("vectors") or not page.get("text_blocks") or not page.get("dpi"):
        return {"dimensions": []}
    from engines.plan_vector_pdf import extract_vector_dimensions
    res = extract_vector_dimensions(page["vectors"], page["text_blocks"], float(page["dpi"]) / 72)
    res["partial_vectors"] = len(page["vectors"]) >= 2500
    return res


async def _ensure_calibration(p: dict, page: dict, plan_id: str, page_index: int,
                              dims: list[dict], w: int, h: int, vec: dict | None = None) -> tuple[dict, bool]:
    calib = (p.get("calibrations") or {}).get(str(page_index))
    if vec and vec.get("pt_per_m") and (vec.get("matched") or 0) >= 3 and page.get("dpi"):
        ppm = float(vec["pt_per_m"]) * float(page["dpi"]) / 72
        if not calib or (calib.get("method") not in ("manual", "two_points", "known_dimension") and abs(ppm / float(calib["pixels_per_meter"]) - 1) > 0.02):
            payload = {"pixels_per_meter": round(ppm, 4), "meters_per_pixel": round(1 / ppm, 8),
                       "method": "pdf_vector", "confidence": 0.98, "samples_used": vec.get("matched"),
                       "effective_scale_denominator": round(1000 * 72 / 25.4 / float(vec["pt_per_m"]), 1),
                       "scale_denominator": p.get("detected_scale_denominator"), "created_at": _now()}
            await _apply_new_calibration(plan_id, p["user_id"], page_index, payload)
            return payload, True
    if calib:
        return calib, False
    if page.get("geometry_coordinate_space") == "image_px" and page.get("dxf_ratio") and page.get("unit_to_m"):
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
    await _apply_new_calibration(plan_id, p["user_id"], page_index, payload)
    return payload, True


def _ai_image(img_b64: str, max_side: int = 2200) -> str:
    """Réduit l'image envoyée à l'IA (grands plans A0/A1) — les bbox normalisées restent valables."""
    import base64
    import io

    from PIL import Image
    im = Image.open(io.BytesIO(base64.b64decode(img_b64)))
    if max(im.size) <= max_side:
        return img_b64
    im.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _interior_report(page: dict, items: list[dict], pixels_per_meter: float | None = None) -> dict:
    """Murs / mesures intérieures nu-à-nu / fermetures (moteur vectoriel) avec renvoi vers l'index des cotes du rapport."""
    from engines.plan_refresh import refresh_interior
    wa = refresh_interior(page, items, pixels_per_meter)
    page["walls_analysis"] = wa
    pdims = page.get("pdf_dimensions") or []

    def item_for(idx):
        if wa.get("cote_index_space") == "report":
            return idx
        if not idx or idx > len(pdims):
            return None
        d = pdims[idx - 1]
        for it in items:
            if all(abs(it[k] - d[k]) < 1.5 for k in ("x1", "y1", "x2", "y2")):
                return it["index"]
        return None
    meas = [{**m, "item_index": item_for(m.get("written_cote_index"))} for m in wa.get("interior_measurements") or []]
    rows = [{**r, "item_index": item_for(r.get("written_cote_index"))} for r in wa.get("closure_equations") or []]
    cotes = [{**c, "item_index": item_for(c.get("index"))} for c in wa.get("cotes") or []]
    per = wa.get("peripheral") or None
    if per:
        per = {**per, "inconsistencies": [{**x, "a_item_index": item_for(x.get("a_index")), "b_item_index": item_for(x.get("b_index"))}
                                          for x in per.get("inconsistencies") or []],
               "chains": [{**c, "total_item_index": item_for(c.get("total_index") or c.get("reference_index"))} for c in per.get("chains") or []]}
    return {"walls": wa["walls"], "interior_measurements": meas, "closure_equations": rows, "cotes": cotes, "peripheral": per,
            "legend": wa.get("legend"), "coverage": wa.get("coverage"),
            "engine_version": wa.get("engine_version"),
            "sections_ignored": wa.get("sections_ignored") or [], "stats": wa.get("stats"), "validation": wa.get("validation")}


async def _ensure_current_geometry(p: dict, page: dict, plan_id: str, page_index: int, user_id: str) -> bool:
    from engines.plan_refresh import GEOMETRY_VERSION, extract_page_geometry
    if p.get("kind") != "pdf" or page.get("geometry_version") == GEOMETRY_VERSION:
        return False
    import asyncio
    import base64
    from engines.plan_sources import load_plan_source
    src = await load_plan_source(db, plan_id, user_id)
    if not src:
        return False  # refresh_interior donnera explicitement un résultat incomplet
    updated = await asyncio.to_thread(extract_page_geometry, base64.b64decode(src["data_b64"]),
                                       page_index, float(page.get("dpi") or 72) / 72)
    page.update(updated)
    await db.plans_takeoff.update_one({"plan_id": plan_id, "user_id": user_id, "pages.index": page_index},
                                      {"$set": {**{f"pages.$.{k}": v for k,v in updated.items()}, "updated_at": _now()},
                                       "$unset": {f"studies.{page_index}": "", f"cotes_checks.{page_index}.geometry": ""}})
    return True


async def _run_check(p: dict, page: dict, plan_id: str, page_index: int,
                     tol_pct: float, tol_cm: float, user_id: str) -> dict:
    await _ensure_current_geometry(p, page, plan_id, page_index, user_id)
    w, h = int(page.get("width_px") or 0), int(page.get("height_px") or 0)
    if not w or not h:
        raise HTTPException(500, "Dimensions de page manquantes")
    reading: dict = {}
    vec: dict | None = None
    if p.get("kind") == "dxf" and page.get("dxf_dimensions") is not None:
        dims = C.dims_from_dxf(page["dxf_dimensions"])
        reading = {"source": "dxf", "count": len(dims)}
    else:
        img = page.get("image_png_b64")
        if not img:
            raise HTTPException(500, "Image manquante")
        vec = _vector_dims(page) if p.get("kind") == "pdf" else None
        vdims = C.dims_from_pdf_vectors((vec or {}).get("dimensions"))
        res = await read_dimension_lines(_ai_image(img), await _report_lang(user_id))
        if res.get("error"):
            if not vdims:
                raise HTTPException(502, res["error"])
            res = {"dimension_lines": [], "error_ai": res["error"]}
        adims = C.dims_from_ai(res["dimension_lines"], w, h)
        snapped = C.snap_dims_to_image(img, adims)
        reading = {"scale_text": res.get("scale_text"), "units_hint": res.get("units_hint"),
                   "snapped_endpoints": snapped, "ai_error": res.get("error_ai")}
        if vdims:
            complete = (vec.get("matched") or 0) >= 0.9 * (vec.get("texts_numeric") or 1) and not vec.get("partial_vectors") and not any(d.get("unverified") for d in vdims)
            dims, cross = C.merge_vector_and_ai(vdims, adims, w, h, vector_complete=complete)
            reading.update({"source": "pdf_vector+ai", "count": len(dims), "cross": cross,
                            "vector": {k: v for k, v in vec.items() if k != "dimensions"}})
        else:
            dims = adims
            reading.update({"source": "ai", "count": len(dims)})
    if not dims and p.get("kind") != "dxf":
        raise HTTPException(422, "Aucune cote lisible sur cette page")
    calib, auto = await _ensure_calibration(p, page, plan_id, page_index, dims, w, h, vec)
    from engines.plan_refresh import carry_user_edits
    previous = ((p.get("cotes_checks") or {}).get(str(page_index)) or {})
    unmatched = carry_user_edits(dims, previous.get("items") or [])
    if unmatched:
        raise HTTPException(409, f"Corrections conservées dans le rapport précédent : cotes {unmatched} à rapprocher de la nouvelle extraction")
    report = C.check_dimensions(dims, float(calib["pixels_per_meter"]), tol_pct, tol_cm, w, h,
                                elements=page.get("pdf_elements") or [], auto_spans=page.get("pdf_auto_spans") or [])
    ai_rooms = ((p.get("ai_analysis") or {}).get("rooms") or []) \
        if (p.get("ai_analysis") or {}).get("page_index") in (None, page_index) else []
    page_rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    if ai_rooms and page_rooms:
        report["surfaces"] = T.reconcile_written_surfaces(page_rooms, ai_rooms, float(calib["pixels_per_meter"]))
    report.update({"page_index": page_index, "calibration": calib, "auto_calibrated": auto,
                   "reading": reading, "created_at": _now(), "interior": _interior_report(page, report["items"], float(calib["pixels_per_meter"])), "engine_version": 2, "revision": uuid.uuid4().hex})
    prev_geo = ((p.get("cotes_checks") or {}).get(str(page_index)) or {}).get("geometry")
    if prev_geo:  # ne jamais perdre les passes IA (2-4) : conservées et marquées à rafraîchir
        report["geometry"] = {**prev_geo, "stale": True, "stale_since": _now()}
    open_issues = await db.plan_report_issues.count_documents({"plan_id": plan_id, "page_index": page_index, "status": "open"})
    report.update({"open_issues": open_issues, "under_review": open_issues > 0})
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user_id},
        {"$set": {f"cotes_checks.{page_index}": report, "updated_at": _now()}, "$unset": {f"studies.{page_index}": ""}})
    await _snapshot(plan_id, user_id, "cotes_check", {"page": page_index, **report["summary"]})
    await _push_version(plan_id, user_id, page_index, report, "check")
    return report


async def _push_version(plan_id: str, user_id: str, page_index: int, report: dict, trigger: str, issue_id: str | None = None) -> dict:
    """Historique des versions du rapport : une entrée par recalcul (résumé, validation intérieure, incohérences périphériques)."""
    n = await db.plan_report_versions.count_documents({"plan_id": plan_id, "page_index": page_index}) + 1
    it = report.get("interior") or {}
    v = {"version_id": f"ver_{uuid.uuid4().hex[:8]}", "plan_id": plan_id, "user_id": user_id, "page_index": page_index, "version": n,
         "trigger": trigger, "issue_id": issue_id, "summary": report.get("summary"), "interior_validation": it.get("validation"),
         "interior_stats": it.get("stats"), "peripheral_inconsistencies": ((it.get("peripheral") or {}).get("inconsistencies") or [])[:20],
         "open_issues": await db.plan_report_issues.count_documents({"plan_id": plan_id, "page_index": page_index, "status": "open"}),
         "created_at": _now()}
    await db.plan_report_versions.insert_one(dict(v))
    v.pop("_id", None)
    return v


class IssueIn(BaseModel):
    page_index: int = Field(0, ge=0)
    target: str = Field("", max_length=80)
    element: str = Field(min_length=2, max_length=200)
    description: str = Field(min_length=5, max_length=3000)
    expected_value: str = Field("", max_length=80)


@router.post("/{plan_id}/cotes/issues")
async def report_issue(plan_id: str, body: IssueIn, user=Depends(current_user)) -> dict:
    """« Signaler une erreur d'analyse » : l'utilisateur désigne une cote / mesure / élément et décrit l'erreur ; l'analyse
    est marquée à réviser, une version « signalement » est archivée et l'assistant en tient compte."""
    p, _ = await _plan_page(plan_id, user["user_id"], body.page_index, False)
    issue = {"issue_id": f"iss_{uuid.uuid4().hex[:8]}", "plan_id": plan_id, "user_id": user["user_id"], "page_index": body.page_index,
             "target": body.target, "element": body.element.strip(), "description": body.description.strip(),
             "expected_value": body.expected_value.strip(), "status": "open", "created_at": _now(), "resolved_at": None, "resolution": None}
    await db.plan_report_issues.insert_one(dict(issue))
    issue.pop("_id", None)
    report = (p.get("cotes_checks") or {}).get(str(body.page_index)) or {}
    if report:
        await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {f"cotes_checks.{body.page_index}.under_review": True,
                                                                          f"cotes_checks.{body.page_index}.open_issues": 1 + await db.plan_report_issues.count_documents(
                                                                              {"plan_id": plan_id, "page_index": body.page_index, "status": "open"}) - 1}})
        await _push_version(plan_id, user["user_id"], body.page_index, report, "issue_reported", issue["issue_id"])
    return issue


@router.patch("/{plan_id}/cotes/issues/{issue_id}")
async def resolve_issue(plan_id: str, issue_id: str, body: dict, user=Depends(current_user)) -> dict:
    res = (body or {}).get("resolution", "").strip()[:2000]
    r = await db.plan_report_issues.update_one({"issue_id": issue_id, "plan_id": plan_id, "user_id": user["user_id"]},
                                               {"$set": {"status": "resolved", "resolved_at": _now(), "resolution": res}})
    if not r.matched_count:
        raise HTTPException(404, "Signalement introuvable")
    iss = await db.plan_report_issues.find_one({"issue_id": issue_id}, {"_id": 0})
    remaining = await db.plan_report_issues.count_documents({"plan_id": plan_id, "page_index": iss["page_index"], "status": "open"})
    await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {f"cotes_checks.{iss['page_index']}.under_review": remaining > 0,
                                                                      f"cotes_checks.{iss['page_index']}.open_issues": remaining}})
    return iss


@router.get("/{plan_id}/cotes/inconsistencies.pdf")
async def inconsistencies_pdf(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    """Une page : incohérences des chaînes périphériques, à transmettre à l'architecte / BET."""
    from engines.compare_pdf import build_inconsistencies_pdf
    p, _ = await _plan_page(plan_id, user["user_id"], page_index, False)
    report = (p.get("cotes_checks") or {}).get(str(page_index))
    if not report or not (report.get("interior") or {}).get("peripheral"):
        raise HTTPException(404, "Aucune chaîne périphérique analysée sur cette page")
    branding = await _resolve_branding(user["user_id"])
    pdf = build_inconsistencies_pdf(p, page_index, report, branding, _lang_of(branding))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="incoherences-{plan_id[-6:]}-p{page_index + 1}.pdf"'})


@router.post("/{plan_id}/cotes/issues/{issue_id}/reanalyze")
async def guided_reanalysis(plan_id: str, issue_id: str, user=Depends(current_user)) -> dict:
    """Correction guidée en tâche de fond (ré-extraction + recalcul ciblé) → {job_id} à suivre sur /cotes-jobs/{job_id}."""
    iss = await db.plan_report_issues.find_one({"issue_id": issue_id, "plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "issue_id": 1})
    if not iss:
        raise HTTPException(404, "Signalement introuvable")
    return _start_job(lambda: _guided_reanalysis(plan_id, issue_id, user), user["user_id"])


async def _guided_reanalysis(plan_id: str, issue_id: str, user: dict) -> dict:
    """Correction guidée : recalcule uniquement la cible du signalement (cote n° / mesure INT-… / chaîne) après ré-extraction
    vectorielle, compare avant/après et archive une version « guided_correction » ; clôt le signalement si la cible a changé."""
    iss = await db.plan_report_issues.find_one({"issue_id": issue_id, "plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0})
    if not iss:
        raise HTTPException(404, "Signalement introuvable")
    page_index = iss["page_index"]
    p, page = await _plan_page(plan_id, user["user_id"], page_index, True)
    before = (p.get("cotes_checks") or {}).get(str(page_index)) or {}

    def _target(rep: dict):
        t = (iss.get("target") or "").strip()
        m = re.match(r"(?i)cote\s*n[°º]?\s*(\d+)", t) or re.match(r"^(\d+)$", t)
        if m:
            it = next((x for x in rep.get("items") or [] if x.get("index") == int(m.group(1))), None)
            return {"kind": "cote", "index": int(m.group(1)), "indicated_m": it and it.get("indicated_m"), "measured_m": it and it.get("measured_m"),
                    "status": it and it.get("status")}
        if t.upper().startswith("INT-"):
            mm = next((x for x in ((rep.get("interior") or {}).get("interior_measurements") or []) if x["measurement_id"] == t.upper()), None)
            return {"kind": "measurement", "id": t.upper(), "geometric_m": mm and mm.get("geometric_dimension_m"),
                    "written_m": mm and mm.get("written_dimension_m"), "status": mm and mm.get("status")}
        return {"kind": "page", "summary": rep.get("summary"), "interior_complete": ((rep.get("interior") or {}).get("validation") or {}).get("complete")}
    tb = _target(before)
    from engines.plan_sources import load_plan_source
    src = await load_plan_source(db, plan_id, user["user_id"])
    if src and src.get("data_b64") and p.get("kind") in ("pdf", "dxf"):
        await cotes_reextract(plan_id, user)
        p, page = await _plan_page(plan_id, user["user_id"], page_index, True)
    after_report = await _run_check(p, page, plan_id, page_index, before.get("tol_pct") or 2.0, before.get("tol_cm") or 3.0, user["user_id"])
    ta = _target(after_report)
    changed = tb != ta
    v = await _push_version(plan_id, user["user_id"], page_index, after_report, "guided_correction", issue_id)
    await db.plan_report_versions.update_one({"version_id": v["version_id"]}, {"$set": {"target_before": tb, "target_after": ta, "changed": changed}})
    resolution = (f"Correction guidée : cible recalculée ({'valeur modifiée' if changed else 'valeur inchangée'}) — avant {tb} / après {ta}")[:2000]
    if changed:
        await db.plan_report_issues.update_one({"issue_id": issue_id}, {"$set": {"status": "resolved", "resolved_at": _now(), "resolution": resolution}})
    else:
        await db.plan_report_issues.update_one({"issue_id": issue_id}, {"$set": {"resolution": resolution, "last_reanalysis_at": _now()}})
    remaining = await db.plan_report_issues.count_documents({"plan_id": plan_id, "page_index": page_index, "status": "open"})
    await db.plans_takeoff.update_one({"plan_id": plan_id}, {"$set": {f"cotes_checks.{page_index}.under_review": remaining > 0, f"cotes_checks.{page_index}.open_issues": remaining}})
    return {"issue_id": issue_id, "changed": changed, "target_before": tb, "target_after": ta, "version": v["version"], "resolved": changed}


@router.get("/{plan_id}/cotes/versions")
async def list_versions(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)) -> dict:
    await _plan_page(plan_id, user["user_id"], page_index, False)
    versions = [v async for v in db.plan_report_versions.find({"plan_id": plan_id, "page_index": page_index}, {"_id": 0}).sort("version", -1).limit(50)]
    issues = [i async for i in db.plan_report_issues.find({"plan_id": plan_id, "page_index": page_index}, {"_id": 0}).sort("created_at", -1).limit(100)]
    return {"versions": versions, "issues": issues}


def _start_job(coro_factory, user_id: str) -> dict:
    """Lance un traitement long en tâche de fond (évite le timeout 60 s de l'ingress) → {job_id}.

    État persisté dans `cotes_jobs` (survit aux rechargements et au multi-pods)."""
    import asyncio
    import uuid
    from datetime import datetime, timezone
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    async def runner():
        await db.cotes_jobs.insert_one({"job_id": job_id, "user_id": user_id, "status": "running",
                                        "started_at": _now(), "created": datetime.now(timezone.utc)})
        try:
            result = await coro_factory()
            upd = {"status": "done", "result": result, "finished_at": _now()}
        except HTTPException as e:
            upd = {"status": "error", "error": e.detail, "finished_at": _now()}
        except Exception as e:  # noqa: BLE001
            upd = {"status": "error", "error": f"{type(e).__name__}: {e}"[:300], "finished_at": _now()}
        await db.cotes_jobs.update_one({"job_id": job_id}, {"$set": upd})

    asyncio.create_task(runner())
    return {"job_id": job_id, "status": "running"}


@router.get("/cotes-jobs/{job_id}")
async def cotes_job(job_id: str, user=Depends(current_user)) -> dict:
    j = await db.cotes_jobs.find_one({"job_id": job_id, "user_id": user["user_id"]}, {"_id": 0, "user_id": 0, "created": 0})
    if not j:
        # insertion juste après le lancement : laisser le client re-sonder
        return {"job_id": job_id, "status": "running"}
    return j


@router.post("/{plan_id}/cotes/check")
async def cotes_check(plan_id: str, body: CotesCheckIn, background: bool = Query(False),
                      user=Depends(current_user)) -> dict:
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=True)
    if background:
        return _start_job(lambda: _run_check(p, page, plan_id, body.page_index, body.tol_pct, body.tol_cm, user["user_id"]),
                          user["user_id"])
    return await _run_check(p, page, plan_id, body.page_index, body.tol_pct, body.tol_cm, user["user_id"])


class CotesCheckAllIn(BaseModel):
    tol_pct: float = Field(default=2.0, ge=0.1, le=20)
    tol_cm: float = Field(default=3.0, ge=0, le=100)


def _global_summary(reports: list[dict]) -> dict:
    sums = [r["summary"] for r in reports]
    agg = {k: sum(s.get(k, 0) for s in sums)
           for k in ("total", "ok", "warn", "ko", "ignored", "chains_total", "chains_ko", "chains_warn")}
    agg["max_delta_cm"] = max((s.get("max_delta_cm", 0) for s in sums), default=0)
    agg["pages"] = len(reports)
    agg["verdict"] = ("ko" if agg["ko"] or agg["chains_ko"]
                      else "warn" if agg["warn"] or agg["chains_warn"] else "ok")
    return agg


@router.post("/{plan_id}/cotes/check-all")
async def cotes_check_all(plan_id: str, body: CotesCheckAllIn, background: bool = Query(False),
                          user=Depends(current_user)) -> dict:
    """Contrôle des cotes sur toutes les pages (lectures IA en parallèle)."""
    import asyncio
    p, _ = await _plan_page(plan_id, user["user_id"], 0, with_image=True)
    pages = p.get("pages") or []

    async def one(i: int):
        try:
            return await _run_check(p, pages[i], plan_id, i, body.tol_pct, body.tol_cm, user["user_id"])
        except HTTPException as e:
            return {"page_index": i, "error": e.detail}

    async def run_all():
        results = await asyncio.gather(*(one(i) for i in range(len(pages))))
        done = [r for r in results if "error" not in r]
        errors = [{"page_index": r["page_index"], "error": r["error"]} for r in results if "error" in r]
        return {"pages": [{"page_index": r["page_index"], "summary": r["summary"]} for r in done],
                "errors": errors, "summary": _global_summary(done) if done else None,
                "tolerance": {"pct": body.tol_pct, "cm": body.tol_cm}}

    if background:
        return _start_job(run_all, user["user_id"])
    return await run_all()


@router.get("/{plan_id}/cotes/report-all.pdf")
async def cotes_pdf_all(plan_id: str, user=Depends(current_user)):
    """Rapport PDF global : synthèse multi-pages + détail et plan annoté de chaque page."""
    p, _ = await _plan_page(plan_id, user["user_id"], 0, with_image=True)
    checks = p.get("cotes_checks") or {}
    pages = p.get("pages") or []
    bundle = []
    for i, page in enumerate(pages):
        rep = checks.get(str(i))
        if rep:
            bundle.append((i, rep, render_cotes_overlay(page["image_png_b64"], rep)))
    if not bundle:
        raise HTTPException(404, "Aucune page contrôlée — lancez d'abord le contrôle des cotes")
    branding = await _resolve_branding(user["user_id"])
    PDF_LANG.set(_lang_of(branding))
    pdf = build_cotes_pdf_multi(p, bundle, _global_summary([b[1] for b in bundle]), branding)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="controle-cotes-{plan_id}-global.pdf"'})


latest_router = APIRouter(prefix="/cotes", tags=["cotes"])


@latest_router.get("/latest")
async def cotes_latest(user=Depends(current_user)) -> dict:
    """Dernier contrôle des cotes de l'utilisateur (tuile tableau de bord)."""
    cur = db.plans_takeoff.find({"user_id": user["user_id"], "cotes_checks": {"$exists": True, "$ne": {}}},
                                {"_id": 0, "plan_id": 1, "filename": 1, "cotes_checks": 1})
    best = None
    plans_checked = 0
    async for pl in cur:
        checks = pl.get("cotes_checks") or {}
        if not checks:
            continue
        plans_checked += 1
        reps = [r for r in checks.values() if r.get("summary")]
        if not reps:
            continue
        ts = max((r.get("recomputed_at") or r.get("created_at") or "") for r in reps)
        if not best or ts > best["checked_at"]:
            agg = _global_summary(reps)
            worst = min(checks.items(), key=lambda kv: {"ko": 0, "warn": 1, "ok": 2}.get(
                (kv[1].get("summary") or {}).get("verdict"), 3))
            best = {"plan_id": pl["plan_id"], "filename": pl.get("filename"), "page_index": int(worst[0]),
                    "pages_checked": len(reps), "checked_at": ts, "summary": agg, "verdict": agg["verdict"]}
    return {"latest": best, "plans_checked": plans_checked}



class GeometryIn(BaseModel):
    page_index: int = Field(default=0, ge=0)


def _lang_of(branding: dict | None) -> str:
    return "pt" if ((branding or {}).get("country") or "").upper() == "PT" else "fr"


async def _report_lang(user_id: str) -> str:
    """Langue des analyses/rapports de plans : PT si l'entreprise est au Portugal, sinon FR."""
    return _lang_of(await _resolve_branding(user_id))


@router.post("/{plan_id}/cotes/geometry")
async def cotes_geometry(plan_id: str, body: GeometryIn, background: bool = Query(False),
                         user=Depends(current_user)) -> dict:
    """Analyse géométrique complète (double lecture IA) : fermetures, contrôles croisés, façades, anomalies."""
    from engines.plan_geometry_ai import analyze_geometry
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=True)
    lang = await _report_lang(user["user_id"])

    async def run():
        report = (p.get("cotes_checks") or {}).get(str(body.page_index))
        if not report or report.get("engine_version") != 2 or not report.get("revision"):
            report = await _run_check(p, page, plan_id, body.page_index, 2.0, 3.0, user["user_id"])
        geo = await analyze_geometry(_ai_image(page["image_png_b64"]), report,
                                     int(page.get("width_px") or 0), int(page.get("height_px") or 0), lang)
        if geo.get("error"):
            raise HTTPException(502, geo["error"])
        geo["created_at"] = _now()
        prev_nar = ((report.get("geometry") or {}).get("narratif"))
        if prev_nar:
            geo["narratif"] = {**prev_nar, "stale": True}
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id}, {"$set": {f"cotes_checks.{body.page_index}.geometry": geo, "updated_at": _now()}})
        await _snapshot(plan_id, user["user_id"], "cotes_geometry",
                        {"page": body.page_index, "niveau": geo["niveau_global"], "anomalies": len(geo["anomalies"])})
        return geo

    if background:
        return _start_job(run, user["user_id"])
    return await run()


@router.post("/{plan_id}/cotes/reextract")
async def cotes_reextract(plan_id: str, user=Depends(current_user)) -> dict:
    """Relit la source native ; préserve le repère CAO et les corrections utilisateur."""
    import asyncio
    import base64
    from engines.plan_refresh import extract_page_geometry, carry_user_edits
    from engines.plan_sources import load_plan_source, load_cad_source

    owner = {"plan_id": plan_id, "user_id": user["user_id"]}
    p = await db.plans_takeoff.find_one(owner, {"_id": 0})
    if not p: raise HTTPException(404, "Plan introuvable")
    if p.get("kind") not in ("pdf", "dxf"):
        raise HTTPException(422, "Ce plan image doit être relu par l’analyse visuelle, sans extraction vectorielle.")
    prepared = []
    if p.get("kind") == "dxf":
        from engines.plan_dxf import process_dxf
        from engines.cad_geometry import UNIT_FACTORS
        filename = p.get("filename") or "plan.dxf"
        kind = "converted_dxf" if filename.lower().endswith(".dwg") else "original"
        data = await load_cad_source(db, plan_id, user["user_id"], kind)
        if not data: raise HTTPException(409, "Source CAO native non conservée : réimportez le DWG/DXF")
        units = (p.get("cad_import") or {}).get("units") or {}
        override = units.get("name") if units.get("source") == "user" and units.get("name") in UNIT_FACTORS else None
        parsed = await asyncio.to_thread(process_dxf, data, filename.rsplit(".", 1)[0]+".dxf", override)
        updated = parsed["pages"][0]
        old = p["pages"][0]
        if old.get("image_png_b64") != updated.get("image_png_b64"):
            raise HTTPException(409, "Le rendu CAO a évolué : réimportez le dessin pour recaler les mesures. Le plan existant est conservé.")
        prepared.append((0, updated, C.dims_from_dxf(updated["dxf_dimensions"])))
    else:
        src = await load_plan_source(db, plan_id, user["user_id"])
        if not src: raise HTTPException(409, "PDF source absent : réimportez le fichier")
        data = base64.b64decode(src["data_b64"])
        for pg in p["pages"]:
            if not pg.get("dpi"): continue
            updated = await asyncio.to_thread(extract_page_geometry, data, pg["index"], float(pg["dpi"])/72)
            prepared.append((pg["index"], updated, C.dims_from_pdf_vectors(updated["pdf_dimensions"])))
    # Validate all page associations before publishing any new geometry.
    for index, updated, dims in prepared:
        previous = (p.get("cotes_checks") or {}).get(str(index)) or {}
        unmatched = carry_user_edits(dims, previous.get("items") or [])
        if unmatched: raise HTTPException(409, f"Corrections conservées : cotes {unmatched} de la page {index+1} à rapprocher avant réextraction")
    out = []
    for index, updated, dims in prepared:
        values = {**{f"pages.$.{k}": v for k, v in updated.items()}, "updated_at": _now()}
        if p.get("kind") == "dxf":
            values.update(cad_import=parsed["cad_import"], structural_metre=parsed.get("structural_metre"))
        await db.plans_takeoff.update_one({**owner, "pages.index": index},
            {"$set": values, "$unset": {f"studies.{index}": "", f"cotes_checks.{index}.engine_version": "", f"cotes_checks.{index}.revision": ""}})
        walls = updated["walls_analysis"]
        out.append({"page_index": index, "source": p["kind"], "dimensions": len(dims),
                    "elements": len(updated.get("pdf_elements") or []), "auto_spans": len(updated.get("pdf_auto_spans") or []),
                    "walls": walls.get("stats"), "interior_complete": walls["validation"]["complete"]})
    return {"pages": out}


@router.post("/{plan_id}/cotes/narratif")
async def cotes_narratif(plan_id: str, body: GeometryIn, background: bool = Query(False),
                         user=Depends(current_user)) -> dict:
    """Passage 4 : rédaction du rapport narratif (une section par grande cote) — nécessite l'analyse géométrique."""
    from engines.plan_geometry_ai import analyze_geometry, write_narrative
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=True)
    lang = await _report_lang(user["user_id"])

    async def run():
        report = (p.get("cotes_checks") or {}).get(str(body.page_index))
        if not report or report.get("engine_version") != 2 or not report.get("revision"):
            report = await _run_check(p, page, plan_id, body.page_index, 2.0, 3.0, user["user_id"])
        geo = report.get("geometry")
        img = _ai_image(page["image_png_b64"])
        w, h = int(page.get("width_px") or 0), int(page.get("height_px") or 0)
        if geo and geo.get("stale"):
            geo = None  # cotes relues depuis : l'analyse géométrique doit être refaite avant la rédaction
        if not geo:
            geo = await analyze_geometry(img, report, w, h, lang)
            if geo.get("error"):
                raise HTTPException(502, geo["error"])
            geo["created_at"] = _now()
        nar = await write_narrative(img, report, geo, lang)
        if nar.get("error"):
            raise HTTPException(502, nar["error"])
        nar["created_at"] = _now()
        geo["narratif"] = nar
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id}, {"$set": {f"cotes_checks.{body.page_index}.geometry": geo, "updated_at": _now()}})
        await _snapshot(plan_id, user["user_id"], "cotes_narratif",
                        {"page": body.page_index, "sections": len(nar["sections"]), "lang": lang})
        return nar

    if background:
        return _start_job(run, user["user_id"])
    return await run()


@router.get("/{plan_id}/cotes/narratif.pdf")
async def cotes_narratif_pdf(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    from engines.plan_narrative_pdf import build_narrative_report
    p, page = await _plan_page(plan_id, user["user_id"], page_index, with_image=True)
    report = (p.get("cotes_checks") or {}).get(str(page_index))
    if not report or not (report.get("geometry") or {}).get("narratif"):
        raise HTTPException(404, "Rédigez d'abord le rapport narratif")
    branding = await _resolve_branding(user["user_id"])
    lang = (report["geometry"]["narratif"].get("lang") or _lang_of(branding))
    PDF_LANG.set(lang)
    pdf = build_narrative_report(p, page_index, report, page["image_png_b64"], branding, lang)
    fname = f"rapport-narratif-{plan_id[-6:]}-p{page_index + 1}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{plan_id}/cotes/narratif-all.pdf")
async def cotes_narratif_all_pdf(plan_id: str, user=Depends(current_user)):
    """Rapport narratif multi-pages : toutes les pages disposant d'un narratif, en un seul PDF brandé."""
    from engines.plan_narrative_pdf import build_narrative_report_multi
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                        {"_id": 0, "plan_id": 1, "filename": 1, "cotes_checks": 1, "pages.index": 1,
                                         "pages.image_png_b64": 1, "pages.level_label": 1, "detected_scale_denominator": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    bundle = []
    for pg in p.get("pages") or []:
        rep = (p.get("cotes_checks") or {}).get(str(pg["index"]))
        if rep and (rep.get("geometry") or {}).get("narratif") and pg.get("image_png_b64"):
            bundle.append((pg["index"], rep, pg["image_png_b64"]))
    if not bundle:
        raise HTTPException(404, "Aucune page avec rapport narratif : rédigez-le d'abord")
    branding = await _resolve_branding(user["user_id"])
    lang = bundle[0][1]["geometry"]["narratif"].get("lang") or _lang_of(branding)
    PDF_LANG.set(lang)
    pdf = build_narrative_report_multi(p, bundle, branding, lang)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="rapport-narratif-{plan_id[-6:]}-complet.pdf"'})


class StudiesIn(BaseModel):
    page_index: int = Field(default=0, ge=0)
    request: str = Field(default="", max_length=2000)
    effort: str = Field(default="high", pattern="^(high|max)$")


def _engine_json(report: dict) -> dict:
    """Calculs exacts ConstruPilot fournis au modèle (jamais recalculés par lui)."""
    keep = ("index", "indicated_m", "measured_m", "delta_cm", "status", "niveau", "orientation", "source", "anchor_mm", "anchor_status",
            "facade_status", "chain_status", "x1", "y1", "x2", "y2")
    return {"calibration": {k: (report.get("calibration") or {}).get(k) for k in ("method", "effective_scale_denominator", "scale_denominator")},
            "reading": {k: v for k, v in (report.get("reading") or {}).items() if k in ("source", "cross")},
            "cotes": [{k: it.get(k) for k in keep} for it in report.get("items") or [] if not it.get("ignored")],
            "chaines": report.get("chains") or [], "facades_opposees": report.get("facades") or [],
            "elements_dessines": report.get("elements") or [], "mesures_automatiques": report.get("auto_spans") or [],
            "murs_et_dimensions_interieures": {k: v for k, v in (report.get("interior") or {}).items() if k != "cotes"},
            "conclusion_rapide": (report.get("summary") or {}).get("conclusion"), "summary": report.get("summary")}


@router.post("/{plan_id}/studies/analyze")
async def studies_analyze(plan_id: str, body: StudiesIn, background: bool = Query(False), user=Depends(current_user)) -> dict:
    """Analyse OpenAI (GPT-6 Astra, 2 passes) du PDF original + calculs ConstruPilot → JSON structuré stocké."""
    import base64
    from engines.openai_studies import StudiesError, analyze_plan, check_quota, small_dimension_crops
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=True)
    from engines.plan_sources import load_plan_source
    src = await load_plan_source(db, plan_id, user["user_id"])
    if not src:
        raise HTTPException(409, "PDF original non conservé (plan importé avant cette version) : réimportez le fichier")
    if (p.get("page_count") or 1) > 20:
        raise HTTPException(413, "Document trop long (> 20 pages)")
    try:
        await check_quota(user["user_id"])
    except StudiesError as e:
        raise HTTPException(429, str(e))
    lang = await _report_lang(user["user_id"])
    proj = (await db.plans_takeoff.find_one({"plan_id": plan_id}, {"_id": 0, "project_id": 1}) or {}).get("project_id")

    async def run():
        report = (p.get("cotes_checks") or {}).get(str(body.page_index))
        if not report or report.get("engine_version") != 2 or not report.get("revision"):
            report = await _run_check(p, page, plan_id, body.page_index, 2.0, 3.0, user["user_id"])
        crops = small_dimension_crops(page["image_png_b64"], report.get("items") or [])
        from engines.openai_studies import zone_crops
        from engines.plan_refresh import refresh_interior
        walls_result = refresh_interior(page, report.get("items") or [], (report.get("calibration") or {}).get("pixels_per_meter"))
        crop_geometry = walls_result
        if walls_result and page.get("geometry_coordinate_space") == "image_px":
            crop_geometry = {**walls_result, "pt_per_m": walls_result.get("pt_per_m", 0) / (float(page["dpi"]) / 72)}
        zcrops = zone_crops(base64.b64decode(src["data_b64"]), body.page_index, crop_geometry, float(page["dpi"]) / 72) if walls_result else []
        req = body.request or ("Contrôle de cohérence des cotes, chaînes de cotes, alignements, épaisseurs de murs et éléments dessinés "
                               "de la page fournie, sans analyse structurelle.")
        try:
            study = await analyze_plan(user_id=user["user_id"], plan_id=plan_id, project_id=proj,
                                       pdf_bytes=base64.b64decode(src["data_b64"]), filename=src.get("filename") or p.get("filename") or "plan.pdf",
                                       page_index=body.page_index, request_text=req, engine_json=_engine_json(report), crops=crops,
                                       lang=lang, effort=body.effort, walls_result=walls_result, zone_crop_list=zcrops)
        except StudiesError as e:
            raise HTTPException(502, str(e))
        study["request"] = req
        study["report_revision"] = report["revision"]
        saved = await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"], f"cotes_checks.{body.page_index}.revision": report["revision"]},
            {"$set": {f"studies.{body.page_index}": study, "updated_at": _now()}})
        if not saved.matched_count:
            raise HTTPException(409, "Les cotes ont changé pendant l'analyse : relancez l'étude sur les valeurs actuelles")
        await _snapshot(plan_id, user["user_id"], "studies_analyze", {"page": body.page_index, "verified": study["verified"],
                                                                      "inconsistencies": len(study["analysis"].get("inconsistencies") or [])})
        return study

    if background:
        return _start_job(run, user["user_id"])
    return await run()


@router.get("/{plan_id}/studies")
async def studies_get(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "studies": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    return (p.get("studies") or {}).get(str(page_index)) or {}


@router.get("/{plan_id}/studies/report.pdf")
async def studies_pdf(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    from engines.studies_pdf import build_studies_report
    p, page = await _plan_page(plan_id, user["user_id"], page_index, with_image=True)
    full = await db.plans_takeoff.find_one({"plan_id": plan_id}, {"_id": 0, "studies": 1})
    study = ((full or {}).get("studies") or {}).get(str(page_index))
    if not study:
        raise HTTPException(404, "Lancez d'abord l'analyse OpenAI")
    report = (p.get("cotes_checks") or {}).get(str(page_index)) or {"items": [], "summary": {}}
    branding = await _resolve_branding(user["user_id"])
    lang = study.get("lang") or _lang_of(branding)
    PDF_LANG.set(lang)
    pdf = build_studies_report(p, page_index, study, report, page.get("image_png_b64"), branding, lang)
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="analyse-openai-{plan_id[-6:]}-p{page_index + 1}.pdf"'})


@router.get("/{plan_id}/cotes")
async def cotes_last(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)) -> dict:
    p, _ = await _plan_page(plan_id, user["user_id"], page_index, with_image=False)
    report = (p.get("cotes_checks") or {}).get(str(page_index))
    if not report:
        raise HTTPException(404, "Aucun contrôle des cotes pour cette page")
    return report


class CoteEditIn(BaseModel):
    page_index: int = Field(default=0, ge=0)
    indicated_m: float | None = Field(default=None, gt=0, le=500)
    ignored: bool | None = None


class RecomputeIn(BaseModel):
    page_index: int = Field(default=0, ge=0)
    tol_pct: float | None = Field(default=None, ge=0.1, le=20)
    tol_cm: float | None = Field(default=None, ge=0, le=100)


async def _recompute(p: dict, page: dict, plan_id: str, page_index: int, report: dict,
                     items: list[dict], tol_pct: float, tol_cm: float) -> dict:
    w, h = int(page.get("width_px") or 0), int(page.get("height_px") or 0)
    await _ensure_current_geometry(p, page, plan_id, page_index, report.get("user_id") or p.get("user_id", ""))
    ppm = float((report.get("calibration") or {}).get("pixels_per_meter") or 0)
    if not ppm:
        raise HTTPException(400, "Calibration du rapport manquante — relancez le contrôle")
    fresh = C.check_dimensions(C.items_to_dims(items), ppm, tol_pct, tol_cm, w, h,
                               elements=page.get("pdf_elements") or [], auto_spans=page.get("pdf_auto_spans") or [])
    ai_rooms = ((p.get("ai_analysis") or {}).get("rooms") or []) \
        if (p.get("ai_analysis") or {}).get("page_index") in (None, page_index) else []
    page_rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    if ai_rooms and page_rooms:
        fresh["surfaces"] = T.reconcile_written_surfaces(page_rooms, ai_rooms, ppm)
    fresh["interior"] = _interior_report(page, fresh["items"], ppm)
    new_report = {**report, **fresh, "engine_version": 2, "revision": uuid.uuid4().hex,
                  "calibration_stale": False, "recomputed_at": _now()}
    if report.get("geometry"):
        new_report["geometry"] = {**report["geometry"], "stale": True}
        if report["geometry"].get("narratif"):
            new_report["geometry"]["narratif"] = {**report["geometry"]["narratif"], "stale": True}
    saved = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": p.get("user_id"),
         f"cotes_checks.{page_index}.revision": report.get("revision")},
        {"$set": {f"cotes_checks.{page_index}": new_report, "updated_at": _now()},
         "$unset": {f"studies.{page_index}": ""}})
    if saved.matched_count == 0:
        raise HTTPException(409, "Les cotes ont changé pendant le recalcul — rechargez et réessayez")
    return new_report


@router.patch("/{plan_id}/cotes/items/{index}")
async def cotes_edit_item(plan_id: str, index: int, body: CoteEditIn, user=Depends(current_user)) -> dict:
    """Corrige la valeur inscrite d'une cote (mauvaise lecture) ou l'ignore, puis recalcule sans IA."""
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=False)
    report = (p.get("cotes_checks") or {}).get(str(body.page_index))
    if not report:
        raise HTTPException(404, "Lancez d'abord le contrôle des cotes")
    items = report.get("items") or []
    if index < 1 or index > len(items):
        raise HTTPException(404, "Cote inconnue")
    it = items[index - 1]
    if body.indicated_m is not None and abs(body.indicated_m - it["indicated_m"]) > 1e-9:
        if it.get("original_m") is None:
            it["original_m"] = it["indicated_m"]
        it["indicated_m"] = round(body.indicated_m, 3)
        it["edited"] = True
    if body.ignored is not None:
        it["ignored"] = body.ignored
    tol = report.get("tolerance") or {}
    new_report = await _recompute(p, page, plan_id, body.page_index, report, items,
                                  float(tol.get("pct", 2.0)), float(tol.get("cm", 3.0)))
    await _snapshot(plan_id, user["user_id"], "cotes_edit",
                    {"page": body.page_index, "index": index, "indicated_m": body.indicated_m,
                     "ignored": body.ignored})
    return new_report


@router.post("/{plan_id}/cotes/recompute")
async def cotes_recompute(plan_id: str, body: RecomputeIn, user=Depends(current_user)) -> dict:
    """Recalcule le rapport (nouvelle tolérance) à partir des cotes déjà lues — sans IA."""
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=False)
    report = (p.get("cotes_checks") or {}).get(str(body.page_index))
    if not report:
        raise HTTPException(404, "Lancez d'abord le contrôle des cotes")
    tol = report.get("tolerance") or {}
    return await _recompute(p, page, plan_id, body.page_index, report, report.get("items") or [],
                            body.tol_pct if body.tol_pct is not None else float(tol.get("pct", 2.0)),
                            body.tol_cm if body.tol_cm is not None else float(tol.get("cm", 3.0)))


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


@router.get("/{plan_id}/cotes/interior-overlay.png")
async def cotes_interior_overlay(plan_id: str, page_index: int = Query(0, ge=0), highlight: str = Query(""), user=Depends(current_user)):
    """Annexe graphique des mesures intérieures (plan SANS annotations de cotes) ; `highlight` = measurement_id à mettre en évidence."""
    from engines.plan_interior_overlay import render_interior_overlay
    p, page = await _plan_page(plan_id, user["user_id"], page_index, with_image=True)
    report = (p.get("cotes_checks") or {}).get(str(page_index)) or {}
    interior = report.get("interior") or _interior_report(page, report.get("items") or [])
    if not interior:
        raise HTTPException(404, "Aucun mur à deux faces établi sur cette page")
    return Response(content=render_interior_overlay(page["image_png_b64"], interior, highlight or None), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


def _EMAIL_PT(sm: dict, report: dict, fname: str, page_index: int, verdict: str, perso: str) -> str:
    return ((f"<p>{perso}</p>" if perso else "") +
            f"<p>Segue em anexo o <b>relatório de controlo de cotas</b> da planta « {fname} » "
            f"(página {page_index + 1}): cada cota inscrita foi medida à escala e comparada com o seu valor.</p>"
            f"<p><b>{sm['total']}</b> cotas controladas · <b>{sm['ok']}</b> conformes · <b>{sm['warn']}</b> a verificar · "
            f"<b>{sm['ko']}</b> incoerência(s) · {sm['chains_total']} cadeia(s) de cotas ({sm['chains_ko']} incoerente(s)) · "
            f"desvio máx. {sm['max_delta_cm']:.0f} cm — tolerância ±{report['tolerance']['pct']} % / {report['tolerance']['cm']} cm.</p>"
            f"<p>Veredicto: <b>{verdict}</b>. A planta anotada (cotas medidas em verde / laranja / vermelho) encontra-se na última página do PDF.</p>")


class CotesSendIn(BaseModel):
    page_index: int = Field(default=0, ge=0)
    to_email: EmailStr
    message: str = ""
    copy_me: bool = True


@router.post("/{plan_id}/cotes/send")
async def cotes_send(plan_id: str, body: CotesSendIn, user=Depends(current_user)) -> dict:
    """Envoie le rapport de contrôle des cotes (PDF) à l'architecte / au client."""
    import html as _html

    from engines.emailer import logo_url_for, send_email_with_pdf, wrap_company_html

    p, report, png = await _report_and_overlay(plan_id, user["user_id"], body.page_index)
    branding = await _resolve_branding(user["user_id"]) or {}
    lang = _lang_of(branding)
    PDF_LANG.set(lang)
    if report.get("geometry"):
        from engines.plan_report_pdf import build_control_report
        page = (p.get("pages") or [])[body.page_index]
        pdf = build_control_report(p, body.page_index, report, page["image_png_b64"], branding)
    else:
        pdf = build_cotes_pdf(p, body.page_index, report, png, branding)
    sm = report["summary"]
    company = branding.get("company_name") or user.get("name") or "ConstruPilot"
    perso = _html.escape(body.message.strip()[:2000]).replace("\n", "<br/>")
    verdict = tr({"ok": "aucune incohérence", "warn": "écarts à vérifier",
                  "ko": f"{sm['ko']} incohérence(s)"}[sm["verdict"]], lang)
    fname = _html.escape(p.get("filename") or "plan")
    inner = _EMAIL_PT(sm, report, fname, body.page_index, verdict, perso) if lang == "pt" else (
        (f"<p>{perso}</p>" if perso else "") +
        f"<p>Veuillez trouver ci-joint le <b>rapport de contrôle des cotes</b> du plan « {fname} » "
        f"(page {body.page_index + 1}) : chaque cote inscrite a été mesurée à l'échelle et comparée à sa valeur.</p>"
        f"<p><b>{sm['total']}</b> cotes contrôlées · <b>{sm['ok']}</b> conformes · <b>{sm['warn']}</b> à vérifier · "
        f"<b>{sm['ko']}</b> incohérence(s) · {sm['chains_total']} chaîne(s) de cotes ({sm['chains_ko']} incohérente(s)) · "
        f"écart max {sm['max_delta_cm']:.0f} cm — tolérance ±{report['tolerance']['pct']} % / {report['tolerance']['cm']} cm.</p>"
        f"<p>Verdict : <b>{verdict}</b>. Le plan annoté (cotes mesurées en vert / orange / rouge) figure en dernière page du PDF.</p>")
    geo = report.get("geometry")
    if geo and lang == "pt":
        inner += (f"<p><b>Análise geométrica ConstruPilot (dupla leitura)</b>: nível "
                  f"<b>{_html.escape(tr(geo.get('niveau_global_label') or geo.get('niveau_global') or '', 'pt'))}</b> — "
                  f"{len(geo.get('anomalies') or [])} anomalia(s), "
                  f"{(geo.get('double_lecture') or {}).get('confirmees', 0)} confirmada(s) na passagem 2. "
                  f"{_html.escape((geo.get('reponses') or {}).get('fermeture') or '')}</p>")
    elif geo:
        inner += (f"<p><b>Analyse géométrique ConstruPilot (double lecture)</b> : niveau "
                  f"<b>{_html.escape(geo.get('niveau_global_label') or geo.get('niveau_global') or '')}</b> — "
                  f"{len(geo.get('anomalies') or [])} anomalie(s), "
                  f"{(geo.get('double_lecture') or {}).get('confirmees', 0)} confirmée(s) au passage 2. "
                  f"{_html.escape((geo.get('reponses') or {}).get('fermeture') or '')}</p>")
    if sm.get("conclusion"):
        inner += f"<p><b>{'Conclusão rápida' if lang == 'pt' else 'Conclusion rapide'} :</b> {_html.escape(tr(sm['conclusion'], lang))}</p>"
    inner += f"<p style='color:#64748B;font-size:12px'>{disclaimer(p, body.page_index, report, branding, lang)}</p>"
    title = f"Relatório de controlo de cotas — {fname}" if lang == "pt" else f"Rapport de contrôle des cotes — {fname}"
    html = wrap_company_html(
        title, inner, company_name=company,
        logo_url=logo_url_for(user["user_id"], branding), logo_b64=branding.get("logo_b64"),
        contact_line=branding.get("contact_line"), siret=branding.get("siret"),
        vat=branding.get("vat"), nif=branding.get("nif"), alvara=branding.get("alvara"),
        company_email=branding.get("company_email"), verified=bool(branding.get("verified")))
    subject = f"{'Relatório de controlo de cotas' if lang == 'pt' else 'Rapport de contrôle des cotes'} — {p.get('filename') or 'plan'} ({verdict})"
    reply_to = branding.get("company_email") or user.get("email")
    try:
        await send_email_with_pdf(body.to_email, subject, html, pdf,
                                  filename=f"controle-cotes-p{body.page_index + 1}.pdf",
                                  reply_to=reply_to, from_name=company)
        if body.copy_me and user.get("email") and user["email"].lower() != body.to_email.lower():
            await send_email_with_pdf(user["email"], f"[{'Cópia' if lang == 'pt' else 'Copie'}] {subject}", html, pdf,
                                      filename=f"controle-cotes-p{body.page_index + 1}.pdf",
                                      reply_to=reply_to, from_name=company)
    except RuntimeError as e:
        raise HTTPException(503, str(e))
    except Exception:
        raise HTTPException(502, "Envoi de l'e-mail impossible — réessayez plus tard")
    entry = {"kind": "cotes", "to_email": body.to_email, "page_index": body.page_index,
             "sent_at": _now(), "verdict": sm["verdict"], "ko": sm["ko"], "total": sm["total"]}
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$push": {"sent_reports": {"$each": [entry], "$slice": -20}},
         "$set": {f"cotes_checks.{body.page_index}.last_sent": entry}})
    return {"ok": True, "sent_to": body.to_email, "copy_sent": body.copy_me, **entry}


@router.get("/{plan_id}/cotes/rapport.pdf")
async def cotes_rapport(plan_id: str, page_index: int = Query(0, ge=0), court: bool = Query(False),
                        user=Depends(current_user)):
    """Rapport de contrôle du plan ConstruPilot (couverture, résumé, calculs, plan annoté CP-xx, fiches, checklist)."""
    from engines.plan_report_pdf import build_control_report
    p, page = await _plan_page(plan_id, user["user_id"], page_index, with_image=True)
    report = (p.get("cotes_checks") or {}).get(str(page_index))
    if not report:
        raise HTTPException(404, "Lancez d'abord le contrôle des cotes")
    branding = await _resolve_branding(user["user_id"])
    PDF_LANG.set(_lang_of(branding))
    pdf = build_control_report(p, page_index, report, page["image_png_b64"], branding, court=court)
    fname = f"rapport-controle-plan{'-court' if court else ''}-{plan_id[-6:]}-p{page_index + 1}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{plan_id}/cotes/report.pdf")
async def cotes_pdf(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    p, report, png = await _report_and_overlay(plan_id, user["user_id"], page_index)
    branding = await _resolve_branding(user["user_id"])
    PDF_LANG.set(_lang_of(branding))
    ipng = None
    if report.get("interior"):
        from engines.plan_interior_overlay import render_interior_overlay
        _, page = await _plan_page(plan_id, user["user_id"], page_index, with_image=True)
        ipng = render_interior_overlay(page["image_png_b64"], report["interior"])
    pdf = build_cotes_pdf(p, page_index, report, png, branding, ipng)
    fname = f"controle-cotes-{plan_id}-p{page_index + 1}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})

