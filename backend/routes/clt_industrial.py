"""Private CLT measurement, company rates and cost control."""
from __future__ import annotations

import asyncio
import hashlib
import os
import secrets
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, StringConstraints
from pymongo.errors import DuplicateKeyError

from bim_studio.clt_access import allowed
from bim_studio.clt_costs import CostLot, Rate, summary
from bim_studio.clt_economics import (ELECTRICITY_URL, EstimateInput, LibraryItem, Parameter, estimate,
                                      library_merged, lot_from_estimate, merged, parse_eurostat,
                                      read_table_file, rows_to_items)
from bim_studio.store import get_db, now, tenant_of
from core.permissions import require_feature
from core.security import pro_required

router = APIRouter(prefix="/clt-industrial", tags=["clt-industrial"])
MAX_BYTES = 15 * 1024 * 1024
Coordinate = Annotated[float, Field(ge=-10_000_000, le=10_000_000, allow_inf_nan=False)]
Ring = Annotated[list[tuple[Coordinate, Coordinate]], Field(min_length=4, max_length=4097)]
Thickness = Annotated[float, Field(gt=0, le=1500, allow_inf_nan=False)]


async def viewer(user=Depends(pro_required)):
    if not allowed(user):
        raise HTTPException(404, "Piloto CLT indisponível.")
    return user


async def editor(user=Depends(viewer)):
    require_feature(user, "devis")
    return user


@router.get("/config")
async def configuration(user=Depends(viewer)):
    return {"enabled": True, "dwg": os.getenv("APS_DWG_ENABLED") == "true"}


async def _upload(file):
    data = await file.read(MAX_BYTES + 1)
    if not data or len(data) > MAX_BYTES:
        raise HTTPException(413, "Envie um ficheiro com até 15 MB.")
    return data


@router.post("/pdf")
async def pdf_evidence(file: UploadFile = File(...), user=Depends(editor)):
    from bim_studio.clt_pdf import inspect_pdf
    from fitz import FileDataError

    try:
        return await asyncio.to_thread(inspect_pdf, await _upload(file), include_review_images=True)
    except (ValueError, FileDataError) as exc:
        raise HTTPException(422, "PDF inválido ou fora dos limites da análise.") from exc


def _model_ifc(data):
    import tempfile

    import fitz
    from bim_studio.clt_model3d import build
    from bim_studio.clt_pdf import inspect_pdf

    extras = inspect_pdf(data)["estimate_extras"]
    if not extras:
        raise ValueError("Modelo 3D disponível só para desenhos revistos.")
    with fitz.open(stream=data, filetype="pdf") as doc:
        model, _ = build(doc, extras)
    with tempfile.NamedTemporaryFile(suffix=".ifc") as tmp:
        model.write(tmp.name)
        return open(tmp.name, "rb").read()


@router.post("/pdf/model3d")
async def pdf_model3d(file: UploadFile = File(...), user=Depends(editor)):
    from fitz import FileDataError

    try:
        result = await asyncio.to_thread(_model_ifc, await _upload(file))
    except (ValueError, FileDataError) as exc:
        raise HTTPException(422, str(exc) if "revistos" in str(exc) else "PDF inválido ou fora dos limites da análise.") from exc
    return Response(result, media_type="application/x-step",
                    headers={"Content-Disposition": 'attachment; filename="modelo-clt.ifc"', "Cache-Control": "no-store"})


@router.post("/pdf/preview")
async def pdf_preview(file: UploadFile = File(...), page: int = Form(..., ge=1, le=30), user=Depends(editor)):
    from bim_studio.clt_pdf import render_page
    from fitz import FileDataError

    try:
        result = await asyncio.to_thread(render_page, await _upload(file), page)
    except (ValueError, FileDataError) as exc:
        raise HTTPException(422, "Folha indisponível.") from exc
    return Response(result, media_type="image/png", headers={"Cache-Control": "no-store"})


