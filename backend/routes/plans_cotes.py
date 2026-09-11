"""Contrôle des cotes d'un plan : lecture (IA ou DXF) → mesure à l'échelle → rapport + PDF."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, EmailStr, Field

from core.db import db
from core.security import current_user
from engines import plan_cotes as C
from engines import plan_texts as T
from engines.plan_ai import read_dimension_lines
from engines.plan_cotes_pdf import build_cotes_pdf, build_cotes_pdf_multi, render_cotes_overlay
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


async def _run_check(p: dict, page: dict, plan_id: str, page_index: int,
                     tol_pct: float, tol_cm: float, user_id: str) -> dict:
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
        res = await read_dimension_lines(_ai_image(img))
        if res.get("error"):
            raise HTTPException(502, res["error"])
        dims = C.dims_from_ai(res["dimension_lines"], w, h)
        snapped = C.snap_dims_to_image(img, dims)
        reading = {"source": "ai", "count": len(dims), "scale_text": res.get("scale_text"),
                   "units_hint": res.get("units_hint"), "snapped_endpoints": snapped}
    if not dims:
        raise HTTPException(422, "Aucune cote lisible sur cette page")
    calib, auto = await _ensure_calibration(p, page, plan_id, page_index, dims, w, h)
    report = C.check_dimensions(dims, float(calib["pixels_per_meter"]), tol_pct, tol_cm, w, h)
    ai_rooms = ((p.get("ai_analysis") or {}).get("rooms") or []) \
        if (p.get("ai_analysis") or {}).get("page_index") in (None, page_index) else []
    page_rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    if ai_rooms and page_rooms:
        report["surfaces"] = T.reconcile_written_surfaces(page_rooms, ai_rooms, float(calib["pixels_per_meter"]))
    report.update({"page_index": page_index, "calibration": calib, "auto_calibrated": auto,
                   "reading": reading, "created_at": _now()})
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id}, {"$set": {f"cotes_checks.{page_index}": report, "updated_at": _now()}})
    await _snapshot(plan_id, user_id, "cotes_check", {"page": page_index, **report["summary"]})
    return report


_JOBS: dict[str, dict] = {}


def _start_job(coro_factory, user_id: str) -> dict:
    """Lance un traitement long en tâche de fond (évite le timeout 60 s de l'ingress) → {job_id}."""
    import asyncio
    import uuid
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    _JOBS[job_id] = {"status": "running", "user_id": user_id, "started_at": _now()}

    async def runner():
        try:
            _JOBS[job_id].update({"status": "done", "result": await coro_factory(), "finished_at": _now()})
        except HTTPException as e:
            _JOBS[job_id].update({"status": "error", "error": e.detail, "finished_at": _now()})
        except Exception as e:  # noqa: BLE001
            _JOBS[job_id].update({"status": "error", "error": f"{type(e).__name__}: {e}"[:300], "finished_at": _now()})
        for k in [k for k, v in _JOBS.items() if v.get("finished_at") and len(_JOBS) > 200]:
            _JOBS.pop(k, None)

    asyncio.create_task(runner())
    return {"job_id": job_id, "status": "running"}


@router.get("/cotes-jobs/{job_id}")
async def cotes_job(job_id: str, user=Depends(current_user)) -> dict:
    j = _JOBS.get(job_id)
    if not j or j["user_id"] != user["user_id"]:
        raise HTTPException(404, "Tâche inconnue")
    return {k: v for k, v in j.items() if k != "user_id"}


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


@router.post("/{plan_id}/cotes/geometry")
async def cotes_geometry(plan_id: str, body: GeometryIn, background: bool = Query(False),
                         user=Depends(current_user)) -> dict:
    """Analyse géométrique complète (double lecture IA) : fermetures, contrôles croisés, façades, anomalies."""
    from engines.plan_geometry_ai import analyze_geometry
    p, page = await _plan_page(plan_id, user["user_id"], body.page_index, with_image=True)

    async def run():
        report = (p.get("cotes_checks") or {}).get(str(body.page_index))
        if not report:
            report = await _run_check(p, page, plan_id, body.page_index, 2.0, 3.0, user["user_id"])
        geo = await analyze_geometry(_ai_image(page["image_png_b64"]), report,
                                     int(page.get("width_px") or 0), int(page.get("height_px") or 0))
        if geo.get("error"):
            raise HTTPException(502, geo["error"])
        geo["created_at"] = _now()
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id}, {"$set": {f"cotes_checks.{body.page_index}.geometry": geo, "updated_at": _now()}})
        await _snapshot(plan_id, user["user_id"], "cotes_geometry",
                        {"page": body.page_index, "niveau": geo["niveau_global"], "anomalies": len(geo["anomalies"])})
        return geo

    if background:
        return _start_job(run, user["user_id"])
    return await run()


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
    ppm = float((report.get("calibration") or {}).get("pixels_per_meter") or 0)
    if not ppm:
        raise HTTPException(400, "Calibration du rapport manquante — relancez le contrôle")
    fresh = C.check_dimensions(C.items_to_dims(items), ppm, tol_pct, tol_cm, w, h)
    ai_rooms = ((p.get("ai_analysis") or {}).get("rooms") or []) \
        if (p.get("ai_analysis") or {}).get("page_index") in (None, page_index) else []
    page_rooms = [r for r in (p.get("rooms") or []) if r.get("page_index") == page_index]
    if ai_rooms and page_rooms:
        fresh["surfaces"] = T.reconcile_written_surfaces(page_rooms, ai_rooms, ppm)
    new_report = {**report, **fresh, "recomputed_at": _now()}
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id}, {"$set": {f"cotes_checks.{page_index}": new_report, "updated_at": _now()}})
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
    if report.get("geometry"):
        from engines.plan_report_pdf import build_control_report
        page = (p.get("pages") or [])[body.page_index]
        pdf = build_control_report(p, body.page_index, report, page["image_png_b64"], branding)
    else:
        pdf = build_cotes_pdf(p, body.page_index, report, png, branding)
    sm = report["summary"]
    company = branding.get("company_name") or user.get("name") or "ConstruPilot"
    perso = _html.escape(body.message.strip()[:2000]).replace("\n", "<br/>")
    verdict = {"ok": "aucune incohérence", "warn": "écarts à vérifier",
               "ko": f"{sm['ko']} incohérence(s)"}[sm["verdict"]]
    fname = _html.escape(p.get("filename") or "plan")
    inner = (
        (f"<p>{perso}</p>" if perso else "") +
        f"<p>Veuillez trouver ci-joint le <b>rapport de contrôle des cotes</b> du plan « {fname} » "
        f"(page {body.page_index + 1}) : chaque cote inscrite a été mesurée à l'échelle et comparée à sa valeur.</p>"
        f"<p><b>{sm['total']}</b> cotes contrôlées · <b>{sm['ok']}</b> conformes · <b>{sm['warn']}</b> à vérifier · "
        f"<b>{sm['ko']}</b> incohérence(s) · {sm['chains_total']} chaîne(s) de cotes ({sm['chains_ko']} incohérente(s)) · "
        f"écart max {sm['max_delta_cm']:.0f} cm — tolérance ±{report['tolerance']['pct']} % / {report['tolerance']['cm']} cm.</p>"
        f"<p>Verdict : <b>{verdict}</b>. Le plan annoté (cotes mesurées en vert / orange / rouge) figure en dernière page du PDF.</p>")
    geo = report.get("geometry")
    if geo:
        inner += (f"<p><b>Analyse géométrique ConstruPilot (double lecture)</b> : niveau "
                  f"<b>{_html.escape(geo.get('niveau_global_label') or geo.get('niveau_global') or '')}</b> — "
                  f"{len(geo.get('anomalies') or [])} anomalie(s), "
                  f"{(geo.get('double_lecture') or {}).get('confirmees', 0)} confirmée(s) au passage 2. "
                  f"{_html.escape((geo.get('reponses') or {}).get('fermeture') or '')}</p>")
    html = wrap_company_html(
        f"Rapport de contrôle des cotes — {fname}", inner, company_name=company,
        logo_url=logo_url_for(user["user_id"], branding), logo_b64=branding.get("logo_b64"),
        contact_line=branding.get("contact_line"), siret=branding.get("siret"),
        vat=branding.get("vat"), nif=branding.get("nif"), alvara=branding.get("alvara"),
        company_email=branding.get("company_email"), verified=bool(branding.get("verified")))
    subject = f"Rapport de contrôle des cotes — {p.get('filename') or 'plan'} ({verdict})"
    reply_to = branding.get("company_email") or user.get("email")
    try:
        await send_email_with_pdf(body.to_email, subject, html, pdf,
                                  filename=f"controle-cotes-p{body.page_index + 1}.pdf",
                                  reply_to=reply_to, from_name=company)
        if body.copy_me and user.get("email") and user["email"].lower() != body.to_email.lower():
            await send_email_with_pdf(user["email"], f"[Copie] {subject}", html, pdf,
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
    pdf = build_control_report(p, page_index, report, page["image_png_b64"], branding, court=court)
    fname = f"rapport-controle-plan{'-court' if court else ''}-{plan_id[-6:]}-p{page_index + 1}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})


@router.get("/{plan_id}/cotes/report.pdf")
async def cotes_pdf(plan_id: str, page_index: int = Query(0, ge=0), user=Depends(current_user)):
    p, report, png = await _report_and_overlay(plan_id, user["user_id"], page_index)
    branding = await _resolve_branding(user["user_id"])
    pdf = build_cotes_pdf(p, page_index, report, png, branding)
    fname = f"controle-cotes-{plan_id}-p{page_index + 1}.pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{fname}"'})
