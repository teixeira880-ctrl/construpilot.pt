"""CRUD & calibration routes du module plans (upload, list, get, delete,
calibrate, plan defaults, page level).

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Literal

from fastapi import Request, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from core.uploads import (
    validate_upload, ALLOWED_IMAGE, ALLOWED_DOCUMENT, ALLOWED_CAD,
)
from engines import geometry as G
from engines.plan_sources import save_plan_source, save_cad_source, delete_plan_sources, copy_plan_sources, image_plan_pdf
from engines.plan_processor import process_upload

from routes.plans_common import (
    ALLOWED_MIMES, MAX_UPLOAD_MB, _now, _plan_summary, _snapshot, _apply_new_calibration, router,
)

logger = logging.getLogger(__name__)


# ============ UPLOAD ============

async def _process_and_store(data: bytes, filename: str, content_type: str, user: dict, project_id: str | None,
                             deskew: bool, cad_unit: str | None, display_name: str | None = None) -> dict:
    """Traitement complet (conversion DWG, lecture, calibration, stockage). Peut dépasser 2 min : exécuté en tâche de fond."""
    file = type("F", (), {"filename": filename, "content_type": content_type})()
    original_data = data
    mime = (file.content_type or "").lower()
    lower_name = (file.filename or "").lower()
    is_cad = lower_name.endswith((".dxf", ".dwg"))
    if mime and mime not in ALLOWED_MIMES and not is_cad:
        if mime != "application/octet-stream":
            raise HTTPException(415, f'Formato não suportado: {mime}')

    conversion = {}
    # DWG → DXF through the configured provider; the analysis pipeline is unchanged.
    if lower_name.endswith(".dwg"):
        from engines.dwg_convert import dwg_to_dxf
        try:
            from core.permissions import require_feature
            require_feature(user, "dashboard")
            data = await dwg_to_dxf(data, file.filename or "plan.dwg", user_id=user["user_id"], provenance=conversion)
        except HTTPException:
            raise
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        except Exception:
            logger.exception("DWG conversion failed")
            raise HTTPException(502, "Conversão DWG impossível — tente mais tarde.")
        parse_name = (file.filename or "plan")[:-4] + ".dxf"
        mime = "image/vnd.dxf"
    else:
        parse_name = file.filename or "plan"

    try:
        parsed = await asyncio.to_thread(process_upload, data, parse_name, mime, deskew, cad_unit)
    except Exception as e:
        logger.exception("plan process failed")
        raise HTTPException(422, f'Impossível ler o ficheiro: {e}')

    if conversion:
        parsed.setdefault("cad_import", {})["conversion"] = conversion
        for page in parsed.get("pages", []):
            page.setdefault("cad_import", {})["conversion"] = conversion

    plan_id = "plan_" + secrets.token_hex(6)
    calibrations = _auto_calibrate_pages(parsed)

    doc = {
        "plan_id": plan_id,
        "user_id": user["user_id"],
        "project_id": project_id,
        "filename": (display_name.strip()[:120] if (display_name and display_name.strip()) else file.filename),
        "size_bytes": len(original_data),
        "kind": parsed["kind"],
        "page_count": parsed["page_count"],
        "detected_scale_denominator": parsed.get("detected_scale_denominator"),
        "structural_metre": parsed.get("structural_metre"),
        "cad_import": parsed.get("cad_import"),
        "pages": parsed["pages"],
        "calibrations": calibrations,
        "rooms": [],
        "measurements": [],
        "ai_analysis": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await _insert_plan_safe(doc)
    try:
        import base64
        import hashlib
        if parsed["kind"] == "pdf":
            await save_plan_source(db, plan_id, user["user_id"], data, mime="application/pdf",
                                   filename=file.filename, source_kind="original_pdf", created_at=_now())
        elif parsed["kind"] == "dxf":
            await save_plan_source(db, plan_id, user["user_id"], base64.b64decode(parsed["analysis_pdf_b64"]),
                                   mime="application/pdf", filename=parse_name.rsplit(".", 1)[0]+".pdf", source_kind="cad_render",
                                   original_filename=file.filename, original_sha256=hashlib.sha256(original_data).hexdigest(), created_at=_now())
            await save_cad_source(db, plan_id, user["user_id"], "original", original_data)
            if lower_name.endswith(".dwg"):
                await save_cad_source(db, plan_id, user["user_id"], "converted_dxf", data)
        elif parsed["kind"] == "image":
            pdf = await asyncio.to_thread(image_plan_pdf, parsed["pages"][0])
            await save_plan_source(db, plan_id, user["user_id"], pdf, mime="application/pdf",
                                   filename=parse_name.rsplit(".", 1)[0]+".pdf", source_kind="normalized_image",
                                   original_filename=file.filename, original_sha256=hashlib.sha256(original_data).hexdigest(), created_at=_now())
            await save_cad_source(db, plan_id, user["user_id"], "original", original_data)
    except BaseException as exc:
        await db.plans_takeoff.delete_one({"plan_id": plan_id, "user_id": user["user_id"]})
        await delete_plan_sources(db, plan_id, user["user_id"])
        if isinstance(exc, asyncio.CancelledError): raise
        raise HTTPException(503, "Importação não guardada na totalidade. Tente importar novamente.") from None
    return doc


@router.post("/upload")
async def upload_plan(
    request: Request,
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    deskew: bool = Form(False),
    cad_unit: Literal["mm", "cm", "m", "inches", "feet"] | None = Form(None),
    wait: bool = Form(False),
    display_name: str | None = Form(None),
    user=Depends(current_user),
):
    """Par défaut synchrone (API publique, scripts, tests). Avec l'en-tête `X-Async-Upload: 1` (front) : validation
    immédiate puis traitement en tâche de fond (le proxy coupe à 120 s) et 202 {job_id} à suivre sur /upload-jobs/{job_id}."""
    lower_name = (file.filename or "").lower()
    # CAD via extensão: browsers enviam DWG/DXF/IFC como octet-stream.
    # Passamos override_content_type para forçar o branch magic-bytes em validate_upload
    # sem escrever em file.content_type (read-only em Starlette ≥0.37).
    override_ct = None
    if lower_name.endswith((".dxf", ".dwg", ".ifc")):
        override_ct = "application/octet-stream"
    file = await validate_upload(
        file,
        ALLOWED_IMAGE + ALLOWED_DOCUMENT + ALLOWED_CAD,
        max_mb=MAX_UPLOAD_MB,
        override_content_type=override_ct,
    )
    data = await file.read(MAX_UPLOAD_MB * 1024 * 1024 + 1)
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f'Ficheiro demasiado volumoso (>{MAX_UPLOAD_MB} MB)')
    if not data: raise HTTPException(422, "Ficheiro vazio")
    if project_id and not await db.projects.find_one({"project_id": project_id, "user_id": user["user_id"]}, {"_id": 1}):
        raise HTTPException(403, "Obra inacessível para esta conta")
    mime = (file.content_type or "").lower()
    if mime and mime not in ALLOWED_MIMES and not lower_name.endswith((".dxf", ".dwg")) and mime != "application/octet-stream":
        raise HTTPException(415, f'Formato não suportado: {mime}')
    if wait or request.headers.get("x-async-upload") != "1":
        return _plan_summary(await _process_and_store(data, file.filename or "plan", mime, user, project_id, deskew, cad_unit, display_name))
    job_id = "pjob_" + secrets.token_hex(6)
    await db.plan_upload_jobs.insert_one({"job_id": job_id, "user_id": user["user_id"], "filename": display_name or file.filename, "size_bytes": len(data),
                                          "status": "processing", "created_at": _now(), "updated_at": _now()})
    asyncio.create_task(_run_upload_job(job_id, data, file.filename or "plan", mime, user, project_id, deskew, cad_unit, display_name))
    from fastapi.responses import JSONResponse
    return JSONResponse({"job_id": job_id, "status": "processing"}, status_code=202)


async def _run_upload_job(job_id, data, filename, mime, user, project_id, deskew, cad_unit, display_name=None):
    try:
        doc = await _process_and_store(data, filename, mime, user, project_id, deskew, cad_unit, display_name)
        await db.plan_upload_jobs.update_one({"job_id": job_id}, {"$set": {"status": "done", "plan_id": doc["plan_id"], "updated_at": _now()}})
    except HTTPException as e:
        await db.plan_upload_jobs.update_one({"job_id": job_id}, {"$set": {"status": "error", "status_code": e.status_code, "detail": e.detail, "updated_at": _now()}})
    except Exception as e:  # noqa: BLE001
        logger.exception("plan upload job failed")
        await db.plan_upload_jobs.update_one({"job_id": job_id}, {"$set": {"status": "error", "status_code": 500, "detail": f"Import impossible : {type(e).__name__}", "updated_at": _now()}})


@router.get("/upload-jobs/{job_id}")
async def upload_job(job_id: str, user=Depends(current_user)):
    j = await db.plan_upload_jobs.find_one({"job_id": job_id, "user_id": user["user_id"]}, {"_id": 0})
    if not j:
        raise HTTPException(404, "Importação não encontrada")
    if j["status"] == "done" and j.get("kind") is None:
        p = await db.plans_takeoff.find_one({"plan_id": j["plan_id"], "user_id": user["user_id"]}, {"_id": 0})
        j["plan"] = _plan_summary(p) if p else None
    return j


# ============ MÉTRÉ STRUCTURE (DWG/DXF) ============

@router.get("/{plan_id}/structural-metre")
async def get_structural_metre(plan_id: str, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structural_metre": 1, "structural_estimate": 1, "kind": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    return {"metre": p.get("structural_metre"),
            "estimate": p.get("structural_estimate"),
            "kind": p.get("kind")}


class StructuralEstimateIn(BaseModel):
    storey_height_m: float = 2.70
    n_levels: int = 1
    # None → utilise la valeur auto-détectée sur le plan, sinon le défaut moteur
    wall_thickness_m: float | None = None
    beam_w_m: float | None = None
    beam_h_m: float | None = None
    col_w_m: float | None = None
    col_h_m: float | None = None
    slab_thickness_m: float | None = None
    slab_area_m2: float | None = None
    margin_pct: float = 12.0
    partitions_as_concrete: bool = True
    arase_inf_m: float | None = None
    arase_sup_m: float | None = None


@router.post("/{plan_id}/structural-estimate")
async def compute_structural_estimate(plan_id: str, body: StructuralEstimateIn,
                                       user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structural_metre": 1, "calibrations": 1,
         "pages.dxf_ratio": 1, "pages.index": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    metre = p.get("structural_metre")
    if not metre:
        raise HTTPException(400, "Nenhuma medição de estrutura disponível (planta não DWG/DXF ou sem camadas utilizáveis)")
    # Recale le métré sur la calibration du plan (corrige toute échelle DWG erronée).
    metre, scale_src = _rescale_metre_to_calibration(metre, p)
    from engines.dxf_takeoff import cost_structural
    estimate = cost_structural(metre, body.dict())
    estimate["scale_source"] = scale_src
    estimate["metre"] = metre
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {"structural_estimate": estimate, "updated_at": _now()}})
    return estimate


@router.post("/{plan_id}/metre-to-quote")
async def structural_metre_to_quote(plan_id: str, body: StructuralEstimateIn,
                                    user=Depends(current_user)) -> dict:
    """Transforme le métré structure (DWG/DXF) en devis client éditable.

    Recalcule l'estimation avec les hypothèses fournies, intègre la marge dans les
    prix unitaires (invisible pour le client), applique la TVA, puis crée un
    document `quote` en base et renvoie son doc_id (édition via /devis-editeur/{id})."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structural_metre": 1, "calibrations": 1, "filename": 1,
         "pages.dxf_ratio": 1, "pages.index": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    metre = p.get("structural_metre")
    if not metre:
        raise HTTPException(400, "Nenhuma medição de estrutura disponível (planta não DWG/DXF ou sem camadas utilizáveis)")
    metre, _scale_src = _rescale_metre_to_calibration(metre, p)
    from engines.dxf_takeoff import cost_structural
    estimate = cost_structural(metre, body.dict())
    margin = float(estimate["params"].get("margin_pct", 0)) / 100.0
    vat_rate = round(float(estimate["totals"].get("tva_rate", 0.23)) * 100.0, 2)

    lines: list[dict] = []
    for lot in estimate.get("lots", []):
        for ln in lot.get("lines", []):
            pu = round(float(ln.get("pu", 0)) * (1 + margin), 2)
            lines.append({
                "designation": ln.get("designation", ""),
                "description": ln.get("detail", ""),
                "unit": ln.get("unit", "u"),
                "qty": round(float(ln.get("qty", 0)), 2),
                "unit_price_ht": pu,
                "vat_rate": vat_rate,
                "category": lot.get("lot", ""),
            })
    if not lines:
        raise HTTPException(422, "A medição não contém nenhuma linha a orçamentar.")

    from routes.documents import _compute_totals
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "quote",
        "number": None,
        "title": f"Orçamento de estrutura — {p.get('filename') or 'plan'}",
        "client_id": None,
        "client": None,
        "status": "draft",
        "lines": lines,
        "notes": "Orçamento gerado a partir da medição de estrutura (DWG/DXF).",
        "payment_terms": "",
        "deposit_pct": 0,
        "totals": _compute_totals(lines, 0),
        "issue_date": None,
        "due_date": None,
        "source": "structural_metre",
        "plan_id": plan_id,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await db.pro_documents.insert_one(dict(doc))
    doc.pop("_id", None)
    return {"ok": True, "doc_id": doc["doc_id"], "totals": doc["totals"],
            "line_count": len(lines)}


