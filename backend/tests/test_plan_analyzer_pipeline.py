"""Teste de integração: pipeline `analyze_plan` com Aurora mockado.

Valida num único teste (motor client fica preso ao primeiro event loop):
  - Extração DXF real do fixture + persistência
  - Extração PDF real do fixture + persistência
  - Fallback 503 quando Aurora devolve texto vazio 3× seguidas

Corre com: `cd /app/backend && python -m pytest tests/test_plan_analyzer_pipeline.py -v -s`
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from engines.aurora_contract import AURORA_ANSWER_SCHEMA, AuroraCompanyAnswer


FIXTURES = Path(__file__).parent / "fixtures"


MOCK_AURORA_JSON = """{
  "plan_summary": {"type": "planta baixa", "area_total_m2": 180, "num_divisoes": 8, "escala": "1:100", "descricao": "T3"},
  "measurements": {"paredes_ml": 45.5, "portas_un": 8, "janelas_un": 6, "divisoes": ["sala","cozinha","q1","q2","q3","wc1","wc2","corredor"]},
  "works": [
    {"designation": "Alvenaria tijolo 30", "category": "Alvenaria", "unit": "m2", "quantity": 120, "notes": ""},
    {"designation": "Pladur 100mm", "category": "Pladur", "unit": "m2", "quantity": 60, "notes": ""},
    {"designation": "Pintura interior", "category": "Pintura", "unit": "m2", "quantity": 380, "notes": ""}
  ],
  "risks_and_notes": ["Verificar cotas em obra", "Confirmar isolamento térmico"]
}"""


def _make_answer(text: str) -> AuroraCompanyAnswer:
    return AuroraCompanyAnswer(
        schema=AURORA_ANSWER_SCHEMA,
        text=text,
        model="gpt-5.6-luna",
        route="openai/gpt-5.6-luna",
        mode="reasoning",
    )


@pytest.mark.anyio
async def test_analyze_plan_pipeline_full():
    """Executa DXF, PDF e fallback 503 em sequência (mesmo event loop)."""
    from core.db import db
    from engines import plan_analyzer

    assert (FIXTURES / "plan_test.dxf").exists()
    assert (FIXTURES / "plan_test.pdf").exists()
    dxf_bytes = (FIXTURES / "plan_test.dxf").read_bytes()
    pdf_bytes = (FIXTURES / "plan_test.pdf").read_bytes()

    # Limpeza inicial
    await db.plan_analyses.delete_many(
        {"project_id": {"$in": ["prj_test_pipeline_dxf", "prj_test_pipeline_pdf", "prj_test_503"]}}
    )

    fake_sync = AsyncMock(return_value=None)
    fake_ask_ok = AsyncMock(return_value=(
        _make_answer(MOCK_AURORA_JSON),
        {"attempts": 1, "ok": True, "last_status": 200, "schema": AURORA_ANSWER_SCHEMA,
         "model": "gpt-5.6-luna", "route": "openai/gpt-5.6-luna", "mode": "reasoning"},
    ))
    fake_ask_empty = AsyncMock(return_value=(
        None,
        {"attempts": 3, "ok": False, "last_status": 200, "error": "empty_text_after_retries"},
    ))

    # --- 1) DXF ---
    with patch("engines.plan_analyzer.sync_project_to_aurora", fake_sync), \
         patch("engines.aurora_client.AuroraCompanyClient.ask_with_retry", fake_ask_ok):
        payload, status = await plan_analyzer.analyze_plan(
            file_bytes=dxf_bytes,
            filename="plan_test.dxf",
            project_id="prj_test_pipeline_dxf",
            plan_type="planta baixa",
            project_doc={"project_id": "prj_test_pipeline_dxf", "user_id": "user_test"},
            db=db, user_id="user_test",
        )
    assert status == 200, f"DXF status={status}: {payload}"
    assert payload["status"] == "completed"
    assert payload["analysis_id"].startswith("an_")
    assert payload["plan_summary"]["area_total_m2"] == 180
    assert len(payload["quote"]["priced_works"]) + len(payload["quote"]["unpriced_works"]) == 3
    assert payload["extraction_summary"]["source_ext"] == ".dxf"
    assert payload["extraction_summary"]["dxf_entities"] == 7

    dxf_id = payload["analysis_id"]
    doc = await db.plan_analyses.find_one({"analysis_id": dxf_id}, {"_id": 0})
    assert doc is not None, "DXF: doc não encontrado em plan_analyses"
    assert doc["file_type"] == "dxf"
    assert doc["file_size"] == len(dxf_bytes)
    assert doc["aurora"]["schema"] == AURORA_ANSWER_SCHEMA
    assert doc["extraction"]["dxf"]["bbox"]["width"] == 12.0
    print(f"\n[OK-DXF] analysis_id={dxf_id} entities={doc['extraction']['dxf']['num_entities']} bbox_width=12.0")

    # --- 2) PDF ---
    with patch("engines.plan_analyzer.sync_project_to_aurora", fake_sync), \
         patch("engines.aurora_client.AuroraCompanyClient.ask_with_retry", fake_ask_ok):
        payload, status = await plan_analyzer.analyze_plan(
            file_bytes=pdf_bytes,
            filename="plan_test.pdf",
            project_id="prj_test_pipeline_pdf",
            plan_type="planta baixa",
            project_doc={"project_id": "prj_test_pipeline_pdf", "user_id": "user_test"},
            db=db, user_id="user_test",
        )
    assert status == 200, f"PDF status={status}: {payload}"
    assert payload["extraction_summary"]["source_ext"] == ".pdf"
    assert (payload["extraction_summary"]["pdf_pages"] or 0) >= 1
    pdf_id = payload["analysis_id"]
    doc = await db.plan_analyses.find_one({"analysis_id": pdf_id}, {"_id": 0})
    assert doc is not None
    assert doc["file_type"] == "pdf"
    assert doc["extraction"]["pdf"]["num_pages"] >= 1
    print(f"[OK-PDF] analysis_id={pdf_id} pages={doc['extraction']['pdf']['num_pages']} chars={doc['extraction']['pdf']['chars_extracted']}")

    # --- 3) 503 gracioso ---
    with patch("engines.plan_analyzer.sync_project_to_aurora", fake_sync), \
         patch("engines.aurora_client.AuroraCompanyClient.ask_with_retry", fake_ask_empty):
        payload, status = await plan_analyzer.analyze_plan(
            file_bytes=dxf_bytes,
            filename="plan_test.dxf",
            project_id="prj_test_503",
            plan_type="planta baixa",
            project_doc={"project_id": "prj_test_503", "user_id": "user_test"},
            db=db, user_id="user_test",
        )
    assert status == 503
    assert payload["status"] == "analysis_unavailable"
    assert payload["aurora_meta"]["error"] == "empty_text_after_retries"
    # Não deve ter sido criado registo
    doc = await db.plan_analyses.find_one({"project_id": "prj_test_503"}, {"_id": 0})
    assert doc is None
    print("[OK-503] Aurora empty_text_after_retries → 503 gracioso, sem insert.")

    # --- 4) Confirmar contagem plan_analyses ---
    total = await db.plan_analyses.count_documents(
        {"project_id": {"$in": ["prj_test_pipeline_dxf", "prj_test_pipeline_pdf"]}}
    )
    assert total == 2, f"Esperado 2 docs, encontrado {total}"
    print(f"[OK-COUNT] plan_analyses recebeu 2 docs (DXF + PDF).")

    # Limpeza final
    await db.plan_analyses.delete_many(
        {"project_id": {"$in": ["prj_test_pipeline_dxf", "prj_test_pipeline_pdf", "prj_test_503"]}}
    )