@router.post("/cad")
async def cad_quantities(
    file: UploadFile = File(...),
    panel_layer: str = Form(..., min_length=1, max_length=120),
    opening_layer: str | None = Form(None, max_length=120),
    thickness_mm: Thickness = Form(...),
    user=Depends(editor),
):
    from bim_studio.clt_cad import measure_dxf
    from ezdxf import DXFError

    data = await _upload(file)
    source_hash = hashlib.sha256(data).hexdigest()
    filename = (file.filename or "").lower()
    provider = "dxf"
    if filename.endswith(".dwg"):
        from engines.autodesk_client import AutodeskError
        from engines.autodesk_dwg import convert

        if os.getenv("APS_DWG_ENABLED") != "true":
            raise HTTPException(503, "Conversão Autodesk APS indisponível.")
        try:
            data, _ = await convert(data, user_id=user["user_id"])
        except AutodeskError as exc:
            if exc.code == "conversion_pending":
                raise HTTPException(409, "A Autodesk ainda está a converter o desenho. Volte a consultar.")
            raise HTTPException(502, "Conversão Autodesk APS indisponível ou desenho inválido.") from exc
        provider = "autodesk-aps"
    elif not filename.endswith(".dxf"):
        raise HTTPException(415, "Envie um DWG ou DXF.")
    try:
        panels = await asyncio.to_thread(measure_dxf, data, panel_layer, opening_layer, thickness_mm)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (DXFError, OSError, UnicodeError) as exc:
        raise HTTPException(422, "Não foi possível ler o DXF.") from exc
    return {"provider": provider, "sha256": source_hash, "dxf_sha256": hashlib.sha256(data).hexdigest(),
            "thickness_mm": thickness_mm, "panels": panels, "status": "review_required",
            "fabrication_ready": False}


class PanelInput(BaseModel):
    outline: Ring
    openings: list[Ring] = Field(default_factory=list, max_length=100)
    thickness_mm: Thickness
    reference_volume_m3: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    zero_tolerance_m3: float = Field(default=0, ge=0, le=1, allow_inf_nan=False)
    source_reference: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=250)]


@router.post("/panel")
async def measure_panel(body: PanelInput, user=Depends(editor)):
    from bim_studio.clt_geometry import panel_quantities, reconciliation

    try:
        result = await asyncio.to_thread(panel_quantities, body.outline, body.openings, body.thickness_mm)
        check = None if body.reference_volume_m3 is None else reconciliation(
            result["net_volume_m3"], body.reference_volume_m3, zero_tolerance=body.zero_tolerance_m3)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {**result, "source_reference": body.source_reference, "reconciliation": check,
            "status": "review_required", "fabrication_ready": False}


@router.get("/rates")
async def list_rates(
    kind: Literal["compra", "producao", "venda"] | None = None,
    limit: int = Query(100, ge=1, le=300),
    skip: int = Query(0, ge=0),
    user=Depends(viewer),
):
    scope = {"tenant_id": tenant_of(user), "owner_id": user["user_id"]}
    if kind:
        scope["kind"] = kind
    rates = await get_db().clt_rates.find(scope, {"_id": 0, "tenant_id": 0, "owner_id": 0}).sort(
        [("effective_from", -1), ("rate_id", 1)]).skip(skip).limit(limit).to_list(limit)
    return {"items": rates}


@router.post("/rates", status_code=201)
async def create_rate(body: Rate, user=Depends(editor)):
    tenant = tenant_of(user)
    rate = body.model_dump(mode="json")
    key = f"{tenant}:{user['user_id']}:{rate['kind']}:{rate['code']}:{rate['unit']}:{rate['effective_from']}"
    rate.update(rate_id=hashlib.sha256(key.encode()).hexdigest(), created_at=now(), created_by=user["user_id"])
    try:
        await get_db().clt_rates.insert_one({"_id": rate["rate_id"], "tenant_id": tenant, "owner_id": user["user_id"], **rate})
    except DuplicateKeyError as exc:
        raise HTTPException(409, "Já existe uma tarifa para este artigo, unidade e data.") from exc
    return rate


class LotWrite(CostLot):
    expected_revision: int = Field(default=0, ge=0)


@router.get("/lots")
async def list_lots(limit: int = Query(50, ge=1, le=200), skip: int = Query(0, ge=0), user=Depends(viewer)):
    docs = await get_db().clt_lots.find({"tenant_id": tenant_of(user), "owner_id": user["user_id"]},
                                     {"_id": 0, "tenant_id": 0, "owner_id": 0, "history": 0}).sort(
        [("updated_at", -1), ("lot_id", 1)]).skip(skip).limit(limit).to_list(limit)
    return {"items": docs}


async def _save_lot(lot_id, body, user):
    tenant = tenant_of(user)
    rate_ids = {line.rate_id for line in body.lines if line.rate_id}
    refs = {}
    if rate_ids:
        async for rate in get_db().clt_rates.find(
            {"_id": {"$in": list(rate_ids)}, "tenant_id": tenant, "owner_id": user["user_id"]}
        ):
            refs[rate["rate_id"]] = Rate.model_validate(rate)
    for line in body.lines:
        if line.rate_id:
            ref = refs.get(line.rate_id)
            if (not ref or ref.unit != line.unit or ref.rate_eur != line.rate_eur
                    or ref.kind != ("compra" if line.stage == "compra" else "producao")):
                raise HTTPException(422, f"A tarifa do artigo {line.code} não corresponde ao custo e unidade indicados.")
    store = get_db().clt_lots
    snapshot = body.model_dump(mode="json", exclude={"expected_revision"})
    doc = {**snapshot, "lot_id": lot_id, "revision": body.expected_revision + 1,
           "updated_at": now(), "updated_by": user["user_id"], "summary": summary(body)}
    if body.expected_revision == 0:
        try:
            await store.insert_one({"_id": lot_id, "tenant_id": tenant, "owner_id": user["user_id"], **doc, "history": []})
        except DuplicateKeyError as exc:
            raise HTTPException(409, "O lote já existe. Recarregue a página.") from exc
    else:
        scope = {"_id": lot_id, "tenant_id": tenant, "owner_id": user["user_id"], "revision": body.expected_revision}
        previous = await store.find_one(scope, {"_id": 0, "tenant_id": 0, "owner_id": 0, "history": 0})
        if not previous:
            raise HTTPException(409, "Lote indisponível ou versão desatualizada.")
        update = await store.update_one(scope, {"$set": doc, "$push": {
            "history": {"$each": [previous], "$slice": -20},
        }})
        if not update.modified_count:
            raise HTTPException(409, "O lote foi alterado. Recarregue a página.")
    return doc


@router.post("/lots", status_code=201)
async def create_lot(body: LotWrite, user=Depends(editor)):
    if body.expected_revision:
        raise HTTPException(422, "Um lote novo começa na revisão zero.")
    return await _save_lot("clt_" + secrets.token_hex(12), body, user)


@router.put("/lots/{lot_id}")
async def update_lot(lot_id: str, body: LotWrite, user=Depends(editor)):
    if not body.expected_revision:
        raise HTTPException(422, "Indique a revisão atual do lote.")
    return await _save_lot(lot_id, body, user)


@router.get("/parameters")
async def get_parameters(user=Depends(viewer)):
    doc = await get_db().clt_parameters.find_one({"_id": tenant_of(user)}) or {}
    return {"items": merged(doc.get("values")), "updated_at": doc.get("updated_at")}


@router.put("/parameters")
async def save_parameters(body: dict[str, Parameter], user=Depends(editor)):
    items = merged({})
    unknown = sorted(set(body) - set(items))
    if unknown:
        raise HTTPException(422, f"Parâmetros desconhecidos: {', '.join(unknown)}")
    values = {key: {**item.model_dump(mode="json"), "origin": item.origin} for key, item in body.items()}
    await get_db().clt_parameters.update_one({"_id": tenant_of(user)}, {"$set": {
        "values": values, "updated_at": now(), "updated_by": user["user_id"]}}, upsert=True)
    return {"items": merged(values)}


async def _library(user):
    doc = await get_db().clt_library.find_one({"_id": tenant_of(user)}) or {}
    return doc.get("items", {})


async def _store_library(user, changes):
    """Upsert or delete items atomically per code, keeping the other items."""
    sets = {f"items.{code}": value for code, value in changes.items()}
    await get_db().clt_library.update_one({"_id": tenant_of(user)}, {"$set": {
        **sets, "updated_at": now(), "updated_by": user["user_id"]}}, upsert=True)


@router.get("/library")
async def get_library(user=Depends(viewer)):
    from bim_studio.clt_economics import BASES, CATEGORIES

    return {"items": library_merged(await _library(user)),
            "categories": {k: v[0] for k, v in CATEGORIES.items()}, "bases": BASES}


