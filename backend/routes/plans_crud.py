"""CRUD & calibration routes du module plans (upload, list, get, delete,
calibrate, plan defaults, page level).

Refactor iter53 : extrait de `routes/plans.py`.
"""
from __future__ import annotations

import logging
import secrets
from typing import Literal

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import geometry as G
from engines.plan_processor import auto_calibration_from_pdf_scale, process_upload

from routes.plans_common import (
    ALLOWED_MIMES, MAX_UPLOAD_MB, _now, _plan_summary, _snapshot, router,
)

logger = logging.getLogger(__name__)


# ============ UPLOAD ============

@router.post("/upload")
async def upload_plan(
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    deskew: bool = Form(False),
    user=Depends(current_user),
):
    # Accès Plan ouvert à tous les utilisateurs connectés (rendus 3D payants à l'unité)
    data = await file.read()
    if len(data) > MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"Fichier trop volumineux (>{MAX_UPLOAD_MB} Mo)")

    mime = (file.content_type or "").lower()
    lower_name = (file.filename or "").lower()
    is_cad = lower_name.endswith((".dxf", ".dwg"))
    if mime and mime not in ALLOWED_MIMES and not is_cad:
        if mime != "application/octet-stream":
            raise HTTPException(415, f"Format non supporté : {mime}")

    # DWG (format AutoCAD propriétaire) → conversion en DXF via CloudConvert
    if lower_name.endswith(".dwg"):
        from engines.dwg_convert import dwg_to_dxf
        try:
            data = await dwg_to_dxf(data, file.filename or "plan.dwg")
        except RuntimeError as e:
            raise HTTPException(422, str(e))
        except Exception:
            logger.exception("DWG conversion failed")
            raise HTTPException(502, "Conversion DWG impossible — réessayez plus tard.")
        parse_name = (file.filename or "plan")[:-4] + ".dxf"
        mime = "image/vnd.dxf"
    else:
        parse_name = file.filename or "plan"

    try:
        parsed = process_upload(data, parse_name, mime, deskew=deskew)
    except Exception as e:
        logger.exception("plan process failed")
        raise HTTPException(422, f"Impossible de lire le fichier : {e}")

    plan_id = "plan_" + secrets.token_hex(6)
    calibrations = _auto_calibrate_pages(parsed)

    doc = {
        "plan_id": plan_id,
        "user_id": user["user_id"],
        "project_id": project_id,
        "filename": file.filename,
        "size_bytes": len(data),
        "kind": parsed["kind"],
        "page_count": parsed["page_count"],
        "detected_scale_denominator": parsed.get("detected_scale_denominator"),
        "structural_metre": parsed.get("structural_metre"),
        "pages": parsed["pages"],
        "calibrations": calibrations,
        "rooms": [],
        "measurements": [],
        "ai_analysis": None,
        "created_at": _now(),
        "updated_at": _now(),
    }
    await _insert_plan_safe(doc)
    return _plan_summary(doc)


# ============ MÉTRÉ STRUCTURE (DWG/DXF) ============

