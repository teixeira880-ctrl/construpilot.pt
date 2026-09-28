"""Endpoints admin para servir documentos técnicos internos (PDF).

- `GET /api/docs/aurora-master-spec.pdf` — serve o master spec Aurora.
- `GET /api/docs/aurora-master-spec.md` — serve a fonte Markdown (útil para diff).
- `POST /api/docs/aurora-master-spec/rebuild` — regenera o PDF a partir do MD.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse

from core.security import admin_user

router = APIRouter(prefix="/docs", tags=["docs"], dependencies=[Depends(admin_user)])

DOCS_DIR = Path("/app/docs")
MD_PATH = DOCS_DIR / "aurora_master_spec.md"
PDF_PATH = DOCS_DIR / "aurora_master_spec.pdf"


@router.get("/aurora-master-spec.pdf", summary="Master Spec Aurora (PDF)")
async def aurora_master_spec_pdf() -> FileResponse:
    """Devolve o PDF final `aurora_master_spec.pdf` (admin-only).

    Se o ficheiro não existir, tenta regenerar a partir do MD antes de servir.
    """
    if not PDF_PATH.exists():
        try:
            from scripts.build_aurora_pdf import build_pdf
            build_pdf()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(500, f"Falha ao gerar PDF: {type(e).__name__}: {e}")
    return FileResponse(
        path=str(PDF_PATH),
        media_type="application/pdf",
        filename="aurora_master_spec.pdf",
        headers={
            "Content-Disposition": 'inline; filename="aurora_master_spec.pdf"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.get("/aurora-master-spec.md", summary="Master Spec Aurora (Markdown)",
            response_class=PlainTextResponse)
async def aurora_master_spec_md() -> PlainTextResponse:
    if not MD_PATH.exists():
        raise HTTPException(404, "Fonte MD não encontrada.")
    return PlainTextResponse(
        content=MD_PATH.read_text(encoding="utf-8"),
        media_type="text/markdown; charset=utf-8",
    )


@router.post("/aurora-master-spec/rebuild", summary="Regenerar PDF a partir do MD")
async def rebuild_aurora_master_spec_pdf() -> dict:
    """Regenera o PDF a partir do MD atual. Útil após edições ao ficheiro fonte."""
    try:
        from scripts.build_aurora_pdf import build_pdf
        build_pdf()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(500, f"Falha ao gerar PDF: {type(e).__name__}: {e}")
    size_kb = PDF_PATH.stat().st_size / 1024
    return {"ok": True, "pdf_path": str(PDF_PATH), "size_kb": round(size_kb, 1)}
