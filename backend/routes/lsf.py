"""Rotas « Estrutura em aço leve — LSF » (ofertas Pro e Pro Business).

Sem IA: o motor é determinístico e parte da geometria já lida e validada no módulo Plantas (ou de um projeto LSF JSON).
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
from engines.lsf import VERSAO, estudo
from engines.lsf import adapter as A
from engines.lsf import defaults as D
from engines.lsf import quantities as Q

router = APIRouter(prefix="/lsf", tags=["lsf"], dependencies=[Depends(require_level("pro"))])

from routes.auth import current_user  # noqa: E402
from engines.nom_fichier import content_disposition, nom_document  # noqa: E402

MAX_INPUT = 3_000_000


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sid() -> str:
    return "lsf_" + uuid.uuid4().hex[:12]


class LevelIn(BaseModel):
    page_index: int = 0
    name: str | None = None
    elevation_m: float | None = None
    height_m: float | None = 2.7
    origin: list[float] | None = None


class FromPlanIn(BaseModel):
    plan_id: str
    country: str | None = "pt"
    levels: list[LevelIn] = Field(default_factory=list)
    options: dict = Field(default_factory=dict)
    title: str | None = None


class FromInputIn(BaseModel):
    input: dict
    title: str | None = None


class ProjectIn(BaseModel):
    project: dict


class VerifIn(BaseModel):
    parametros: dict = Field(default_factory=dict)   # chaves de engines.lsf.verificacao.PARAMETROS (zona de vento, cargas…)


class PriceIn(BaseModel):
    mercado: bool = False          # procurar preços de mercado online para as linhas sem preço (assinalados « a analisar »)


def _resumo(st: dict) -> dict:
    r = st["resultado"]
    e = r["estudo"]
    return {"kg_aco": round(e["kgAco"], 1), "pecas": e["nMembros"], "parafusos": e["nParafusos"], "kg_m2": e.get("kgPorM2"),
            "area_pisos_m2": e.get("areaPisos"), "avisos": len(r["avisos"]), "total_eur": st["totais"]["total"],
            "linhas_sem_preco": st["totais"]["linhas_sem_preco"], "verificacao": (r.get("verificacao") or {}).get("resumo")}


def _calc(project: dict, biblioteca: list | None = None, lang: str = "pt") -> dict:
    try:
        return estudo(project, biblioteca, lang)
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Projeto LSF incoerente: {exc}")


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
    return doc


async def _save(uid: str, project: dict, title: str, plan_id: str | None = None) -> dict:
    st = _calc(project, await _biblioteca(uid))
    doc = {"study_id": _sid(), "user_id": uid, "plan_id": plan_id, "title": title[:160], "created_at": _now(), "updated_at": _now(),
           "version": 1, "engine_version": VERSAO, "project": project, "summary": _resumo(st), "lines": st["linhas"], "totals": st["totais"],
           "warnings": st["resultado"]["avisos"], "assumptions": st["resultado"]["hipoteses"], "reading": project.get("leitura"),
           "verification": st["resultado"].get("verificacao")}
    await db.lsf_studies.insert_one({**doc})
    return _public(doc)


async def _get(study_id: str, uid: str) -> dict:
    doc = await db.lsf_studies.find_one({"study_id": study_id, "user_id": uid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Estudo não encontrado")
    return doc


@router.get("/exemplo")
async def exemplo() -> dict:
    """Projeto LSF de exemplo (moradia R/C + 1.º andar) — ponto de partida para um projeto sem planta."""
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
    if body.title:
        project["nome"] = body.title
    return await _save(user["user_id"], project, body.title or f"Estrutura LSF — {plan.get('filename') or ''}", body.plan_id)


@router.post("/studies/from-input")
async def create_from_input(body: FromInputIn, user=Depends(current_user)) -> dict:
    """Entrada = projeto LSF (perimetros/paredes/pisos/coberturas) OU entrada MEP (levels/rooms/openings em m)."""
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
    return await _save(user["user_id"], project, body.title or project.get("nome") or "Estrutura LSF")


@router.get("/studies")
async def list_studies(user=Depends(current_user)) -> dict:
    rows = await db.lsf_studies.find({"user_id": user["user_id"]}, {"_id": 0, "study_id": 1, "title": 1, "plan_id": 1, "summary": 1,
                                                                    "created_at": 1, "updated_at": 1, "version": 1}).sort("updated_at", -1).to_list(100)
    return {"studies": rows}


@router.get("/studies/{study_id}")
async def get_study(study_id: str, user=Depends(current_user)) -> dict:
    return _public(await _get(study_id, user["user_id"]))


@router.put("/studies/{study_id}/project")
async def update_project(study_id: str, body: ProjectIn, user=Depends(current_user)) -> dict:
    """O profissional ajusta o projeto (perfis, espaçamentos, vãos, cotas, regras…): tudo é recalculado."""
    doc = await _get(study_id, user["user_id"])
    st = _calc(body.project, await _biblioteca(user["user_id"]))
    patch = {"project": body.project, "summary": _resumo(st), "lines": st["linhas"], "totals": st["totais"], "warnings": st["resultado"]["avisos"],
             "assumptions": st["resultado"]["hipoteses"], "updated_at": _now(), "version": int(doc.get("version", 1)) + 1,
             "render_png_b64": None, "verification": st["resultado"].get("verificacao")}
    await db.lsf_studies.update_one({"study_id": study_id, "user_id": user["user_id"]}, {"$set": patch})
    return _public({**doc, **patch})


@router.get("/studies/{study_id}/verificacao")
async def get_verification(study_id: str, user=Depends(current_user)) -> dict:
    """Verificação estrutural indicativa (NP EN 1990/1991/1993-1-3) recalculada a partir do projeto guardado."""
    from engines.lsf.verificacao import PARAMETROS
    doc = await _get(study_id, user["user_id"])
    v = doc.get("verification")
    if not v or v.get("versao") is None:
        v = _calc(doc["project"], await _biblioteca(user["user_id"]))["resultado"]["verificacao"]
    return {"verificacao": v, "parametros_padrao": PARAMETROS, "parametros": doc["project"].get("verificacao") or {}}


@router.put("/studies/{study_id}/verificacao")
async def set_verification(study_id: str, body: VerifIn, user=Depends(current_user)) -> dict:
    """Altera os parâmetros da verificação (zonas, cargas, coeficientes, resistências do fabricante) e recalcula tudo."""
    from engines.lsf.verificacao import PARAMETROS
    doc = await _get(study_id, user["user_id"])
    desconhecidos = sorted(set(body.parametros) - set(PARAMETROS))
    if desconhecidos:
        raise HTTPException(422, f"Parâmetros desconhecidos: {', '.join(desconhecidos)}")
    project = {**doc["project"], "verificacao": {**(doc["project"].get("verificacao") or {}), **body.parametros}}
    return await update_project(study_id, ProjectIn(project=project), user)


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
    await db.lsf_studies.update_one({"study_id": study_id, "user_id": user["user_id"]},
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
        from engines.lsf.render import render
        out = await asyncio.to_thread(render, st["resultado"], None, 1600, 900, 64, False, 150)
    except Exception:  # noqa: BLE001 — sem Mitsuba: sem render
        return []
    if out:
        await db.lsf_studies.update_one({"study_id": doc["study_id"], "user_id": uid}, {"$set": {"render_png_b64": base64.b64encode(out[0][1]).decode()}})
    return out[:1]


@router.get("/studies/{study_id}/pdf")
async def study_pdf(study_id: str, lang: str = "pt", user=Depends(current_user)) -> Response:
    from engines.lsf.pdf import dossier
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    ren = await _render(doc, st, user["user_id"])
    pdf = await asyncio.to_thread(dossier, st["resultado"], st["linhas"], st["totais"], lang if lang in ("pt", "fr", "en", "uk") else "pt",
                                  await _branding(user["user_id"]), ren, doc.get("title"))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": content_disposition(nom_document("Estudo-LSF", doc.get("title"), doc.get("updated_at")))})


@router.get("/studies/{study_id}/xlsx")
async def study_xlsx(study_id: str, lang: str = "pt", user=Depends(current_user)) -> Response:
    from engines.bet_core.brand import from_branding
    from engines.lsf.xlsx import xlsx
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    b = from_branding(await _branding(user["user_id"]), "PT")
    data = xlsx(st["resultado"], st["linhas"], st["totais"], lang, b.hex, b.name if b.is_client else None, doc.get("title"))
    fn = nom_document("Mapa-quantidades-LSF", doc.get("title"), doc.get("updated_at"), ext="xlsx")
    return Response(content=data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": content_disposition(fn)})


@router.get("/studies/{study_id}/viewer")
async def study_viewer(study_id: str, lang: str = "pt", user=Depends(current_user)) -> Response:
    """Visualizador 3D autónomo (HTML único, funciona sem internet)."""
    from engines.bet_core.brand import from_branding
    from engines.lsf.viewer import html_viewer
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    b = from_branding(await _branding(user["user_id"]), "PT")
    return Response(content=html_viewer(st["resultado"], doc.get("title"), lang, "#" + b.hex, b.name if b.is_client else None),
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
    """Resultado completo do motor (peças com geometria, placas, planos de corte) — para integrações e para o editor."""
    doc = await _get(study_id, user["user_id"])
    st = await _full(doc, user["user_id"])
    r = st["resultado"]
    return {"perfis": r["perfis"], "placas": r["placasResumo"], "parafusos": r["parafusos"], "ancoragens": r["ancoragens"], "extras": r["extras"],
            "paredes": r["paredes"], "avisos": r["avisos"], "hipoteses": r["hipoteses"], "estudo": r["estudo"],
            "verificacao": r.get("verificacao"),
            "membros": [{k: m[k] for k in ("id", "grupo", "ref", "nivel", "tipoPeca", "perfilNome", "L", "kg") if k in m} for m in r["membros"]]}


@router.delete("/studies/{study_id}")
async def delete_study(study_id: str, user=Depends(current_user)) -> dict:
    r = await db.lsf_studies.delete_one({"study_id": study_id, "user_id": user["user_id"]})
    if not r.deleted_count:
        raise HTTPException(404, "Estudo não encontrado")
    return {"ok": True}
