"""Rotas « Construção tradicional — betão armado e alvenarias » (ofertas Pro e Pro Business).

Sem IA: o motor é determinístico e parte da geometria já lida e validada no módulo Plantas (ou de um projeto JSON).
O estudo guarda o PROJETO; resultado, dossier PDF, Excel, visualizador 3D e render são recalculados a partir dele
(o mesmo projeto dá sempre exatamente os mesmos números).
"""
from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from engines.access import require_level
from engines.tradicional import VERSAO, estudo
from engines.tradicional import adapter as A
from engines.tradicional import defaults as D
from engines.lsf import quantities as Q

router = APIRouter(prefix="/tradicional", tags=["tradicional"], dependencies=[Depends(require_level("pro"))])

from routes.auth import current_user  # noqa: E402
from engines.nom_fichier import content_disposition, nom_document  # noqa: E402

MAX_INPUT = 3_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sid() -> str:
    return "trd_" + uuid.uuid4().hex[:12]


class LevelIn(BaseModel):
    page_index: int = 0
    name: str | None = None
    elevation_m: float | None = None
    height_m: float | None = 2.7
    origin: list[float] | None = None


class FromPlanIn(BaseModel):
    plan_id: str
    q_adm_kpa: float | None = None
    country: str | None = "pt"
    levels: list[LevelIn] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)
    title: str | None = None


class FromInputIn(BaseModel):
    input: dict
    title: str | None = None


class ProjectIn(BaseModel):
    project: dict


class PriceIn(BaseModel):
    mercado: bool = False          # procurar preços de mercado online para as linhas sem preço (assinalados « a analisar »)


def _resumo(st: dict) -> dict:
    r = st["resultado"]
    e = r["estudo"]
    return {"m3_betao": round(e["m3Betao"], 3), "kg_aco": round(e["kgAco"], 1), "unidades_alvenaria": e["unidadesAlvenaria"],
            "m2_alvenaria": round(e["m2Alvenaria"], 2), "pilares": e["nPilares"], "vigas": e["nVigas"], "sapatas": e["nSapatas"],
            "area_pisos_m2": e.get("areaPisos"), "avisos": len(r["avisos"]), "total_eur": st["totais"]["total"],
            "linhas_sem_preco": st["totais"]["linhas_sem_preco"]}


def _calc(project: dict, biblioteca: list | None = None, lang: str = "pt") -> dict:
    try:
        return estudo(project, biblioteca, lang)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Projeto incoerente: {exc}")


async def _biblioteca(uid: str) -> list:
    try:
        from routes.company_library import get_user_library
        return await get_user_library(uid)
    except Exception:  # noqa: BLE001
        return []


async def _branding(uid: str) -> dict | None:
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "brand_company_name": 1, "brand_logo_b64": 1, "brand_contact_line": 1,
                                                   "brand_address": 1, "brand_city": 1, "brand_postal": 1, "brand_nif": 1,
                                                   "brand_accent_color": 1, "organization_id": 1}) or {}
    src = u
    if u.get("organization_id"):
        org = await db.organizations.find_one({"org_id": u["organization_id"]}, {"_id": 0, "brand_company_name": 1, "brand_logo_b64": 1,
                                                                                 "brand_contact_line": 1, "brand_address": 1, "brand_city": 1,
                                                                                 "brand_postal": 1, "brand_nif": 1})
        if org:
            src = {**u, **{k: v for k, v in org.items() if v}}
    if not (src.get("brand_company_name") or src.get("brand_logo_b64")):
        return None
    return {"company_name": src.get("brand_company_name"), "logo_b64": src.get("brand_logo_b64"), "contact_line": src.get("brand_contact_line"),
            "address": src.get("brand_address"), "city": src.get("brand_city"), "postal": src.get("brand_postal"), "nif": src.get("brand_nif"),
            "accent_color": src.get("brand_accent_color")}


def _public(doc: dict) -> dict:
    doc.pop("_id", None)
    doc.pop("render_png_b64", None)
    has_photo = bool(doc.pop("photo_png_b64", None))
    doc["has_photo"] = has_photo
    return doc


async def _save(uid: str, project: dict, title: str, plan_id: str | None = None) -> dict:
    st = _calc(project, await _biblioteca(uid))
    doc = {"study_id": _sid(), "user_id": uid, "plan_id": plan_id, "title": title[:160], "created_at": _now(), "updated_at": _now(),
           "version": 1, "engine_version": VERSAO, "project": project, "summary": _resumo(st), "lines": st["linhas"], "totals": st["totais"],
           "warnings": st["resultado"]["avisos"], "assumptions": st["resultado"]["hipoteses"], "reading": project.get("leitura")}
    await db.trad_studies.insert_one({**doc})
    return _public(doc)


