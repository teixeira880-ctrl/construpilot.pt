"""Rotas /api/plans-pro/* — Autodesk APS + Cascade IA PT.

Endpoints:
  - POST /api/plans-pro/upload              — DWG/RVT/IFC → upload OSS + translate
  - GET  /api/plans-pro/{plan_id}/status    — polling do estado da translation
  - GET  /api/plans-pro/{plan_id}/viewer-token — token assinado para Viewer SDK
  - POST /api/plans-pro/{plan_id}/analyze   — lança análise IA
  - GET  /api/plans-pro/{plan_id}/analysis  — resultado estruturado
  - GET  /api/plans-pro/history             — lista últimos planos
"""
from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import BaseModel

from core.db import db
from core.security import current_user
from engines.plans_pro import autodesk_client
from engines.plans_pro.excel_export import IVA_RATES_PT, build_workbook
from engines.plans_pro.plan_metadata import aggregate_quantities
from engines.plans_pro.plan_vision import full_analysis
from engines.plans_pro.semantic.exceptions import (
    AutodeskError as SemAutodeskError,
    SchemaValidationError,
    VisionAnalysisError,
)
from engines.plans_pro.semantic.schemas import AnalisePlanta, MissingDataRequest

logger = logging.getLogger("plans_pro.routes")

router = APIRouter(prefix="/plans-pro", tags=["plans-pro"])


ACCEPT_EXT = {".dwg", ".dxf", ".rvt", ".ifc", ".nwc", ".nwd", ".pdf"}
MAX_SIZE = 100 * 1024 * 1024  # 100 MB


def _plan_id() -> str:
    return f"pln_{uuid.uuid4().hex[:14]}"


def _ext(name: str) -> str:
    return ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""


# ---------------------------------------------------------------------------
# Config check
# ---------------------------------------------------------------------------
@router.get("/config")
async def config_status(user=Depends(current_user)):
    """Devolve estado de configuração (sem credentials)."""
    return {
        "autodesk_configured": autodesk_client.is_configured(),
        "accepted_extensions": sorted(ACCEPT_EXT),
        "max_size_mb": MAX_SIZE // (1024 * 1024),
    }


# ---------------------------------------------------------------------------
# Upload + translate
# ---------------------------------------------------------------------------
async def _translate_and_poll(plan_id: str, urn: str) -> None:
    """Background: trigger translate + polling manifest até terminar."""
    async def _upd(**fields):
        fields["updated_at"] = datetime.now(timezone.utc).isoformat()
        await db.plans_pro.update_one({"plan_id": plan_id}, {"$set": fields})

    try:
        await autodesk_client.translate(urn)
        await _upd(translation_status="inprogress", progress="20%")

        # Polling (máx 15 min, intervalo 5s crescente)
        for i in range(180):
            await asyncio.sleep(5)
            try:
                m = await autodesk_client.manifest(urn)
            except Exception as e:  # noqa: BLE001
                logger.warning("manifest poll err %s: %s", plan_id, e)
                continue
            status = (m.get("status") or "").lower()
            progress = m.get("progress") or ""
            await _upd(translation_status=status or "inprogress", progress=progress or f"{min(20 + i, 95)}%")
            if status in ("success", "failed", "timeout"):
                break
        final = await autodesk_client.manifest(urn)
        await _upd(translation_status=final.get("status") or "unknown",
                   progress="100%", manifest=final)
    except Exception as e:  # noqa: BLE001
        logger.exception("translate falhou %s", plan_id)
        await _upd(translation_status="failed", error=str(e)[:300])


@router.post("/upload")
async def upload(
    background: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str | None = Form(None),
    user=Depends(current_user),
):
    if not autodesk_client.is_configured():
        raise HTTPException(503, "Autodesk APS não configurado neste servidor.")
    filename = file.filename or "plan"
    ext = _ext(filename)
    if ext not in ACCEPT_EXT:
        raise HTTPException(400, f"Formato não suportado ({ext}). Aceites: {', '.join(sorted(ACCEPT_EXT))}")
    data = await file.read()
    if not data:
        raise HTTPException(400, "Ficheiro vazio.")
    if len(data) > MAX_SIZE:
        raise HTTPException(400, f"Ficheiro demasiado grande (máx {MAX_SIZE // (1024 * 1024)} MB).")

    try:
        up = await autodesk_client.upload_object(filename, data)
    except Exception as e:  # noqa: BLE001
        logger.exception("upload Autodesk falhou")
        raise HTTPException(502, f"Autodesk upload falhou: {type(e).__name__}") from None

    plan_id = _plan_id()
    doc = {
        "plan_id": plan_id,
        "user_id": user["user_id"],
        "project_id": project_id,
        "file_name": filename,
        "file_type": ext.lstrip("."),
        "size_bytes": len(data),
        "autodesk_urn": up["urn"],
        "oss_object_key": up["object_key"],
        "oss_bucket": up["bucket"],
        "translation_status": "pending",
        "progress": "10%",
        "ai_analysis": None,
        "model_used": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.plans_pro.insert_one(doc)
    background.add_task(_translate_and_poll, plan_id, up["urn"])
    doc.pop("_id", None)
    return doc


# ---------------------------------------------------------------------------
# Status / viewer token
# ---------------------------------------------------------------------------
@router.get("/{plan_id}/status")
async def status(plan_id: str, user=Depends(current_user)):
    doc = await db.plans_pro.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "manifest": 0, "ai_analysis": 0},
    )
    if not doc:
        raise HTTPException(404, "Plano não encontrado.")
    return doc