@router.get("/{plan_id}/structural-metre")
async def get_structural_metre(plan_id: str, user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structural_metre": 1, "structural_estimate": 1, "kind": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
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


@router.post("/{plan_id}/structural-estimate")
async def compute_structural_estimate(plan_id: str, body: StructuralEstimateIn,
                                       user=Depends(current_user)) -> dict:
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "structural_metre": 1, "calibrations": 1,
         "pages.dxf_ratio": 1, "pages.index": 1})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    metre = p.get("structural_metre")
    if not metre:
        raise HTTPException(400, "Aucun métré structure disponible (plan non DWG/DXF ou sans calques exploitables)")
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
        raise HTTPException(404, "Plan introuvable")
    metre = p.get("structural_metre")
    if not metre:
        raise HTTPException(400, "Aucun métré structure disponible (plan non DWG/DXF ou sans calques exploitables)")
    metre, _scale_src = _rescale_metre_to_calibration(metre, p)
    from engines.dxf_takeoff import cost_structural
    estimate = cost_structural(metre, body.dict())
    margin = float(estimate["params"].get("margin_pct", 0)) / 100.0
    vat_rate = round(float(estimate["totals"].get("tva_rate", 0.20)) * 100.0, 2)

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
        raise HTTPException(422, "Le métré ne contient aucune ligne à chiffrer.")

    from routes.documents import _compute_totals
    doc = {
        "doc_id": "doc_" + secrets.token_hex(6),
        "user_id": user["user_id"],
        "doc_type": "quote",
        "number": None,
        "title": f"Devis structure — {p.get('filename') or 'plan'}",
        "client_id": None,
        "client": None,
        "status": "draft",
        "lines": lines,
        "notes": "Devis généré à partir du métré structure (DWG/DXF).",
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
    det = dict(m.get("detected") or {})
    for k in ("wall_thickness_m", "beam_w_m", "col_size_m"):
        if det.get(k):
            det[k] = round(det[k] * f, 3)
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
            "Plan trop volumineux à stocker (trop de pages ou images très lourdes). "
            "Essayez de n'importer que les pages utiles ou un plan en résolution moindre.",
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
    """Calibration automatique d'un DXF/DWG : pixels_per_meter = dxf_ratio × unités/m.
    Le DXF porte des coordonnées réelles → l'échelle est déduite exactement (pas besoin
    d'une mention « 1:100 »). $INSUNITS étant souvent faux/absent, on valide toujours
    la cohérence via l'étendue géométrique (un plan mesure 0,5–1000 m)."""
    units = (parsed.get("dxf_units") or "").lower()
    calibs: dict = {}
    for pg in parsed["pages"]:
        ratio = pg.get("dxf_ratio")  # pixels par unité DXF
        if not ratio:
            continue
        span = _dxf_span_units(pg)
        upm = _UNITS_PER_METER.get(units)
        # Contrôle de plausibilité : la plus grande dimension réelle doit être crédible
        real_span_m = (span / upm) if upm else 0
        if upm and 0.5 <= real_span_m <= 1000:
            method, conf, unit_label = "auto_dxf_units", 0.92, units
        else:
            upm, unit_label = _guess_units_per_meter(pg)
            method, conf = "auto_dxf_guess", 0.6
        calibs[str(pg["index"])] = {
            "pixels_per_meter": round(ratio * upm, 4),
            "method": method,
            "dxf_units": unit_label,
            "confidence": conf,
            "created_at": _now(),
        }
    return calibs


def _auto_calibrate_pages(parsed: dict) -> dict:
    """Try to derive an initial pixels_per_meter per page from the detected scale."""
    if parsed.get("kind") == "dxf":
        return _auto_calibrate_dxf(parsed)
    scale = parsed.get("detected_scale_denominator")
    if not scale:
        return {}
    calibs: dict = {}
    for pg in parsed["pages"]:
        ppm = auto_calibration_from_pdf_scale(scale, pg.get("dpi", 150))
        if ppm:
            calibs[str(pg["index"])] = {
                "pixels_per_meter": ppm,
                "method": "auto_pdf_scale",
                "scale_denominator": scale,
                "confidence": 0.75,
                "created_at": _now(),
            }
    return calibs


# ============ LIST / GET / DELETE ============

@router.get("")
async def list_plans(user=Depends(current_user)) -> dict:
    docs = await db.plans_takeoff.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "pages.image_png_b64": 0}
    ).sort("created_at", -1).to_list(100)
    return {"plans": docs}


@router.get("/{plan_id}")
async def get_plan(plan_id: str, user=Depends(current_user)):
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                         {"_id": 0})
    if not p:
        raise HTTPException(404, "Plan introuvable")
    return _plan_summary(p)


@router.get("/{plan_id}/page/{page_index}")
async def get_plan_page(plan_id: str, page_index: int, user=Depends(current_user)):
    """Renvoie l'image PNG (base64) + vecteurs de la page demandée."""
    p = await db.plans_takeoff.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "pages": 1}
    )
    if not p:
        raise HTTPException(404, "Plan introuvable")
    pages = p.get("pages") or []
    if page_index < 0 or page_index >= len(pages):
        raise HTTPException(404, "Page inconnue")
    return pages[page_index]


@router.delete("/{plan_id}")
async def delete_plan(plan_id: str, user=Depends(current_user)) -> dict:
    res = await db.plans_takeoff.delete_one({"plan_id": plan_id, "user_id": user["user_id"]})
    if res.deleted_count == 0:
        raise HTTPException(404, "Plan introuvable")
    return {"ok": True}


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
        raise HTTPException(404, "Plan introuvable")

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
    }
    await db.plans_takeoff.insert_one(dup)
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
        raise HTTPException(404, "Plan introuvable")
    try:
        calib = G.compute_calibration(body.p1, body.p2, body.real_distance_m)
    except ValueError as e:
        raise HTTPException(422, str(e))
    payload = {**calib, "method": body.method, "confidence": 0.95,
               "p1": list(body.p1), "p2": list(body.p2), "created_at": _now()}
    await db.plans_takeoff.update_one(
        {"plan_id": plan_id},
        {"$set": {f"calibrations.{body.page_index}": payload, "updated_at": _now()}}
    )
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
        raise HTTPException(404, "Plan introuvable")
    calib = (p.get("calibrations") or {}).get(str(body.page_index))
    if not calib:
        raise HTTPException(400, "Page non calibrée")
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
        raise HTTPException(404, "Plan introuvable")
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
        raise HTTPException(404, "Plan introuvable")
    if page_index < 0 or page_index >= len(p.get("pages") or []):
        raise HTTPException(404, "Page inconnue")
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
    label: str = "Compteur"
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
        raise HTTPException(404, "Plan introuvable")
    if body.page_index < 0 or body.page_index >= len(p.get("pages") or []):
        raise HTTPException(404, "Page inconnue")

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