async def _get(study_id: str, uid: str) -> dict:
    doc = await db.trad_studies.find_one({"study_id": study_id, "user_id": uid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Estudo não encontrado")
    return doc


@router.get("/exemplo")
async def exemplo() -> dict:
    """Projeto de exemplo (moradia R/C + 1.º andar) — ponto de partida para um projeto sem planta."""
    return D.exemplo()


@router.post("/studies")
async def create_from_plan(body: FromPlanIn, user=Depends(current_user)) -> dict:
    plan = await db.plans_takeoff.find_one({"plan_id": body.plan_id, "user_id": user["user_id"]},
                                           {"_id": 0, "plan_id": 1, "filename": 1, "rooms": 1, "calibrations": 1, "structure": 1})
    if not plan:
        raise HTTPException(404, "Planta não encontrada")
    try:
        project = A.from_takeoff(plan, [lv.model_dump(exclude_none=True) for lv in body.levels] or None, (body.country or "pt"), body.options)
    except (A.AdapterError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    if body.q_adm_kpa:
        project["regras"]["q_adm_kpa"] = body.q_adm_kpa
        project["hipoteses"] = [h for h in project["hipoteses"] if "Tensão admissível" not in h]
    if body.title:
        project["nome"] = body.title
    return await _save(user["user_id"], project, body.title or f"Construção tradicional — {plan.get('filename') or ''}", body.plan_id)


@router.post("/studies/from-input")
async def create_from_input(body: FromInputIn, user=Depends(current_user)) -> dict:
    """Entrada = projeto (perimetros/paredes/pisos/coberturas) OU entrada MEP (levels/rooms/openings em m)."""
    if len(json.dumps(body.input, default=str)) > MAX_INPUT:
        raise HTTPException(413, "Dados de entrada demasiado volumosos")
    data = dict(body.input)
    try:
        if data.get("levels") and not data.get("perimetros"):
            project = A.from_mep_input(data, body.title)
        else:
            project = {**D.base(data.get("country", "PT")), **data}
    except (A.AdapterError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    if body.title:
        project["nome"] = body.title
    return await _save(user["user_id"], project, body.title or project.get("nome") or "Construção tradicional")


@router.get("/studies")
async def list_studies(user=Depends(current_user)) -> dict:
    rows = await db.trad_studies.find({"user_id": user["user_id"]}, {"_id": 0, "study_id": 1, "title": 1, "plan_id": 1, "summary": 1,
                                                                    "created_at": 1, "updated_at": 1, "version": 1}).sort("updated_at", -1).to_list(100)
    return {"studies": rows}


@router.get("/studies/{study_id}")
async def get_study(study_id: str, user=Depends(current_user)) -> dict:
    return _public(await _get(study_id, user["user_id"]))


@router.put("/studies/{study_id}/project")
async def update_project(study_id: str, body: ProjectIn, user=Depends(current_user)) -> dict:
    """O profissional ajusta o projeto (unidades de alvenaria, vãos, cotas, cargas, terreno…): tudo é recalculado."""
    doc = await _get(study_id, user["user_id"])
    st = _calc(body.project, await _biblioteca(user["user_id"]))
    patch = {"project": body.project, "summary": _resumo(st), "lines": st["linhas"], "totals": st["totais"], "warnings": st["resultado"]["avisos"],
             "assumptions": st["resultado"]["hipoteses"], "updated_at": _now(), "version": int(doc.get("version", 1)) + 1,
             "render_png_b64": None, "photo_png_b64": None}
    await db.trad_studies.update_one({"study_id": study_id, "user_id": user["user_id"]}, {"$set": patch})
    return _public({**doc, **patch})


@router.post("/studies/{study_id}/price")
async def price_study(study_id: str, body: PriceIn | None = None, user=Depends(current_user)) -> dict:
    """Preços: biblioteca da empresa → preços do projeto → (opcional) mercado online real, assinalado « a analisar »."""
    doc = await _get(study_id, user["user_id"])
    lib = await _biblioteca(user["user_id"])
    lines = doc["lines"]
    totals = Q.precificar(lines, lib, doc["project"].get("precos"))
    if body and body.mercado:
        mk = await Q.precos_mercado(lines)
        totals = Q.precificar(lines, lib, doc["project"].get("precos"), mk)
    await db.trad_studies.update_one({"study_id": study_id, "user_id": user["user_id"]},
                                    {"$set": {"lines": lines, "totals": totals, "updated_at": _now()}})
    return {"lines": lines, "totals": totals}


async def _full(doc: dict, uid: str):
    st = _calc(doc["project"], await _biblioteca(uid))
    # preços de mercado já aceites ficam (mesma linha, mesmo código)
    mk = {l["code"]: {"price": l["preco"]["unit"], "supplier": l["preco"].get("fonte"), "url": l["preco"].get("url"), "checked_at": l["preco"].get("data")}
          for l in doc.get("lines") or [] if (l.get("preco") or {}).get("origem") == "mercado"}
    if mk:
        st["totais"] = Q.precificar(st["linhas"], await _biblioteca(uid), doc["project"].get("precos"), mk)
    return st


async def _render(doc: dict, st: dict, uid: str):
    if doc.get("render_png_b64"):
        return [("estrutura", base64.b64decode(doc["render_png_b64"]))]
    try:
        from engines.tradicional.render import render
        out = await asyncio.to_thread(render, st["resultado"], None, 1600, 900, 64, 150)
    except Exception:  # noqa: BLE001 — sem Mitsuba: sem render
        return []
    if out:
        await db.trad_studies.update_one({"study_id": doc["study_id"], "user_id": uid}, {"$set": {"render_png_b64": base64.b64encode(out[0][1]).decode()}})
    return out[:1]


async def _photo(doc: dict, st: dict, uid: str, gerar: bool = False):
    """Foto fotorrealista a partir do render calculado (todas as contas). Guardada no estudo; só gerada a pedido."""
    if doc.get("photo_png_b64"):
        return base64.b64decode(doc["photo_png_b64"])
    if not gerar:
        return None
    ren = await _render(doc, st, uid)
    if not ren:
        return None
    from engines.foto_estrutura import fotorrealista
    r = await fotorrealista(ren[0][1], "tradicional")
    if not r:
        return None
    await db.trad_studies.update_one({"study_id": doc["study_id"], "user_id": uid}, {"$set": {"photo_png_b64": base64.b64encode(r[0]).decode()}})
    return r[0]


@router.post("/studies/{study_id}/photo")
async def study_photo(study_id: str, user=Depends(current_user)) -> Response:
    """Render fotorrealista da estrutura montada (mesma geometria do render calculado) — disponível para todas as contas Pro."""
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    img = await _photo(doc, st, user["user_id"], gerar=True)
    if not img:
        raise HTTPException(503, "Motores de imagem indisponíveis — o render calculado continua disponível")
    return Response(content=img, media_type="image/jpeg" if img[:3] == b"\xff\xd8\xff" else "image/png")


@router.get("/studies/{study_id}/pdf")
async def study_pdf(study_id: str, lang: str = "pt", user=Depends(current_user)) -> Response:
    from engines.tradicional.pdf import dossier
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    ren = await _render(doc, st, user["user_id"])
    foto = await _photo(doc, st, user["user_id"])
    if foto:
        ren = [("fotorrealista", foto)] + ren
    pdf = await asyncio.to_thread(dossier, st["resultado"], st["linhas"], st["totais"], await _branding(user["user_id"]), ren, doc.get("title"))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(nom_document("Construcao-tradicional", doc.get("title"), doc.get("updated_at")))})


@router.get("/studies/{study_id}/xlsx")
async def study_xlsx(study_id: str, lang: str = "pt", user=Depends(current_user)) -> Response:
    from engines.bet_core.brand import from_branding
    from engines.tradicional.xlsx import xlsx
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    b = from_branding(await _branding(user["user_id"]), "PT")
    data = xlsx(st["resultado"], st["linhas"], st["totais"], b.hex, b.name if b.is_client else None, doc.get("title"))
    fn = nom_document("Mapa-quantidades-tradicional", doc.get("title"), doc.get("updated_at"), ext="xlsx")
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": content_disposition(fn)})


@router.get("/studies/{study_id}/viewer")
async def study_viewer(study_id: str, lang: str = "pt", user=Depends(current_user)) -> Response:
    """Visualizador 3D autónomo (HTML único, funciona sem internet)."""
    from engines.bet_core.brand import from_branding
    from engines.tradicional.viewer import html_viewer
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    b = from_branding(await _branding(user["user_id"]), "PT")
    return Response(content=html_viewer(st["resultado"], doc.get("title"), "#" + b.hex, b.name if b.is_client else None),
                    media_type="text/html; charset=utf-8")


@router.get("/studies/{study_id}/render")
async def study_render(study_id: str, user=Depends(current_user)) -> Response:
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    out = await _render(doc, st, user["user_id"])
    if not out:
        raise HTTPException(503, "Render indisponível neste servidor")
    return Response(content=out[0][1], media_type="image/png")


@router.get("/studies/{study_id}/result")
async def study_result(study_id: str, user=Depends(current_user)) -> dict:
    """Resultado completo do motor (elementos dimensionados com geometria e armaduras) — para integrações e para o editor."""
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    r = st["resultado"]
    return {k: r[k] for k in ("pilares", "vigas", "sapatas", "vigasFundacao", "vergas", "lajes", "coberturas", "paredes", "terreo", "extras", "avisos",
                              "hipoteses", "estudo")}


@router.delete("/studies/{study_id}")
async def delete_study(study_id: str, user=Depends(current_user)) -> dict:
    r = await db.trad_studies.delete_one({"study_id": study_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Estudo não encontrado")
    return {"ok": True}
