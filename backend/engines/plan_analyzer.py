"""Pipeline análise de plantas: DWG/DXF/PDF → Aurora `/ask` → orçamento estimado.

Fluxo:
  1. Detecta tipo pelo nome do ficheiro.
  2. DWG → CloudConvert dwg_to_dxf → DXF bytes; DXF → usado direto; PDF → pypdf text.
  3. Extração compacta (~700 chars) para caber no budget Aurora `/ask` (~1200 chars).
  4. `ask_with_retry` (3 tentativas, backoff 1s/2s/4s). Se `mode=reasoning` falhar
     3× com texto vazio, o cliente devolve meta.ok=False e o endpoint responde 503.
  5. Parse JSON tolerante (`_extract_json_from_response`).
  6. Preçar via `price_works_from_library` (bibliotecas pessoal + partilhada PT-2026).
  7. Persistência em `db.plan_analyses`.
"""
from __future__ import annotations

import logging
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

from engines.aurora_analysis import (
    _extract_json_from_response,
    price_works_from_library,
)
from engines.aurora_client import (
    AuroraCompanyClient,
    AuroraConfig,
    AuroraKeyIdInvalid,
    AuroraNotConfigured,
)
from engines.aurora_sync import sync_project_to_aurora
from engines.dwg_convert import dwg_to_dxf
from engines.dwg_convert import is_configured as cloudconvert_configured
from engines.dxf_extractor import extract_dxf_summary, summarize_for_prompt

logger = logging.getLogger("aurora.plan_analyzer")

ALLOWED_EXTS = {".dwg", ".dxf", ".pdf"}
MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB
AURORA_MAX_INPUT_CHARS = 700


ASK_TEMPLATE_PLAN = """Perito construção civil PT. Analisa dados de planta {plan_type} e devolve APENAS JSON compacto (sem markdown):
{{"plan_summary":{{"type":"","area_total_m2":null,"num_divisoes":null,"escala":"","descricao":""}},"measurements":{{"paredes_ml":null,"portas_un":null,"janelas_un":null,"divisoes":[]}},"works":[{{"designation":"","category":"Estrutura|Alvenaria|Cobertura|Canalizacao|Eletricidade|Pladur|Pintura|Ceramica|Carpintaria|Piscinas|Isolamento|Vidros|AVAC|Exterior|Outros","unit":"m2|m3|un|ml|kg|forfait","quantity":0,"notes":""}}],"risks_and_notes":[]}}

Regras: PT-PT; quantity numérico.

Dados:
---
{data}
---

Só JSON."""


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _sanitize_filename(name: str) -> str:
    """Sanitize + limita tamanho. Preserva extensão."""
    stem = Path(name).stem
    ext = Path(name).suffix.lower()
    safe_stem = "".join(c for c in stem if c.isalnum() or c in ("-", "_"))[:60] or "plan"
    return f"{safe_stem}{ext}"


