"""Rotas HTTP do Assistente BTP (Fase A).

Endpoints:
    * POST  /api/btp-assistant/chat           — SSE ou JSON
    * POST  /api/btp-assistant/confirm        — confirma acção pendente
    * GET   /api/btp-assistant/conversations/{id}
    * DELETE /api/btp-assistant/conversations/{id}
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.db import db
from core.rate_limit import limiter, plan_limit_fn
from core.security import current_user
from engines.btp_assistant.router import (
    route_user_request,
    route_user_request_sync,
)
from engines.btp_assistant.tools.executors import executar_tool_call
from engines.btp_assistant.types import Attachment, ToolCall

logger = logging.getLogger("btp_assistant.routes")

router = APIRouter(prefix="/btp-assistant", tags=["btp-assistant"])


# ---------------------------------------------------------------------------
# Entradas
# ---------------------------------------------------------------------------
class AttachmentIn(BaseModel):
    filename: str = Field(..., max_length=200)
    mime_type: str = Field(..., max_length=100)
    data_b64: str = Field(..., max_length=15_000_000)  # ~10 MB base64


class ChatIn(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    conversation_id: str | None = Field(default=None, max_length=80)
    stream: bool = Field(default=True)
    attachments: list[AttachmentIn] = Field(default_factory=list, max_length=6)


class ConfirmIn(BaseModel):
    conversation_id: str
    tool_call_id: str
    name: str
    arguments: dict[str, Any]
    confirmed: bool


# ---------------------------------------------------------------------------
# POST /chat
# ---------------------------------------------------------------------------
@router.post("/chat")
@limiter.limit(plan_limit_fn(free="20/hour", pro="120/hour", business="400/hour"))
async def chat(
    body: ChatIn,
    request: Request,
    user=Depends(current_user),
):
    """Entrada principal do agente. Retorna SSE (default) ou JSON."""
    attachments = [
        Attachment(**a.model_dump()) for a in body.attachments
    ]

    if body.stream:
        async def _sse():
            try:
                async for ev in route_user_request(
                    user_prompt=body.prompt, user_id=user["user_id"],
                    conversation_id=body.conversation_id,
                    attachments=attachments,
                ):
                    data = json.dumps(ev.model_dump(), ensure_ascii=False)
                    yield f"event: {ev.type}\ndata: {data}\n\n"
            except Exception as e:  # noqa: BLE001
                logger.exception("SSE /chat falhou")
                err = {"type": "error", "data": {
                    "message_pt": "Falha interna. Tente novamente.",
                    "detail": f"{type(e).__name__}",
                }}
                yield f"event: error\ndata: {json.dumps(err)}\n\n"

        return StreamingResponse(
            _sse(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    # Non-streaming
    try:
        resp = await route_user_request_sync(
            user_prompt=body.prompt, user_id=user["user_id"],
            conversation_id=body.conversation_id,
            attachments=attachments,
        )
    except Exception:
        logger.exception("chat non-streaming falhou")
        raise HTTPException(
            status_code=503,
            detail="Assistente temporariamente indisponível.",
        ) from None
    return resp.model_dump()


# ---------------------------------------------------------------------------
# POST /confirm — executa acção previamente autorizada
# ---------------------------------------------------------------------------
@router.post("/confirm")
async def confirm(body: ConfirmIn, user=Depends(current_user)):
    if not body.confirmed:
        return {"status": "cancelled", "tool_call_id": body.tool_call_id}
    call = ToolCall(
        id=body.tool_call_id, name=body.name, arguments=body.arguments,
        requires_user_confirmation=False,
    )
    result = await executar_tool_call(call, user_id=user["user_id"])
    return result.model_dump()


# ---------------------------------------------------------------------------
# GET /conversations/{id}
# ---------------------------------------------------------------------------
@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, user=Depends(current_user)):
    doc = await db.btp_assistant_conversations.find_one(
        {"conversation_id": conv_id, "user_id": user["user_id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Conversa não encontrada.")
    return doc


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, user=Depends(current_user)):
    r = await db.btp_assistant_conversations.delete_one(
        {"conversation_id": conv_id, "user_id": user["user_id"]},
    )
    return {"deleted": r.deleted_count}


# ---------------------------------------------------------------------------
# GET /orcamentos/{id}/excel  (gera on-demand)
# ---------------------------------------------------------------------------
@router.get("/orcamentos/{orc_id}/excel")
async def download_excel(orc_id: str, user=Depends(current_user)):
    """Gera Excel do orçamento criado pelo agente (lazy)."""
    doc = await db.btp_assistant_orcamentos.find_one(
        {"orcamento_id": orc_id, "user_id": user["user_id"]}, {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Orçamento não encontrado.")
    from io import BytesIO
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.title = "Orçamento"
    ws.append(["Cliente", doc.get("cliente_nome", "")])
    ws.append(["Título", doc.get("titulo", "")])
    ws.append([])
    ws.append(["Descrição", "Qtd", "Unidade", "Preço Unit. (EUR)", "Total (EUR)"])
    for it in doc.get("items") or []:
        qtd = float(it.get("qtd") or 0)
        pu = float(it.get("preco_unit_eur") or 0)
        ws.append([it.get("descricao", ""), qtd, it.get("unidade", ""), pu, qtd * pu])
    ws.append([])
    ws.append(["Subtotal", doc.get("subtotal_eur", 0.0)])
    ws.append([f"IVA {doc.get('iva_pct', 23)}%", doc.get("iva_eur", 0.0)])
    ws.append(["Total", doc.get("total_eur", 0.0)])
    buf = BytesIO()
    wb.save(buf)
    buf.seek(0)
    from fastapi.responses import Response
    nome = f"orcamento_{orc_id}.xlsx"
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )
