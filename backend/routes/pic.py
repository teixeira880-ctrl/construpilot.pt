"""Plano de estaleiro (PT): leitura IA da planta de implantação, opções a validar,
cálculo de grua / implantação (engines/pic.py), vista aérea DGT, 3D, exportação PDF."""
import base64
import binascii
import io
import re
import unicodedata
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines import ai, pic, pic_pdf

router = APIRouter(prefix="/pro/pic", tags=["pic"])


def _now():
    return datetime.now(timezone.utc).isoformat()


LIGHT = {"_id": 0, "aerial.image_png_b64": 0, "snapshot_3d": 0, "render_ia": 0}


async def _doc(plan_id, uid, light=True):
    return await db.pic_plans.find_one({"plan_id": plan_id, "user_id": uid}, LIGHT if light else {"_id": 0})


async def _base_image(d: dict | None, plan_id: str, uid: str) -> bytes:
    """Image de fond du PIC : orthophoto IGN si le site est en vue aérienne, sinon le plan de masse."""
    if d and (d.get("site") or {}).get("base") == "aerial":
        b64 = (d.get("aerial") or {}).get("image_png_b64")
        if not b64:
            raise HTTPException(422, "Vista aérea indisponível: volte a pedi-la")
        return base64.b64decode(b64)
    p = await _plan(plan_id, uid)
    img = next((pg["image_png_b64"] for pg in (p.get("pages") or []) if pg.get("image_png_b64")), None)
    if not img:
        raise HTTPException(422, "Nenhuma imagem de planta")
    return base64.b64decode(img)


async def _plan(plan_id, uid, with_image=True):
    proj = {"_id": 0} if with_image else {"_id": 0, "pages.image_png_b64": 0}
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": uid}, proj)
    if not p:
        raise HTTPException(404, "Planta não encontrada")
    return p


def _image_size(b64: str) -> tuple[int, int]:
    from PIL import Image
    with Image.open(io.BytesIO(base64.b64decode(b64))) as im:
        return im.size


@router.get("/catalog")
async def catalog() -> dict:
    return {"cranes": [{"key": k, "label": c["label"], "family": pic.FAMILIES.get(c["family"]),
                        "cmax_t": c["cmax_t"], "jib_max_m": c["jib_max_m"],
                        "tip_t": c["tips"].get(c["jib_max_m"]), "jibs": c.get("jibs"),
                        "hsc_m": c.get("hsc_m"), "source": c["source"]}
                       for k, c in pic.CRANES.items()],
            "questions": pic.questions()}


@router.post("/{plan_id}/analyze")
async def analyze(plan_id: str, user=Depends(current_user)) -> dict:
    p = await _plan(plan_id, user["user_id"])
    images = [pg["image_png_b64"] for pg in (p.get("pages") or []) if pg.get("image_png_b64")][:1]
    if not images:
        raise HTTPException(422, "Nenhuma imagem de planta")
    img_w, img_h = _image_size(images[0])
    d = await ai.analyze_site_plan(images)
    site = {"base": "plan", **pic.site_from_analysis(d, img_w, img_h)}
    doc = {"plan_id": plan_id, "user_id": user["user_id"], "filename": p.get("filename"),
           "site": site, "questions": pic.questions(pic.hints(d)),
           "analysis": {"scale_detected": d.get("scale_detected"),
                        "scale_confidence": d.get("scale_confidence"),
                        "obstacles": d.get("obstacles") or [], "streets": d.get("streets") or [],
                        "notes": d.get("notes"), **pic.hints(d)},
           "answers": {}, "result": None, "updated_at": _now()}
    await db.pic_plans.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                  {"$set": doc, "$setOnInsert": {"created_at": _now()}}, upsert=True)
    return doc


class AerialIn(BaseModel):
    address: str = Field(min_length=4, max_length=200)
    plan_id: str | None = None
    span_m: float | None = Field(default=None, ge=80, le=800)


