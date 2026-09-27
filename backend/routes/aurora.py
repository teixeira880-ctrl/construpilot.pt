"""Aurora · rotas de análise de documentos (PC, plantas DWG/DXF/PDF)."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from core.db import db
from core.security import current_user
from engines.aurora_analysis import (
    analyze_pc_document,
    price_works_from_library,
)
from engines.plan_analyzer import analyze_plan
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pypdf import PdfReader


router = APIRouter(prefix="/aurora", tags=["aurora"])


MAX_PDF_BYTES = 20 * 1024 * 1024
MIN_TEXT_CHARS = 100


# ---------------------------------------------------------------------------
# Fase 1 · /analyze-pc — versão produção-ready (retry + fallback 503)
# ---------------------------------------------------------------------------
@router.post("/analyze-pc")
async def analyze_pc(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    user=Depends(current_user),
) -> dict[str, Any]:
    """Upload PDF do Permis de Construire → texto → Aurora `/ask` → preçário."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "PDF vazio.")
    if len(content) > MAX_PDF_BYTES:
        raise HTTPException(413, "PDF demasiado grande (máx 20 MB).")

    try:
        reader = PdfReader(BytesIO(content))
        pages_text = [(p.extract_text() or "") for p in reader.pages]
    except Exception as e:  # noqa: BLE001
        raise HTTPException(400, f"Falha ao ler PDF: {type(e).__name__}") from None

    text = "\n\n".join(pages_text).strip()
    num_pages = len(pages_text)

    if len(text) < MIN_TEXT_CHARS:
        return {
            "status": "pdf_no_text",
            "message": "O PDF parece ser composto por imagens (scan). "
                       "Envie um PDF com texto pesquisável.",
            "num_pages": num_pages, "chars_extracted": len(text),
        }

    user_id = user.get("user_id") or user.get("id")

    # Garantir upsert em Aurora antes do /ask
    from engines.aurora_client import AuroraConfig
    from engines.aurora_sync import sync_project_to_aurora
    if AuroraConfig().configured:
        proj_doc = await db.projects.find_one(
            {"project_id": project_id, "user_id": user_id}, {"_id": 0},
        )
        if not proj_doc:
            raise HTTPException(404, "Projeto não encontrado.")
        await sync_project_to_aurora(proj_doc)

    result = await analyze_pc_document(text=text, project_id=project_id)
    if not result.get("ok"):
        # Fallback gracioso — HTTP 503 se Aurora indisponível
        return {
            "status": "analysis_unavailable",
            "message": "Análise indisponível de momento. Tente novamente em alguns minutos.",
            "error": result.get("error"),
            "num_pages": num_pages, "chars_extracted": len(text),
        }

    analysis = result["analysis"] or {}
    works = analysis.get("works") or []
    quote = await price_works_from_library(works=works, db=db, user_id=user_id)

    return {
        "status": "completed",
        "num_pages": num_pages,
        "chars_extracted": len(text),
        "project_summary": analysis.get("project_summary"),
        "risks_and_notes": analysis.get("risks_and_notes", []),
        "quote": quote,
        "aurora": result.get("aurora"),
    }


# ---------------------------------------------------------------------------
# Fase 2 · Plantas (DWG/DXF/PDF)
# ---------------------------------------------------------------------------
@router.post("/projects/{project_id}/plans/analyze")
async def analyze_project_plan(
    project_id: str,
    file: UploadFile = File(...),
    plan_type: str = Form("planta baixa"),
    user=Depends(current_user),
) -> dict[str, Any]:
    """Upload de planta (DWG/DXF/PDF) → extração → Aurora → orçamento."""
    user_id = user.get("user_id") or user.get("id")
    proj_doc = await db.projects.find_one(
        {"project_id": project_id, "user_id": user_id}, {"_id": 0},
    )
    if not proj_doc:
        raise HTTPException(404, "Projeto não encontrado.")

    content = await file.read()
    payload, status = await analyze_plan(
        file_bytes=content,
        filename=file.filename or "plan.dxf",
        project_id=project_id,
        plan_type=plan_type,
        project_doc=proj_doc,
        db=db,
        user_id=user_id,
    )
    if status >= 400:
        raise HTTPException(status, detail=payload)
    return payload


@router.get("/projects/{project_id}/plans/analyses")
async def list_project_plan_analyses(
    project_id: str,
    user=Depends(current_user),
) -> dict[str, Any]:
    """Lista todas as análises de plantas de um projeto do utilizador."""
    user_id = user.get("user_id") or user.get("id")
    # verificar ownership
    proj = await db.projects.find_one(
        {"project_id": project_id, "user_id": user_id}, {"_id": 0, "project_id": 1},
    )
    if not proj:
        raise HTTPException(404, "Projeto não encontrado.")
    cursor = db.plan_analyses.find(
        {"project_id": project_id, "user_id": user_id},
        {"_id": 0, "extraction": 0, "aurora": 0},
    ).sort("uploaded_at", -1).limit(50)
    items = await cursor.to_list(length=None)
    return {"project_id": project_id, "count": len(items), "items": items}


@router.get("/plans/analyses/{analysis_id}")
async def get_plan_analysis(
    analysis_id: str,
    user=Depends(current_user),
) -> dict[str, Any]:
    """Detalhe completo de uma análise (incluindo extração DXF/PDF e aurora meta)."""
    user_id = user.get("user_id") or user.get("id")
    doc = await db.plan_analyses.find_one(
        {"analysis_id": analysis_id, "user_id": user_id}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Análise não encontrada.")
    return doc
