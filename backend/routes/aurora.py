"""Aurora · rotas de análise de documentos (PC, futuro: plantas)."""
from __future__ import annotations

from io import BytesIO
from typing import Any

from core.db import db
from core.security import current_user
from engines.aurora_analysis import (
    analyze_pc_document,
    price_works_from_library,
)
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pypdf import PdfReader


router = APIRouter(prefix="/aurora", tags=["aurora"])


MAX_PDF_BYTES = 20 * 1024 * 1024  # 20 MB
MIN_TEXT_CHARS = 100


@router.post("/analyze-pc")
async def analyze_pc(
    file: UploadFile = File(...),
    project_id: str = Form(...),
    user=Depends(current_user),
) -> dict[str, Any]:
    """Upload de PDF do Permis de Construire → texto extraído → Aurora `/ask`
    → lookup preços na biblioteca ConstruPilot (pessoal + partilhada PT-2026).
    """
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
            "ok": False,
            "error": "pc_sem_texto",
            "hint": (
                "O PDF parece ser composto por imagens (scan). "
                "OCR ainda não implementado nesta fase — envie um PDF com "
                "texto pesquisável, ou faça OCR primeiro."
            ),
            "chars_extracted": len(text),
            "num_pages": num_pages,
        }

    # 1) Garantir que o projeto existe em Aurora (upsert síncrono antes do /ask)
    from engines.aurora_client import AuroraConfig
    from engines.aurora_sync import sync_project_to_aurora
    if AuroraConfig().configured:
        proj_doc = await db.projects.find_one(
            {"project_id": project_id, "user_id": user.get("user_id") or user.get("id")},
            {"_id": 0},
        )
        if not proj_doc:
            raise HTTPException(404, "Projeto não encontrado.")
        sync_res = await sync_project_to_aurora(proj_doc)
        if not sync_res:
            # Não bloquear — o Aurora `/ask` pode ainda funcionar se o projeto já existir
            pass

    # 2) Aurora ask
    result = await analyze_pc_document(text=text, project_id=project_id)
    if not result.get("ok"):
        return {**result, "chars_extracted": len(text), "num_pages": num_pages}

    analysis = result["analysis"] or {}
    works = analysis.get("works") or []

    # Preçar
    quote = await price_works_from_library(
        works=works, db=db, user_id=user.get("user_id") or user.get("id"),
    )

    return {
        "ok": True,
        "num_pages": num_pages,
        "chars_extracted": len(text),
        "project_summary": analysis.get("project_summary"),
        "risks_and_notes": analysis.get("risks_and_notes", []),
        "quote": quote,
        "aurora": result.get("aurora"),
        "_debug_raw_snippet": result.get("_raw_answer_text"),
        "_debug_analysis_keys": list(analysis.keys()) if analysis else [],
    }