@router.get("/{plan_id}/viewer-token")
async def viewer_token(plan_id: str, user=Depends(current_user)):
    doc = await db.plans_pro.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "autodesk_urn": 1, "translation_status": 1},
    )
    if not doc:
        raise HTTPException(404, "Plano não encontrado.")
    try:
        tok = await autodesk_client.viewer_token()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(503, f"Autodesk token falhou: {type(e).__name__}") from None
    return {
        "urn": doc.get("autodesk_urn"),
        "access_token": tok["access_token"],
        "expires_in": tok["expires_in"],
        "token_type": tok["token_type"],
    }


# ---------------------------------------------------------------------------
# Analyze (IA cascade)
# ---------------------------------------------------------------------------
class AnalyzeIn(BaseModel):
    project_hint: str | None = None
    include_web_norms: bool = True


class AnalyzeResponse(BaseModel):
    """Contrato de saída oficial de ``POST /api/plans-pro/{plan_id}/analyze``.

    Expõe o schema ``AnalisePlanta`` (e ``MissingDataRequest``) no
    OpenAPI (``/api/openapi.json#/components/schemas``) para que
    front-end e testes possam gerar tipos a partir do contrato real.
    """

    plan_id: str
    analise: AnalisePlanta
    missing_data: list[MissingDataRequest]
    requires_human_review: bool
    trace: dict[str, float | int | str | bool | None]
    quantities: dict[str, float | int | str | None]
    views_count: int


