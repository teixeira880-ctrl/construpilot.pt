"""Common take-off methods for every company and every construction system (CLT and traditional).

The same steps for everyone: heights (standard when the plan is silent), wall network and junctions, pieces without
double count, quantities with their origin, cross-checks, prices with source, premium dossier with the dimensioned
drawings attached. Each company works only on its own parameters, library and plans. The CLT Rezult brand stays
with the pilot account; every other account receives the ConstruPilot brand.
"""
from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from bim_studio.store import tenant_of
from core.db import db
from core.permissions import require_feature
from core.security import pro_required
from engines.takeoff_core import adaptadores, desenhos, dossier, estudo, sistemas

router = APIRouter(prefix="/metodos", tags=["metodos"])
Lang = Literal["pt", "en", "uk", "fr"]


async def member(user=Depends(pro_required)):
    if not user or user.get("active") is False or user.get("company_active") is False:
        raise HTTPException(403, "Conta inativa.")
    return user


async def editor(user=Depends(member)):
    require_feature(user, "devis")
    return user


async def _company(user):
    doc = await db.takeoff_parameters.find_one({"_id": tenant_of(user)}) or {}
    lib = await db.takeoff_library.find_one({"_id": tenant_of(user)}) or {}
    return doc.get("valores") or {}, [estudo.PriceItem(**i) for i in lib.get("itens") or []]


def _brand(user):
    """Pilot account: CLT Rezult brand; every other account: ConstruPilot."""
    try:
        from bim_studio.clt_access import is_pilot
        from engines.calc_lots.premium import marca
        if is_pilot(user):
            b = marca("clt-rezult")
            if b:
                return {"nome": b["nome"], "cor": b["cor"], "logo_bytes": b.get("logo_bytes"), "site": b.get("site", "")}
    except Exception:  # noqa: BLE001 - the brand never blocks a dossier
        pass
    return dict(dossier.CONSTRUPILOT)


def _run(body, params, library):
    try:
        return estudo.run(body, params, library)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/sistemas")
async def systems(user=Depends(member)):
    values, library = await _company(user)
    return {"sistemas": {k: {"nome": v["nome"], "prefabricado": v.get("prefabricado", False)} for k, v in sistemas.SYSTEMS.items()},
            "parametros": sistemas.merged(values), "biblioteca": [i.model_dump() for i in library]}


class ParamsIn(BaseModel):
    valores: dict[str, float | dict] = Field(default_factory=dict, max_length=200)


@router.put("/parametros")
async def save_parameters(body: ParamsIn, user=Depends(editor)):
    try:
        merged = sistemas.merged(body.valores)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    clean = {k: v for k, v in body.valores.items() if k in merged}
    await db.takeoff_parameters.update_one({"_id": tenant_of(user)}, {"$set": {"valores": clean}}, upsert=True)
    return {"parametros": merged}


class LibraryIn(BaseModel):
    itens: list[estudo.PriceItem] = Field(default_factory=list, max_length=2000)


@router.put("/biblioteca")
async def save_library(body: LibraryIn, user=Depends(editor)):
    await db.takeoff_library.update_one({"_id": tenant_of(user)}, {"$set": {"itens": [i.model_dump() for i in body.itens]}},
                                        upsert=True)
    return {"itens": len(body.itens)}


@router.get("/plantas")
async def plans(user=Depends(member)):
    """The user's plans already read by the take-off module (traditional construction)."""
    docs = await db.plans_takeoff.find({"user_id": user["user_id"], "trashed_at": None},
                                       {"_id": 0, "plan_id": 1, "filename": 1, "page_count": 1, "created_at": 1,
                                        "pages.index": 1, "pages.level_label": 1, "pages.level_index": 1}).sort("created_at", -1).to_list(100)
    return {"plantas": docs}


class PageChoice(BaseModel):
    index: int = Field(ge=0, le=500)
    nome: str = Field(min_length=1, max_length=60)
    nivel: int = Field(default=0, ge=-5, le=60)
    altura_m: float | None = Field(default=None, gt=0, le=20)


class FromPlan(BaseModel):
    nome: str = Field(default="Estudo", min_length=1, max_length=80)
    pais: Literal["PT", "FR", "UA"] = "PT"
    sistema: estudo.SystemId = "alvenaria_tijolo"
    paginas: list[PageChoice] = Field(min_length=1, max_length=20)


@router.post("/plantas/{plan_id}/projeto")
async def project_from_plan(plan_id: str, body: FromPlan, user=Depends(member)):
    """Common project built from a plan of the take-off module: every wall read, its source, and what is to confirm."""
    p = await db.plans_takeoff.find_one({"plan_id": plan_id, "user_id": user["user_id"]},
                                        {"_id": 0, "pages.image_png_b64": 0, "pages.vectors": 0, "pages.text_blocks": 0})
    if not p:
        raise HTTPException(404, "Planta não encontrada.")
    pages = {pg.get("index", i): pg for i, pg in enumerate(p.get("pages") or [])}
    floors, notes = [], []
    for choice in body.paginas:
        page = pages.get(choice.index)
        if not page:
            raise HTTPException(422, f"A página {choice.index + 1} não existe.")
        rooms = [r for r in p.get("rooms") or [] if r.get("page_index", 0) == choice.index]
        cal = (p.get("calibrations") or {}).get(str(choice.index)) or {}
        try:
            floor, n = adaptadores.from_plan_page(page, name=choice.nome, nivel=choice.nivel, rooms=rooms,
                                                  room_ppm=cal.get("pixels_per_meter"),
                                                  ref=f"{p.get('filename', plan_id)} p.{choice.index + 1}")
        except ValueError as exc:
            raise HTTPException(422, f"{choice.nome}: {exc}") from exc
        if choice.altura_m:
            floor.update(altura_m=choice.altura_m, altura_fonte="altura indicada pelo utilizador")
        floors.append(floor)
        notes += [f"{choice.nome}: {x}" for x in n]
    try:
        project = estudo.Project(nome=body.nome, pais=body.pais, sistema=body.sistema, pisos=floors)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"projeto": project.model_dump(), "notas": notes}


@router.post("/estudo")
async def study(body: estudo.Project, user=Depends(member)):
    params, library = await _company(user)
    result = await asyncio.to_thread(_run, body, params, library)
    return estudo.public(result)


@router.post("/desenhos")
async def drawings(body: estudo.Project, formato: Literal["pdf", "dxf"] = Query("pdf"), lang: Lang = Query("pt"),
                   user=Depends(member)):
    params, library = await _company(user)
    result = await asyncio.to_thread(_run, body, params, library)
    if formato == "dxf":
        data = await asyncio.to_thread(desenhos.dxf, result["_redes"], title=body.nome, lang=lang)
        return Response(data, media_type="application/dxf", headers={"Content-Disposition": 'attachment; filename="desenhos-cotados.dxf"'})
    meta = {f["nome"]: f"{f['altura']['valor_m']:.2f} m · {f['leitura']}" for f in result["pisos"]}
    data, _sheets = await asyncio.to_thread(desenhos.annex_pdf, result["_redes"], meta, title=body.nome, brand=_brand(user), lang=lang)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="desenhos-cotados.pdf"'})


@router.post("/dossier")
async def make_dossier(body: estudo.Project, lang: Lang = Query("pt"), user=Depends(member)):
    params, library = await _company(user)
    result = await asyncio.to_thread(_run, body, params, library)
    data = await asyncio.to_thread(dossier.build, result, brand=_brand(user), lang=lang)
    return Response(data, media_type="application/pdf", headers={"Content-Disposition": 'attachment; filename="dossier-medicoes.pdf"'})