def _extract_pdf_text(pdf_bytes: bytes) -> tuple[str, int]:
    from pypdf import PdfReader
    reader = PdfReader(BytesIO(pdf_bytes))
    pages = [(p.extract_text() or "") for p in reader.pages]
    return "\n\n".join(pages).strip(), len(pages)


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
async def analyze_plan(
    *,
    file_bytes: bytes,
    filename: str,
    project_id: str,
    plan_type: str,
    project_doc: dict[str, Any] | None,
    db,
    user_id: str,
) -> tuple[dict[str, Any], int]:
    """Pipeline completo. Devolve (payload, http_status)."""
    if not file_bytes:
        return {"status": "invalid_file", "message": "Ficheiro vazio."}, 400
    if len(file_bytes) > MAX_FILE_BYTES:
        return {"status": "file_too_large",
                "message": f"Ficheiro > {MAX_FILE_BYTES // (1024*1024)} MB."}, 413

    filename = _sanitize_filename(filename)
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTS:
        return {"status": "unsupported_format",
                "message": "Aceita apenas .dwg, .dxf, .pdf."}, 400

    # Processamento in-memory — não persistimos o ficheiro no pod
    # (a análise final é guardada em MongoDB, não o binário original).

    # ---- Extração ------------------------------------------------------
    extraction: dict[str, Any] = {"source_ext": ext, "file_size": len(file_bytes)}
    plan_data_for_aurora = ""

    if ext == ".dxf":
        summary = extract_dxf_summary(file_bytes)
        extraction["dxf"] = summary
        plan_data_for_aurora = summarize_for_prompt(summary, max_chars=AURORA_MAX_INPUT_CHARS)

    elif ext == ".dwg":
        if not cloudconvert_configured():
            return {
                "status": "cloudconvert_unavailable",
                "message": "Conversão DWG indisponível. Envie o ficheiro em DXF ou PDF.",
            }, 503
        try:
            dxf_bytes = await dwg_to_dxf(file_bytes, filename=filename)
        except RuntimeError as e:
            logger.warning("dwg conversion failed for %s: %s", filename, e)
            return {"status": "dwg_conversion_failed",
                    "message": str(e)}, 502
        summary = extract_dxf_summary(dxf_bytes)
        extraction["dxf"] = summary
        extraction["dwg_converted_size"] = len(dxf_bytes)
        plan_data_for_aurora = summarize_for_prompt(summary, max_chars=AURORA_MAX_INPUT_CHARS)

    elif ext == ".pdf":
        try:
            text, num_pages = _extract_pdf_text(file_bytes)
        except Exception as e:  # noqa: BLE001
            return {"status": "pdf_parse_failed",
                    "message": f"Falha a ler PDF: {type(e).__name__}"}, 400
        extraction["pdf"] = {"num_pages": num_pages, "chars_extracted": len(text)}
        if len(text) < 60:
            return {
                "status": "pdf_no_text",
                "message": "O PDF parece ser composto por imagens (scan). "
                           "Envie um PDF com texto pesquisável.",
                "extraction": extraction,
            }, 422
        plan_data_for_aurora = text[:AURORA_MAX_INPUT_CHARS]

    # ---- Aurora --------------------------------------------------------
    if not AuroraConfig().configured:
        return {"status": "aurora_not_configured",
                "message": "Aurora não configurado."}, 503

    # Garantir que o projeto existe em Aurora (upsert idempotente)
    if project_doc:
        try:
            await sync_project_to_aurora(project_doc)
        except Exception as e:  # noqa: BLE001
            logger.debug("aurora sync pre-analyze failed (silenced): %s", type(e).__name__)

    try:
        client = AuroraCompanyClient()
    except (AuroraNotConfigured, AuroraKeyIdInvalid) as e:
        return {"status": "aurora_config_error", "message": str(e)}, 503

    question = ASK_TEMPLATE_PLAN.format(plan_type=plan_type, data=plan_data_for_aurora)
    logger.info("aurora plan analyze | prompt_len=%d file=%s ext=%s size=%d",
                len(question), filename, ext, len(file_bytes))

    answer, meta = await client.ask_with_retry(
        question=question, project_id=project_id, resources=[],
        max_attempts=3, base_delay=1.0,
    )

    if not meta.get("ok"):
        return {
            "status": "analysis_unavailable",
            "message": "Análise indisponível de momento. Tente novamente em alguns minutos.",
            "aurora_meta": {
                "attempts": meta.get("attempts"),
                "last_status": meta.get("last_status"),
                "error": meta.get("error"),
            },
        }, 503

    parsed = _extract_json_from_response(answer.text if answer else "")
    if not parsed:
        return {
            "status": "parse_failed",
            "message": "Resposta Aurora sem JSON válido.",
            "aurora_meta": {k: meta.get(k) for k in ("attempts", "schema", "model", "route")},
        }, 502

    works = parsed.get("works") or []
    quote = await price_works_from_library(works=works, db=db, user_id=user_id)

    # ---- Persistência --------------------------------------------------
    analysis_id = "an_" + uuid.uuid4().hex[:16]
    doc = {
        "analysis_id": analysis_id,
        "project_id": project_id,
        "user_id": user_id,
        "file_name": filename,
        "file_type": ext.lstrip("."),
        "file_size": len(file_bytes),
        "plan_type": plan_type,
        "uploaded_at": time.time(),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "extraction": extraction,
        "aurora": {
            "attempts": meta.get("attempts"),
            "schema": meta.get("schema"),
            "model": meta.get("model"),
            "route": meta.get("route"),
        },
        "plan_summary": parsed.get("plan_summary"),
        "measurements": parsed.get("measurements"),
        "risks_and_notes": parsed.get("risks_and_notes") or [],
        "quote": quote,
        "status": "completed",
    }
    await db.plan_analyses.insert_one(dict(doc))
    doc.pop("_id", None)

    return {
        "status": "completed",
        "analysis_id": analysis_id,
        "plan_summary": doc["plan_summary"],
        "measurements": doc["measurements"],
        "risks_and_notes": doc["risks_and_notes"],
        "quote": doc["quote"],
        "extraction_summary": {
            "source_ext": ext,
            "file_size": len(file_bytes),
            "dxf_entities": (extraction.get("dxf") or {}).get("num_entities"),
            "pdf_pages": (extraction.get("pdf") or {}).get("num_pages"),
        },
        "aurora_meta": {"attempts": meta.get("attempts"), "model": meta.get("model")},
    }, 200