@router.post("/aerial")
async def aerial(body: AerialIn, user=Depends(current_user)) -> dict:
    """Vista aérea: ortofotomapa oficial da DGT enquadrado no prédio cadastral da morada, à escala."""
    from engines.urbanismo_pt.auto import geo
    g = await geo.geocode(body.address)
    if not g.get("ok"):
        raise HTTPException(404, "Morada não encontrada")
    lat, lon = float(g["data"]["lat"]), float(g["data"]["lon"])
    label = g["data"].get("morada_formatada") or body.address
    cad = await geo.cadastro(lat, lon)
    ring = (cad.get("data") or {}).get("anel_lonlat") if cad.get("ok") else None
    geometry = {"type": "Polygon", "coordinates": [ring]} if ring else None
    frame = pic.aerial_frame_for(geometry, lat, lon, body.span_m)
    # ortofotomapa oficial (DGT, OGC API Maps) pedido exatamente no enquadramento calculado
    bbox = f"{frame['minlon']},{frame['minlat']},{frame['maxlon']},{frame['maxlat']}"
    _st, raw = await geo._get(f"{geo.DGT}/collections/ortos-rgb/map",
                              {"bbox": bbox, "width": frame["size"], "height": frame["size"], "f": "png"}, "bytes")
    fonte = "Ortofotomapa DGT (OrtoSat, 30 cm)"
    if not (raw and raw[:4] == b"\x89PNG"):
        raise HTTPException(502, "Ortofotomapa da DGT indisponível de momento — tente novamente mais tarde")
    # uma vista aérea existente pode ser reenquadrada; caso contrário cria-se um novo plano (o plano de
    # uma planta importada nunca é substituído)
    plan_id = None
    if body.plan_id and body.plan_id.startswith("aerial-") and await _doc(body.plan_id, user["user_id"]):
        plan_id = body.plan_id
    plan_id = plan_id or f"aerial-{uuid.uuid4().hex[:12]}"
    site = pic.aerial_site(frame, geometry)
    notes = ("Limite do estaleiro = prédio cadastral. " if site["parcel"]
             else "Sem cadastro geométrico neste local: trace o limite do estaleiro. ") \
        + "Trace o edifício a construir e coloque o acesso."
    doc = {"plan_id": plan_id, "user_id": user["user_id"], "filename": label,
           "site": site, "questions": pic.questions({}),
           "analysis": {"notes": notes, "source": fonte + (f" — {cad.get('fonte')}" if ring else ""),
                        "address": label, "cadastre": None, "contenance_m2": None, "obstacles": [], "streets": []},
           "answers": {}, "result": None, "updated_at": _now()}
    await db.pic_plans.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {**doc, "aerial": {**frame, "image_png_b64": base64.b64encode(raw).decode()}, "snapshot_3d": None,
                  "render_ia": None},
         "$setOnInsert": {"created_at": _now()}}, upsert=True)
    return doc


@router.get("")
async def list_aerial(user=Depends(current_user)) -> dict:
    """PIC créés à partir d'une adresse (sans plan de masse importé), pour les rouvrir."""
    cur = db.pic_plans.find({"user_id": user["user_id"], "plan_id": {"$regex": "^aerial-"}},
                            {"_id": 0, "plan_id": 1, "filename": 1, "updated_at": 1}).sort("updated_at", -1).limit(50)
    return {"items": [x async for x in cur]}


@router.get("/{plan_id}/image")
async def base_image(plan_id: str, user=Depends(current_user)) -> dict:
    d = await _doc(plan_id, user["user_id"], light=False)
    return {"image_png_b64": base64.b64encode(await _base_image(d, plan_id, user["user_id"])).decode()}


class SnapshotIn(BaseModel):
    image_b64: str = Field(min_length=100, max_length=6_000_000)


@router.post("/{plan_id}/snapshot")
async def snapshot(plan_id: str, body: SnapshotIn, user=Depends(current_user)) -> dict:
    """Capture de la vue 3D (prise dans le navigateur) pour la page 3D du PDF."""
    raw = base64.b64encode(_image_bytes(body.image_b64)).decode()
    r = await db.pic_plans.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                      {"$set": {"snapshot_3d": raw}})
    if not getattr(r, "matched_count", 1):
        raise HTTPException(404, "Plano de estaleiro não encontrado")
    return {"ok": True}


def _image_bytes(image_b64: str) -> bytes:
    raw = image_b64.split(",", 1)[-1]
    try:
        from PIL import Image
        data = base64.b64decode(raw, validate=True)
        with Image.open(io.BytesIO(data)) as im:
            im.verify()
        return data
    except (binascii.Error, ValueError, OSError, SyntaxError):
        raise HTTPException(422, "Imagem inválida") from None


RENDER_HEAD = ("@model is a 3D massing view of a building construction site. Keep exactly the same camera position and "
               "framing, and the same position, size, orientation and number of every tower crane, building, site "
               "cabin, skip, truck, storage area, silo, fence and tree. Do not add, remove or move anything. ")
RENDER_PROMPT = ("Photorealistic aerial drone photograph of this active building construction site in Portugal, clear "
                 "daylight, natural shadows, true-to-life materials: yellow lattice tower cranes, reinforced-concrete "
                 "building under construction with scaffolding, white site cabins, steel waste skips, delivery truck "
                 "on its unloading bay, pallets and formwork in the storage area, galvanised temporary fencing along "
                 "the site boundary, compacted earth and gravel ground. Realistic surroundings beyond the fence. "
                 "No text, no labels, no coloured circles, no annotations, no watermark. Single photorealistic image.")


