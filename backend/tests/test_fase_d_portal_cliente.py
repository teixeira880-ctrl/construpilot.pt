"""Testes do portal cliente final (Fase D).

Cobertura num único event loop (evita problemas de motor+anyio entre testes):
    * Criação do link mágico (`POST /orcamentos/{id}/public-link`).
    * Leitura pública sanitizada (`GET /public/orcamentos/{token}`).
    * PDF público (`GET /public/orcamentos/{token}/pdf`).
    * Expiração (410 Gone).
    * Token inválido (404).
    * `convidar_cliente_portal=true` na tool `criar_orcamento`.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import app  # noqa: E402  (carrega .env + regista rotas)

from httpx import ASGITransport, AsyncClient  # noqa: E402

from engines.btp_assistant.tools.executors import exec_criar_orcamento  # noqa: E402
from engines.btp_assistant.types import ToolCall  # noqa: E402


def _criar_token_auth(user_id: str) -> str:
    from core.security import make_jwt
    return make_jwt(user_id, version=0)


def _async_client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver")


async def _criar_user_e_orcamento(user_id: str) -> str:
    from core.db import db
    await db.users.update_one(
        {"user_id": user_id},
        {"$setOnInsert": {
            "user_id": user_id, "email": f"{user_id}@t.pt",
            "role": "pro", "token_version": 0,
        }},
        upsert=True,
    )
    oid = f"orc_test_{uuid.uuid4().hex[:8]}"
    await db.btp_assistant_orcamentos.insert_one({
        "orcamento_id": oid, "user_id": user_id,
        "cliente_nome": "Silva & Filhos",
        "cliente_email": "silva@example.pt",
        "titulo": "Moradia T3 Lisboa",
        "items": [
            {"descricao": "Betão C25/30", "qtd": 10, "unidade": "m³", "preco_unit_eur": 95.0},
            {"descricao": "Aço A500NR ∅12", "qtd": 500, "unidade": "kg", "preco_unit_eur": 1.08},
        ],
        "iva_pct": 23.0,
        "subtotal_eur": 1490.0,
        "iva_eur": 342.7,
        "total_eur": 1832.7,
        "created_at_iso": datetime.now(timezone.utc).isoformat(),
        "source": "btp_assistant",
    })
    return oid


# ---------------------------------------------------------------------------
# Fluxo completo (todas as asserções num só event loop)
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_fluxo_completo_portal_cliente_fase_d():
    user_id = f"u_test_{uuid.uuid4().hex[:6]}"
    oid = await _criar_user_e_orcamento(user_id)
    tok = _criar_token_auth(user_id)

    async with _async_client() as c:
        # 1. Criar link público sem envio de e-mail
        r = await c.post(
            f"/api/orcamentos/{oid}/public-link",
            json={"enviar_email": False},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["token"].startswith("mp_")
        assert data["url"].endswith(data["token"])
        assert data["email_enviado"] is False
        link_token = data["token"]

        # 2. Orçamento inexistente → 404
        r404 = await c.post(
            "/api/orcamentos/orc_nao_existe/public-link",
            json={"enviar_email": False},
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r404.status_code == 404

        # 3. Consultar público — devolve dados sanitizados (sem PII)
        r2 = await c.get(f"/api/public/orcamentos/{link_token}")
        assert r2.status_code == 200, r2.text
        pub = r2.json()
        assert pub["titulo"] == "Moradia T3 Lisboa"
        assert pub["cliente_nome"] == "Silva & Filhos"
        assert pub["numero"] == oid
        assert len(pub["items"]) == 2
        assert pub["total_eur"] == pytest.approx(1832.7)
        assert "created_by_user_id" not in pub
        assert "user_id" not in pub

        # 4. Token inexistente → 404
        r_404_tok = await c.get("/api/public/orcamentos/mp_nao_existe_xyz")
        assert r_404_tok.status_code == 404

        # 5. PDF público — devolve application/pdf + magic bytes
        r_pdf = await c.get(f"/api/public/orcamentos/{link_token}/pdf")
        assert r_pdf.status_code == 200, r_pdf.text
        assert r_pdf.headers["content-type"].startswith("application/pdf")
        assert r_pdf.content.startswith(b"%PDF")
        assert len(r_pdf.content) > 1500

        # 6. Link expirado → 410 Gone
        from core.db import db
        tok_exp = f"mp_expired_{uuid.uuid4().hex[:12]}"
        await db.orcamento_public_links.insert_one({
            "token": tok_exp, "orcamento_id": oid,
            "created_by_user_id": user_id, "cliente_email": None,
            "created_at": datetime.now(timezone.utc) - timedelta(days=100),
            "expires_at": datetime.now(timezone.utc) - timedelta(days=1),
            "viewed_count": 0, "last_viewed_at": None,
        })
        r_exp = await c.get(f"/api/public/orcamentos/{tok_exp}")
        assert r_exp.status_code == 410


# ---------------------------------------------------------------------------
# Tool `criar_orcamento` com `convidar_cliente_portal=true`
# ---------------------------------------------------------------------------
@pytest.mark.anyio
async def test_tool_criar_orcamento_com_convite_portal_gera_link():
    user_id = f"u_test_{uuid.uuid4().hex[:6]}"
    call = ToolCall(
        id="tc1", name="criar_orcamento",
        arguments={
            "cliente_nome": "Costa Lda",
            "cliente_email": "costa@example.pt",
            "titulo": "Reabilitação Baixa Pombalina",
            "items": [
                {"descricao": "Reboco de cimento", "qtd": 100, "unidade": "m²", "preco_unit_eur": 7.5},
            ],
            "convidar_cliente_portal": True,
        },
    )
    result = await exec_criar_orcamento(call, user_id=user_id)
    assert result.status == "ok"
    assert "public_link_token" in result.payload
    assert result.payload["public_link_token"].startswith("mp_")
    assert "public_link_url" in result.payload
