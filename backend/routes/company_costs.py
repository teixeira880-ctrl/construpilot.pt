"""Recursos e custos da empresa (mão de obra por função, veículos, máquinas, gasóleo, custos de estrutura) e dossier
económico de um orçamento (custo, venda, margem, meios, planeamento, cenários) — documento interno, PDF premium."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import pro_required

router = APIRouter(tags=["company-costs"])


class ResourceIn(BaseModel):
    id: str = Field(min_length=1, max_length=40)
    kind: Literal["mao_de_obra", "veiculo", "maquina"] = "mao_de_obra"
    name: str = Field(min_length=1, max_length=80)
    unit: Literal["h", "dia", "km", "mes"] = "h"
    cost: float = Field(ge=0, le=100000)
    consumption_l_100km: float | None = Field(default=None, ge=0, le=200)


class ParamsIn(BaseModel):
    fuel_price_l: float | None = Field(default=None, ge=0, le=10)
    overhead_pct: float | None = Field(default=None, ge=0, le=100)
    hours_per_day: float | None = Field(default=None, gt=0, le=24)
    km_per_day: float | None = Field(default=None, ge=0, le=2000)
    labour_share_pct: float | None = Field(default=None, ge=0, le=100)
    target_margin_pct: float | None = Field(default=None, ge=0, le=90)
    supervision_h_week: float | None = Field(default=None, ge=0, le=80)
    truck_days_pct: float | None = Field(default=None, ge=0, le=100)
    digger_days_pct: float | None = Field(default=None, ge=0, le=100)
    team: dict[str, float] | None = None
    vehicles: dict[str, float] | None = None
    machines: dict[str, float] | None = None


class CostsIn(BaseModel):
    resources: list[ResourceIn] = Field(default_factory=list, max_length=80)
    params: ParamsIn = Field(default_factory=ParamsIn)


async def _country(uid: str) -> str:
    u = await db.users.find_one({"user_id": uid}, {"_id": 0, "brand_country": 1, "country": 1}) or {}
    return "FR" if str(u.get("brand_country") or u.get("country") or "PT").upper() == "FR" else "PT"


async def company_costs(uid: str) -> dict:
    from engines import economic_dossier as E
    saved = await db.company_cost_resources.find_one({"user_id": uid}, {"_id": 0})
    return {**E.merge(saved, await _country(uid)), "saved": bool(saved)}


@router.get("/company/cost-resources")
async def get_costs(user=Depends(pro_required)) -> dict:
    return await company_costs(user["user_id"])


@router.put("/company/cost-resources")
async def put_costs(body: CostsIn, user=Depends(pro_required)) -> dict:
    params = {k: v for k, v in body.params.model_dump().items() if v is not None}
    await db.company_cost_resources.update_one(
        {"user_id": user["user_id"]},
        {"$set": {"user_id": user["user_id"], "resources": [r.model_dump() for r in body.resources], "params": params,
                  "updated_at": datetime.now(timezone.utc).isoformat()}}, upsert=True)
    return await company_costs(user["user_id"])


@router.get("/documents/{doc_id}/economic-dossier")
async def economic_dossier(doc_id: str, format: str = "pdf", user=Depends(pro_required)):
    from engines import economic_dossier as E
    doc = await db.pro_documents.find_one({"doc_id": doc_id, "user_id": user["user_id"], "doc_type": "quote"}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Orçamento não encontrado")
    purchase = await db.library_items.find({"user_id": user["user_id"], "cost_price_ht": {"$gt": 0}},
                                           {"_id": 0, "designation": 1, "unit": 1, "cost_price_ht": 1}).to_list(5000)
    country = await _country(user["user_id"])
    r = E.compute(doc, await company_costs(user["user_id"]), purchase, country)
    if format == "json":
        return {k: v for k, v in r.items() if k not in ("resources",)}
    from routes.company_page import pdf_customization
    from routes.plans_common import _resolve_branding
    branding = {**(await _resolve_branding(user["user_id"]) or {}), **await pdf_customization(user["user_id"])}
    from core.ui_lang import explicit_ui_lang
    lang = "fr-FR" if (explicit_ui_lang() == "fr" or country == "FR") else "pt"
    from engines import economic_dossier_pdf
    import asyncio
    pdf = await asyncio.to_thread(economic_dossier_pdf.build, r, branding, lang)
    name = f"Dossier_economico_{(doc.get('number') or doc_id)}.pdf"
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{name}"'})