@router.post("/{plan_id}/render")
async def render_ia(plan_id: str, body: SnapshotIn, user=Depends(current_user)) -> dict:
    """Image d'ambiance photoréaliste générée par IA à partir de la vue 3D (géométrie de référence)."""
    d = await _doc(plan_id, user["user_id"])
    if not d or not (d.get("result") or {}).get("elements"):
        raise HTTPException(404, "Calcule primeiro o plano de estaleiro")
    base = _image_bytes(body.image_b64)
    from engines import photoreal
    res = await photoreal.render(base, RENDER_PROMPT, head=RENDER_HEAD, feature="pic_photoreal",
                                 session_id=f"pic_{plan_id}", timeout=180)
    if not res:
        raise HTTPException(502, "Render fotorrealista indisponível de momento — tente novamente mais tarde")
    img, engine = res
    b64 = base64.b64encode(img).decode()
    await db.pic_plans.update_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                  {"$set": {"render_ia": {"image_b64": b64, "engine": engine, "at": _now()}}})
    return {"image_b64": b64, "engine": engine}


@router.get("/{plan_id}")
async def get_pic(plan_id: str, user=Depends(current_user)) -> dict:
    d = await _doc(plan_id, user["user_id"])
    if not d:
        raise HTTPException(404, "Ainda não há plano de estaleiro para esta planta")
    return d


class SiteIn(BaseModel):
    m_per_px: float | None = Field(default=None, gt=0)
    parcel: list[list[float]] = Field(default_factory=list)
    buildings: list[list[list[float]]] = Field(default_factory=list)
    accesses: list[list[float]] = Field(default_factory=list)


class PlacedIn(BaseModel):
    id: str
    x: float
    y: float
    w: float | None = None
    h: float | None = None
    rot: float = 0


class ComputeIn(BaseModel):
    site: SiteIn
    answers: dict = Field(default_factory=dict)
    placed: list[PlacedIn] = Field(default_factory=list)


@router.post("/{plan_id}/compute")
async def compute(plan_id: str, body: ComputeIn, user=Depends(current_user)) -> dict:
    """Calcule (ou vérifie, si `placed` est fourni) le plan d'installation."""
    d = await _doc(plan_id, user["user_id"])
    if not d:
        raise HTTPException(404, "Faça primeiro a análise da planta de implantação ou a vista aérea")
    site = {**d["site"], "m_per_px": body.site.m_per_px, "parcel": pic.norm_points(body.site.parcel),
            "buildings": [pts for pts in (pic.norm_points(b) for b in body.site.buildings) if len(pts) >= 3],
            "accesses": pic.norm_points(body.site.accesses)}
    placed = [{k: v for k, v in e.model_dump().items() if v is not None} for e in body.placed]
    result = pic.compute(site, body.answers, placed or None)
    await db.pic_plans.update_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"$set": {"site": site, "answers": body.answers, "result": result, "snapshot_3d": None, "render_ia": None,
                  "updated_at": _now()}})
    return {"site": site, "result": result}


@router.get("/{plan_id}/pdf")
async def pdf(plan_id: str, user=Depends(current_user)):
    d = await _doc(plan_id, user["user_id"], light=False)
    if not d or not (d.get("result") or {}).get("elements"):
        raise HTTPException(404, "Calcule primeiro o plano de estaleiro")
    image = await _base_image(d, plan_id, user["user_id"])
    try:
        from routes.phase7 import get_branding
        branding = await get_branding(user)
    except Exception:  # noqa: BLE001 — le PDF sort même sans charte
        branding = {}
    snap = None
    if d.get("snapshot_3d"):
        try:
            snap = base64.b64decode(d["snapshot_3d"])
        except (binascii.Error, ValueError):
            snap = None
    ia = None
    if (d.get("render_ia") or {}).get("image_b64"):
        try:
            ia = base64.b64decode(d["render_ia"]["image_b64"])
        except (binascii.Error, ValueError):
            ia = None
    data = pic_pdf.build(d, image, branding, snapshot=snap, render_ia=ia)
    raw = unicodedata.normalize("NFKD", (d.get("filename") or plan_id).rsplit(".", 1)[0])
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", raw.encode("ascii", "ignore").decode()).strip("-")
    name = f"Plano-de-estaleiro-{stem or plan_id}.pdf"
    return Response(data, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