class LinkFerraillageIn(BaseModel):
    ferraillage_plan_ids: list[str] = Field(default_factory=list, max_length=30)


@router.patch("/{plan_id}/link-ferraillage")
async def link_ferraillage(plan_id: str, body: LinkFerraillageIn,
                           user=Depends(current_user)) -> dict:
    """Rattache des plans de ferraillage à un plan de coffrage (gros œuvre).
    Les aciers de ces plans seront chiffrés conjointement dans le devis consolidé."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "plan_id": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    valid = await db.plans_takeoff.find(
        {"plan_id": {"$in": body.ferraillage_plan_ids}, "user_id": user["user_id"]},
        {"_id": 0, "plan_id": 1}).to_list(30)
    valid_ids = [v["plan_id"] for v in valid if v["plan_id"] != plan_id]
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"ferraillage_plan_ids": valid_ids, "updated_at": _now()}})
    return {"ok": True, "plan_id": plan_id, "ferraillage_plan_ids": valid_ids}


def _rescale_metre_to_calibration(metre: dict, p: dict):
    """Aligne le métré sur l'échelle réelle du plan : unit_to_m = dxf_ratio / pixels_per_meter.
    Corrige les métadonnées d'unité DWG erronées dès que l'utilisateur (re)calibre le plan."""
    pages = p.get("pages") or []
    ratio = pages[0].get("dxf_ratio") if pages else None
    ppm = ((p.get("calibrations") or {}).get("0") or {}).get("pixels_per_meter")
    old_u = metre.get("unit_to_m") or 0
    if not (ratio and ppm and old_u):
        return metre, "metre_units"
    new_u = ratio / ppm
    f = new_u / old_u
    if abs(f - 1.0) < 0.02:
        return metre, "calibration(=auto)"
    m = dict(metre)
    for k in ("walls_ml", "partitions_ml", "beams_ml", "linteaux_ml"):
        if m.get(k):
            m[k] = round(m[k] * f, 1)
    if m.get("slab_area_m2"):
        m["slab_area_m2"] = round(m["slab_area_m2"] * f * f, 1)
    if m.get("col_area_m2"):
        m["col_area_m2"] = round(m["col_area_m2"] * f * f, 3)
    for k in ("wall_area_m2", "partition_area_m2", "beam_area_m2"):
        if m.get(k):
            m[k] = round(m[k] * f * f, 2)
    det = dict(m.get("detected") or {})
    for k in ("wall_thickness_m", "beam_w_m", "col_size_m"):
        if det.get(k):
            det[k] = round(det[k] * f, 3)
    if det.get("col_area_m2"):
        det["col_area_m2"] = round(det["col_area_m2"] * f * f, 3)
    for k in ("wall_area_m2", "partition_area_m2", "beam_area_m2"):
        if det.get(k):
            det[k] = round(det[k] * f * f, 2)
    if det.get("col_sections"):
        det["col_sections"] = [{"w_cm": round(s["w_cm"] * f), "h_cm": round(s["h_cm"] * f)}
                               for s in det["col_sections"]]
    m["detected"] = det
    m["unit_to_m"] = new_u
    return m, "calibration"



def _bson_size_mb(doc: dict) -> float:
    import bson
    return len(bson.BSON.encode(doc)) / 1024 / 1024


async def _insert_plan_safe(doc: dict) -> None:
    """Insère le plan en garantissant de rester sous la limite BSON de 16 Mo.
    Si le document est trop lourd (PDF multi-pages avec beaucoup d'images), on
    dégrade progressivement : d'abord les vecteurs, puis les textes.
    """
    if _bson_size_mb(doc) > 15:
        for pg in doc.get("pages", []):
            pg["vectors"] = []
        logger.warning("plan %s: vecteurs supprimés pour tenir sous 16 Mo", doc.get("plan_id"))
    if _bson_size_mb(doc) > 15:
        for pg in doc.get("pages", []):
            pg["text_blocks"] = []
    if _bson_size_mb(doc) > 15:
        raise HTTPException(
            413,
            "Planta demasiado volumosa para guardar (demasiadas páginas ou imagens muito pesadas). Tente importar apenas as páginas úteis ou uma planta com menor resolução.",
        )
    await db.plans_takeoff.insert_one(doc)


_UNITS_PER_METER = {
    "mm": 1000.0, "cm": 100.0, "m": 1.0, "decimeters": 10.0,
    "dekameters": 0.1, "inches": 39.3701, "feet": 3.28084, "microns": 1_000_000.0,
}


def _dxf_span_units(pg: dict) -> float:
    b = pg.get("dxf_bounds") or {}
    return max(float(b.get("max_x", 0)) - float(b.get("min_x", 0)),
               float(b.get("max_y", 0)) - float(b.get("min_y", 0)))


def _guess_units_per_meter(pg: dict) -> tuple[float, str]:
    """Devine l'unité DXF depuis l'étendue réelle du dessin quand $INSUNITS est absent
    ou incohérent. Un bâtiment fait typiquement 3–60 m dans sa plus grande dimension."""
    span = _dxf_span_units(pg)
    if span > 3000:      # 3000–60000 → millimètres (3–60 m)
        return 1000.0, "mm"
    if span > 300:       # 300–6000 → centimètres (3–60 m)
        return 100.0, "cm"
    return 1.0, "m"      # 3–60 → mètres


def _auto_calibrate_dxf(parsed: dict) -> dict:
    """L'unité déclarée ou choisie est la référence, quelle que soit l'emprise."""
    result={}
    for page in parsed["pages"]:
        ratio,unit=page.get("dxf_ratio"),page.get("unit_to_m")
        if not ratio or not unit or unit<=0:continue
        ppm=ratio/unit
        result[str(page["index"])]={"pixels_per_meter":ppm,"meters_per_pixel":1/ppm,
                                    "method":"auto_dxf_units","confidence":.99,"dxf_units":parsed.get("dxf_units"),
                                    "created_at":_now()}
    return result


def _auto_calibrate_pages(parsed: dict) -> dict:
    """Try to derive an initial pixels_per_meter per page from the detected scale."""
    if parsed.get("kind") == "dxf":
        return _auto_calibrate_dxf(parsed)
    from engines.plan_page_context import initial_pdf_calibrations
    return initial_pdf_calibrations(parsed, _now())



# ============ LIST / GET / DELETE ============

@router.get("")
async def list_plans(user=Depends(current_user)) -> dict:
    docs = await db.plans_takeoff.find(
        {"user_id": user["user_id"], "trashed_at": {"$exists": False}},
        {"_id": 0, "pages.image_png_b64": 0}
    ).sort("created_at", -1).to_list(100)
    return {"plans": docs}


@router.get("/{plan_id}")
async def get_plan(plan_id: str, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    return _plan_summary(p)


@router.get("/{plan_id}/page/{page_index}")
async def get_plan_page(plan_id: str, page_index: int, user=Depends(current_user)):
    """Renvoie l'image PNG (base64) + vecteurs de la page demandée."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1}
    )
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Página desconhecida")
    return pages[page_index]