@router.post("/{plan_id}/analyze", response_model=AnalyzeResponse)
async def analyze(plan_id: str, body: AnalyzeIn, user=Depends(current_user)):
    """Executa a cascade IA — Fase 1 blindada.

    Devolve HTTP 200 mesmo quando `missing_data` não está vazio: o
    frontend precisa de mostrar modal ao utilizador em vez de 400.
    """
    doc = await db.plans_pro.find_one({"plan_id": plan_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Plano não encontrado.")
    if doc.get("translation_status") != "success":
        raise HTTPException(409, "Translation ainda não terminada ou falhou.")
    urn = doc["autodesk_urn"]

    # 1. Metadata APS
    try:
        meta = await autodesk_client.metadata(urn)
    except Exception as e:  # excepção legacy do autodesk_client
        logger.exception("metadata APS falhou (plan=%s)", plan_id)
        raise HTTPException(
            status_code=502,
            detail=f"Autodesk metadata indisponível: {type(e).__name__}",
        ) from None
    views = ((meta.get("data") or {}).get("metadata") or [])

    # Quantities (fonte determinística para cross-check)
    categories_views: list[dict] = []
    manifest = doc.get("manifest") or {}
    for d in (manifest.get("derivatives") or []):
        for child in (d.get("children") or []):
            cats = child.get("categories") or []
            layers = child.get("layers") or []
            if cats or layers:
                categories_views.append({"categories": cats, "layers": layers})
    quantities = aggregate_quantities(categories_views) if categories_views else {}

    # 2. Thumbnail (opcional)
    thumb: bytes | None = None
    try:
        thumb = await autodesk_client.thumbnail(urn)
    except Exception as e:  # noqa: BLE001 — thumbnail é opcional
        logger.exception("thumbnail APS indisponível (plan=%s)", plan_id)
        thumb = None

    # 3. Cascade IA tipada
    try:
        analise = await full_analysis(
            plan_id=plan_id,
            filename=doc["file_name"],
            metadata={"quantities": quantities, "views": views},
            thumbnail_bytes=thumb,
            thumbnail_mime="image/png",
            project_hint=body.project_hint,
            include_web_norms=body.include_web_norms,
        )
    except VisionAnalysisError:
        # Todos os providers LLM falharam HTTP/vazio
        logger.exception("vision analysis falhou totalmente (plan=%s)", plan_id)
        raise HTTPException(
            status_code=503,
            detail="Provedores IA indisponíveis — tente novamente em instantes.",
        ) from None
    except SchemaValidationError:
        # Já tratado no full_analysis (embalado como MissingDataRequest),
        # este bloco é defesa em profundidade.
        logger.exception("schema validation inesperada (plan=%s)", plan_id)
        raise HTTPException(
            status_code=502,
            detail="Resposta IA inválida — contacte o suporte.",
        ) from None
    except SemAutodeskError:
        logger.exception("erro Autodesk tipado (plan=%s)", plan_id)
        raise HTTPException(
            status_code=502,
            detail="Erro Autodesk APS — tente novamente.",
        ) from None

    # 4. Persistir — novo contrato + wrapper legacy mínimo para Excel export
    analise_dump = analise.model_dump(mode="json")
    legacy_wrapper = {
        "synthesis": {
            # Vazio por design em Fase 1 (sem ouvrages ainda).
            # Excel export produz orçamento com totais a 0 sem crashar.
            "ouvrages": [],
            "normas_aplicaveis": [],
            "resumo": None,
        },
        "analise": analise_dump,
    }
    thumb_b64 = base64.b64encode(thumb).decode() if thumb else None
    update = {
        "ai_analysis": legacy_wrapper,
        "quantities": quantities,
        "views_count": len(views),
        "thumbnail_b64": thumb_b64,
        "model_used": analise.trace.get("providers_used"),
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.plans_pro.update_one({"plan_id": plan_id}, {"$set": update})

    # Novo contrato de resposta (breaking change — ver relatório Fase 1)
    return {
        "plan_id": plan_id,
        "analise": analise_dump,
        "missing_data": [md.model_dump(mode="json") for md in analise.missing_data],
        "requires_human_review": analise.requires_human_review,
        "trace": analise.trace,
        "quantities": quantities,
        "views_count": len(views),
    }


@router.get("/{plan_id}/analysis")
async def get_analysis(plan_id: str, user=Depends(current_user)):
    doc = await db.plans_pro.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "manifest": 0},
    )
    if not doc:
        raise HTTPException(404, "Plano não encontrado.")
    if not doc.get("ai_analysis"):
        raise HTTPException(409, "Análise ainda não foi executada. Chame /analyze primeiro.")
    return doc


# ---------------------------------------------------------------------------
# Excel export
# ---------------------------------------------------------------------------
@router.get("/{plan_id}/export-excel")
async def export_excel(
    plan_id: str,
    iva_rate: str = Query("23", description="Taxa IVA PT: 23 | 22 | 16 | 6 | 0"),
    user=Depends(current_user),
):
    """Gera orçamento Excel .xlsx a partir da análise IA do plano."""
    if str(iva_rate) not in IVA_RATES_PT:
        raise HTTPException(400, f"iva_rate inválido. Aceites: {sorted(IVA_RATES_PT)}")
    doc = await db.plans_pro.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0, "manifest": 0, "thumbnail_b64": 0},
    )
    if not doc:
        raise HTTPException(404, "Plano não encontrado.")
    if not doc.get("ai_analysis"):
        raise HTTPException(409, "Análise IA ainda não foi executada. Chame /analyze primeiro.")

    try:
        # Fetch branding do utilizador (NIF, logo, morada)
        branding = await db.users.find_one(
            {"user_id": user["user_id"]},
            {"_id": 0, "brand_company_name": 1, "brand_nif": 1, "brand_address": 1,
             "brand_city": 1, "brand_postal": 1, "brand_contact_line": 1,
             "brand_logo_b64": 1, "organization_id": 1},
        ) or {}
        # Override com org branding se pertence a org
        if branding.get("organization_id"):
            org = await db.organizations.find_one(
                {"org_id": branding["organization_id"]},
                {"_id": 0, "brand_company_name": 1, "brand_nif": 1, "brand_address": 1,
                 "brand_city": 1, "brand_postal": 1, "brand_contact_line": 1,
                 "brand_logo_b64": 1},
            )
            if org:
                for k, v in org.items():
                    if v:
                        branding[k] = v
        data, meta = build_workbook(plan_doc=doc, iva_rate=str(iva_rate), branding=branding)
    except Exception as e:  # noqa: BLE001
        logger.exception("Excel export falhou %s", plan_id)
        raise HTTPException(500, f"Falha ao gerar Excel: {type(e).__name__}") from None

    stem = (doc.get("file_name") or "orcamento").rsplit(".", 1)[0][:40].replace('"', "")
    filename = f"orcamento_{stem}_{meta['numero_orc']}.xlsx"
    return Response(
        content=data,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "private, no-store",
            "X-Orc-Numero": meta["numero_orc"],
            "X-Orc-Total-HT": str(meta["totals"]["total_ht_eur"]),
            "X-Orc-Total-TTC": str(meta["totals"]["total_ttc_eur"]),
        },
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------
@router.get("/history/list")
async def history(limit: int = 20, user=Depends(current_user)):
    limit = max(1, min(int(limit or 20), 100))
    items = await db.plans_pro.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "manifest": 0, "thumbnail_b64": 0, "ai_analysis.synthesis.ouvrages": 0},
    ).sort("created_at", -1).to_list(limit)
    return {"items": items}