@router.put("/library/{code}")
async def save_library_item(code: str, body: LibraryItem, user=Depends(editor)):
    if body.code != code.upper():
        raise HTTPException(422, "O código do URL e do artigo não coincidem.")
    item = body.model_dump(mode="json")
    await _store_library(user, {body.code: item})
    return {"items": library_merged(await _library(user))}


@router.delete("/library/{code}")
async def delete_library_item(code: str, user=Depends(editor)):
    await _store_library(user, {code.upper(): {"deleted": True}})
    return {"items": library_merged(await _library(user))}


class TablePaste(BaseModel):
    rows: list[list[str | float | int | None]] = Field(min_length=2, max_length=2000)
    save: bool = False


@router.post("/library/table")
async def library_table(body: TablePaste, user=Depends(editor)):
    """Rows pasted from Excel. With save=false returns the preview only."""
    try:
        items, errors = rows_to_items(body.rows)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if body.save and items:
        await _store_library(user, {item["code"]: item for item in items})
    return {"items": items, "errors": errors, "saved": bool(body.save and items)}


@router.post("/library/import")
async def library_import(file: UploadFile = File(...), user=Depends(editor)):
    """Excel, CSV or PDF price list → preview rows for confirmation."""
    data = await _upload(file)
    try:
        rows = await asyncio.to_thread(read_table_file, data, file.filename or "")
        items, errors = rows_to_items(rows)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - unreadable file
        raise HTTPException(422, "Não foi possível ler a tabela do ficheiro.") from exc
    return {"items": items, "errors": errors, "saved": False}


@router.post("/library/electricity/refresh")
async def refresh_electricity(band: Literal["MWH_LT20", "MWH20-499", "MWH500-1999", "MWH2000-19999",
                                            "MWH20000-69999", "MWH70000-149999"] = Query("MWH500-1999"),
                              geo: str = Query("PT", pattern=r"^[A-Z]{2}$"), user=Depends(editor)):
    import httpx

    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.get(ELECTRICITY_URL.format(geo=geo, band=band))
            response.raise_for_status()
            period, value = parse_eurostat(response.json())
    except (httpx.HTTPError, KeyError, ValueError) as exc:
        raise HTTPException(502, "O Eurostat não respondeu. Tente mais tarde ou introduza o preço.") from exc
    current = library_merged(await _library(user)).get("EN-ELETRICIDADE")
    item = {**(current or {"code": "EN-ELETRICIDADE", "category": "energia", "name": "Eletricidade da fábrica",
                           "unit": "kWh", "sale_eur": None, "basis": "kwh", "per_basis": "1"}),
            "cost_eur": str(value), "origin": "mercado", "effective_from": None,
            "source": f"Eurostat nrg_pc_205, {geo}, não doméstico {band}, sem impostos, {period} (atualizado automaticamente)"}
    item.pop("standard", None)
    await _store_library(user, {"EN-ELETRICIDADE": LibraryItem.model_validate(item).model_dump(mode="json")})
    return {"period": period, "eur_kwh": float(value), "items": library_merged(await _library(user))}


async def _estimate(body, user):
    # the last reviewed floors feed the Assistant's complete CLT study ("estudo_clt_completo")
    await get_db().clt_estimate_inputs.update_one({"_id": tenant_of(user)}, {"$set": {
        "body": body.model_dump(mode="json", include={"floors", "start", "start_mode"}), "updated_at": now(),
        "updated_by": user["user_id"]}}, upsert=True)
    doc = await get_db().clt_parameters.find_one({"_id": tenant_of(user)}) or {}
    return estimate(body, merged(doc.get("values")), library_merged(await _library(user)))


@router.post("/estimate")
async def estimate_costs(body: EstimateInput, user=Depends(viewer)):
    return await _estimate(body, user)


class EstimateLot(EstimateInput):
    lot_name: str = Field(min_length=1, max_length=120)


@router.post("/estimate/lot", status_code=201)
async def estimate_to_lot(body: EstimateLot, user=Depends(editor)):
    """Create the cost-tracking lot whose baseline is the full estimate."""
    result = await _estimate(body, user)
    lot = LotWrite.model_validate(lot_from_estimate(body.lot_name, result))
    return {"estimate": result, "lot": await _save_lot("clt_" + secrets.token_hex(12), lot, user)}
