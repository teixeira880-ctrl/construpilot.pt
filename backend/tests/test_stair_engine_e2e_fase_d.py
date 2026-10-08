"""Fase D · Stair Engine E2E — tool `calcular_escada` ligada ao motor real.

Cobertura:
    * `calculate_stair` com dados padrão (altura 2.70 m, pé-direito 2.70 m, 18 degraus auto)
      → dimensões coerentes (espelho 16-18 cm, cobertor 25-32 cm, inclinação 25-35°)
    * Fórmula de Blondel: `2h + g ∈ [60, 64]` cm
    * Tool `calcular_escada` devolve `analysis_id`, `pdf_url`, campos chave
    * Endpoint `GET /api/stair-engine/{analysis_id}/pdf` devolve PDF válido (magic %PDF)
"""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import app  # noqa: E402

from httpx import ASGITransport, AsyncClient  # noqa: E402


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


# ---------------------------------------------------------------------------
# 1. Motor directamente: dimensões coerentes + Blondel
# ---------------------------------------------------------------------------
def test_stair_engine_calculo_padrao_blondel_e_dimensoes():
    from engines.stair_engine import StairInputs, calculate_stair

    inp = StairInputs(
        altura_total_m=2.70, pe_direito_m=2.70,
        largura_m=1.0, num_degraus=None,
        uso="habitacao", material="betao",
    )
    r = calculate_stair(inp)
    dim = r["dimensoes"]
    assert 16.0 <= dim["altura_degrau_cm"] <= 18.0, f"espelho fora de 16-18 cm: {dim['altura_degrau_cm']}"
    assert 25.0 <= dim["profundidade_cobertor_cm"] <= 32.0, f"cobertor fora de 25-32 cm: {dim['profundidade_cobertor_cm']}"
    assert 60.0 <= dim["blondel"] <= 64.0, f"Blondel fora de 60-64 cm: {dim['blondel']}"
    assert 25.0 <= dim["inclinacao_graus"] <= 36.0, f"inclinação fora: {dim['inclinacao_graus']}°"
    assert dim["num_degraus"] >= 15, "nr de degraus insuficiente para 2.70 m"


# ---------------------------------------------------------------------------
# 2 + 3. Fluxo completo da tool `calcular_escada` + PDF endpoint (um único loop)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_fluxo_completo_tool_calcular_escada_e_pdf():
    from core.db import db
    from core.security import make_jwt
    from engines.btp_assistant.tools.executors import exec_calcular_escada
    from engines.btp_assistant.types import ToolCall

    user_id = f"u_test_stair_{uuid.uuid4().hex[:6]}"
    await db.users.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id, "email": f"{user_id}@t.pt",
            "role": "pro", "token_version": 0,
        }},
        upsert=True,
    )

    # a) Tool devolve payload com dimensões coerentes + analysis_id
    call = ToolCall(
        id="tc-stair", name="calcular_escada",
        arguments={
            "altura_total_m": 2.70, "pe_direito_m": 2.70, "largura_m": 1.0,
            "uso": "habitacao", "material": "betao",
        },
    )
    r = await exec_calcular_escada(call, user_id=user_id)
    assert r.status == "ok", f"status inesperado: {r.status} · {r.text_pt}"
    p = r.payload
    assert p["analysis_id"].startswith("stair_")
    assert p["pdf_url"].endswith("/pdf")
    assert 16.0 <= float(p["altura_degrau_cm"]) <= 18.0
    assert 25.0 <= float(p["cobertor_cm"]) <= 32.0
    assert 60.0 <= float(p["blondel_cm"]) <= 64.0

    # b) Endpoint PDF: chama a função directamente (evita problemas de event
    # loop com AsyncClient entre testes em suíte completa).
    from routes.stair_engine import pdf_por_analysis_id as _pdf_endpoint
    rpdf = await _pdf_endpoint(
        p["analysis_id"],
        user={"user_id": user_id, "sub": user_id, "role": "pro"},
    )
    assert rpdf.media_type == "application/pdf"
    assert rpdf.body.startswith(b"%PDF")
    assert len(rpdf.body) > 1500