@router.get("/{plan_id}/thumb")
async def plan_thumbnail(plan_id: str, user=Depends(current_user)):
    """Vignette JPEG (~240 px) de la page 1 du plan — mise en cache sur le plan."""
    import base64
    from io import BytesIO
    from fastapi.responses import Response
    cached = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "thumb_b64": 1})
    if cached is None:
        raise HTTPException(404, "Planta não encontrada")
    b64 = cached.get("thumb_b64")
    if not b64:
        doc = await db.plans_takeoff.find_one(
            {"plan_id": plan_id, "user_id": user["user_id"]},
            {"_id": 0, "pages": {"$slice": 1}})
        pages = (doc or {}).get("pages") or []
        img_b64 = pages[0].get("image_png_b64") if pages else None
        if not img_b64:
            raise HTTPException(404, "Pré-visualização indisponível")
        try:
            from PIL import Image
            im = Image.open(BytesIO(base64.b64decode(img_b64))).convert("RGB")
            im.thumbnail((240, 240))
            out = BytesIO()
            im.save(out, format="JPEG", quality=70)
            b64 = base64.b64encode(out.getvalue()).decode()
        except Exception:
            raise HTTPException(404, "Pré-visualização indisponível")
        await db.plans_takeoff.update_one(
            {"plan_id": plan_id, "user_id": user["user_id"]}, {"$set": {"thumb_b64": b64}})
    return Response(content=base64.b64decode(b64), media_type="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


class BulkTrashIn(BaseModel):
    plan_ids: list[str] = Field(default_factory=list)
    all: bool = False


@router.post("/bulk-trash")
async def bulk_trash_plans(body: BulkTrashIn, user=Depends(current_user)) -> dict:
    """Met plusieurs plans (ou tous) à la corbeille d'un seul coup (récupérables 30 jours)."""
    from routes.trash import trash_record
    q = {"user_id": user["user_id"], "trashed_at": {"$exists": False}}
    if not body.all:
        if not body.plan_ids:
            raise HTTPException(400, "Nenhuma planta selecionada")
        q["plan_id"] = {"$in": body.plan_ids}
    plans = await db.plans_takeoff.find(
        q, {"_id": 0, "pages": 0, "rooms": 0, "measurements": 0}
    ).to_list(2000)
    count = 0
    for p in plans:
        await trash_record("plan", p, user["user_id"])
        count += 1
    return {"ok": True, "trashed": count}


@router.delete("/{plan_id}")
async def delete_plan(plan_id: str, user=Depends(current_user)) -> dict:
    plan = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages": 0, "rooms": 0, "measurements": 0})
    if not plan:
        raise HTTPException(404, "Planta não encontrada")
    from routes.trash import trash_record
    return await trash_record("plan", plan, user["user_id"])


def _duplicate_filename(name: str) -> str:
    """Ajoute un suffixe '(copie)' avant l'extension, ou '(copie N)' si déjà présent."""
    base = name or "plan"
    dot = base.rfind(".")
    stem, ext = (base[:dot], base[dot:]) if dot > 0 else (base, "")
    if "(copie" in stem:
        return f"{stem.rsplit('(copie', 1)[0].rstrip()} (copie 2){ext}"
    return f"{stem} (copie){ext}"


@router.post("/{plan_id}/duplicate")
async def duplicate_plan(plan_id: str, user=Depends(current_user)) -> dict:
    """Clone un plan (pages, rooms, ouvertures, calibrations, defaults) sous un
    nouveau plan_id. Utile pour tester des variantes (finitions, cloisons différentes).

    Ne copie PAS : les rendus 3D, les vidéos, les snapshots d'historique — le duplicata
    démarre propre. Le fichier PDF/image d'origine (pages avec image_png_b64) est bien
    conservé pour que le duplicata soit exploitable sans réimport.
    """
    # Accès Plan ouvert à tous les utilisateurs connectés (rendus 3D payants à l'unité)
    src = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0}
    )
    if not src:
        raise HTTPException(404, "Planta não encontrada")

    new_id = "plan_" + secrets.token_hex(6)
    dup = {
        "plan_id": new_id,
        "user_id": user["user_id"],
        "project_id": src.get("project_id"),
        "filename": _duplicate_filename(src.get("filename") or "plan"),
        "size_bytes": src.get("size_bytes"),
        "kind": src.get("kind"),
        "page_count": src.get("page_count"),
        "detected_scale_denominator": src.get("detected_scale_denominator"),
        "pages": src.get("pages") or [],
        "calibrations": dict(src.get("calibrations") or {}),
        "rooms": [dict(r) for r in (src.get("rooms") or [])],
        "measurements": list(src.get("measurements") or []),
        "ai_analysis": src.get("ai_analysis"),
        "plan_defaults": src.get("plan_defaults"),
        "walls_detected": src.get("walls_detected"),
        "created_at": _now(),
        "updated_at": _now(),
        "duplicated_from": plan_id,
        "cad_import": src.get("cad_import"),
        "structural_metre": src.get("structural_metre"),
    }
    try:
        await copy_plan_sources(db, plan_id, new_id, user["user_id"])
        await _insert_plan_safe(dup)
    except BaseException:
        await delete_plan_sources(db, new_id, user["user_id"])
        raise
    return {"ok": True, "plan_id": new_id, "duplicated_from": plan_id,
            "filename": dup["filename"], "rooms": len(dup["rooms"])}


# ============ CALIBRATION ============

class CalibIn(BaseModel):
    page_index: int
    p1: tuple[float, float]
    p2: tuple[float, float]
    real_distance_m: float = Field(gt=0, le=10000)
    method: Literal["two_points", "known_dimension"] = "two_points"


@router.post("/{plan_id}/calibrate")
async def calibrate_plan(plan_id: str, body: CalibIn, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    try:
        calib = G.compute_calibration(body.p1, body.p2, body.real_distance_m)
    except ValueError as e:
        raise HTTPException(422, str(e))
    payload = {**calib, "method": body.method, "confidence": 0.95,
               "p1": list(body.p1), "p2": list(body.p2), "created_at": _now()}
    await _apply_new_calibration(plan_id, user["user_id"], body.page_index, payload)
    await _snapshot(plan_id, user["user_id"], "calibrate",
                    {"page": body.page_index, "ppm": payload["pixels_per_meter"]})
    return {"ok": True, "page_index": body.page_index, "calibration": payload}


class CalibCheckIn(BaseModel):
    page_index: int
    p1: tuple[float, float]
    p2: tuple[float, float]
    expected_m: float = Field(gt=0)


@router.post("/{plan_id}/calibrate/check")
async def calibrate_check(plan_id: str, body: CalibCheckIn, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "calibrations": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if not calib:
        raise HTTPException(400, "Página não calibrada")
    measured = G.distance_m(body.p1, body.p2, calib["pixels_per_meter"])
    return G.calibration_check(measured, body.expected_m)


# ============ PLAN DEFAULTS & PAGE LEVEL ============

class PlanDefaultsIn(BaseModel):
    ceiling_h_m: float = Field(ge=1.5, le=6.0)
    floor_thickness_m: float = Field(ge=0.02, le=1.0)


@router.patch("/{plan_id}/defaults")
async def update_plan_defaults(plan_id: str, body: PlanDefaultsIn, user=Depends(current_user)) -> dict:
    """Défauts globaux du plan (hauteur murs, épaisseur plancher)."""
    res = await db.plans_takeoff.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"plan_defaults": {"ceiling_h_m": body.ceiling_h_m,
                                     "floor_thickness_m": body.floor_thickness_m},
                   "updated_at": _now()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Planta não encontrada")
    return {"ok": True,
            "plan_defaults": {"ceiling_h_m": body.ceiling_h_m,
                              "floor_thickness_m": body.floor_thickness_m}}


class PageLevelIn(BaseModel):
    level_index: int | None = None
    level_label: str | None = None


@router.patch("/{plan_id}/pages/{page_index}/level")
async def set_page_level(plan_id: str, page_index: int, body: PageLevelIn,
                        user=Depends(current_user)) -> dict:
    """Assigne un niveau (RDC / R+1 / R+2 / Sous-sol) à une page."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0, "pages": 1})
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    if page_index < 0 or page_index >= len(p.get("pages") or []):
        raise HTTPException(404, "Página desconhecida")
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"pages.{page_index}.level_index": body.level_index,
                  f"pages.{page_index}.level_label": body.level_label,
                  "updated_at": _now()}}
    )
    return {"ok": True, "page_index": page_index,
            "level_index": body.level_index, "level_label": body.level_label}


# ============ ANNOTATIONS (Counter / Notes / Angles / Roof pitch surfaces) ============
# Inspiré de QuoterPlan : outils de traçage plan persistés par page dans plan.annotations

class CounterMarker(BaseModel):
    x: float
    y: float


class CounterAnnotation(BaseModel):
    id: str
    label: str = "Contador"
    color: str = "#f97316"  # orange par défaut (ConstruPilot palette)
    unit: str = "u"          # u / prises / spots / radiateurs / m² / etc.
    markers: list[CounterMarker] = []


class NoteAnnotation(BaseModel):
    id: str
    x: float
    y: float
    text: str = ""


class AngleAnnotation(BaseModel):
    id: str
    # 3 points : sommet + 2 branches
    vx: float
    vy: float
    ax: float
    ay: float
    bx: float
    by: float
    degrees: float
    label: str | None = None  # ex: "Pente toiture ouest"


class PitchSurfaceAnnotation(BaseModel):
    id: str
    points: list[list[float]]       # polygone en pixels
    projected_area_m2: float         # aire vue en plan
    pitch_degrees: float             # inclinaison (0 = à plat)
    real_area_m2: float              # aire réelle = projected / cos(pitch)
    label: str | None = None


class AnnotationsIn(BaseModel):
    page_index: int = 0
    counters: list[CounterAnnotation] = []
    notes: list[NoteAnnotation] = []
    angles: list[AngleAnnotation] = []
    pitched_surfaces: list[PitchSurfaceAnnotation] = []


@router.patch("/{plan_id}/annotations")
async def save_annotations(plan_id: str, body: AnnotationsIn, user=Depends(current_user)) -> dict:
    """Persiste les 4 types d'annotations QuoterPlan-like par page (compteur / note / angle / pente).

    Le document plan stocke `annotations` = { "<page_index>": { counters, notes, angles, pitched_surfaces } }.
    """
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0, "pages": 1, "annotations": 1}
    )
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    if body.page_index < 0 or body.page_index >= len(p.get("pages") or []):
        raise HTTPException(404, "Página desconhecida")

    page_key = str(body.page_index)
    payload = {
        "counters": [c.model_dump() for c in body.counters],
        "notes": [n.model_dump() for n in body.notes],
        "angles": [a.model_dump() for a in body.angles],
        "pitched_surfaces": [s.model_dump() for s in body.pitched_surfaces],
    }
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"annotations.{page_key}": payload, "updated_at": _now()}}
    )
    total_counter_items = sum(len(c["markers"]) for c in payload["counters"])
    return {"ok": True, "page_index": body.page_index,
            "totals": {"counters": len(payload["counters"]),
                       "counter_items": total_counter_items,
                       "notes": len(payload["notes"]),
                       "angles": len(payload["angles"]),
                       "pitched_surfaces": len(payload["pitched_surfaces"])}}

