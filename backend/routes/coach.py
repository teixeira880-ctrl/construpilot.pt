"""Rota HTTP do Coach IA (Aurora exclusivo).

Endpoint principal: `POST /api/coach/ask` (JSON, não-streaming).
Endpoint auxiliar: `GET /api/coach/conversations/{conversation_id}` (histórico).

Nunca chama Emergent LLM — apenas Aurora Company API V1.
"""
import logging
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.db import db
from core.rate_limit import (
    TOTAL_LIMITS,
    WEB_LIMITS,
    limiter,
    plan_limit_fn,
    user_plan,
    web_search_remaining,
)
from core.security import current_user, current_user_with_state
from engines.coach_ai import (
    CoachUnavailableError,
    coach_ask,
)

router = APIRouter(prefix="/coach", tags=["coach"])
logger = logging.getLogger("coach.route")

HISTORY_FETCH_LIMIT = 20


class CoachAskIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    project_id: str | None = None
    conversation_id: str | None = None
    use_web_search: bool | None = None  # None=auto, True=sempre, False=nunca


def _new_conversation_id() -> str:
    return "conv_" + uuid.uuid4().hex[:14]


def _new_message_id() -> str:
    return "msg_" + uuid.uuid4().hex[:14]


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


@router.post("/ask")
@limiter.limit(plan_limit_fn(free="20/hour", pro="60/hour", business="120/hour"))
async def coach_ask_endpoint(
    request: Request,
    response: Response,
    body: CoachAskIn,
    user=Depends(current_user_with_state),
) -> dict[str, Any]:
    """Envia pergunta ao Coach IA (Aurora).

    - Persiste msg utilizador em `coach_messages` mesmo se Aurora falhar.
    - Persiste msg assistente **apenas** se Aurora responder com texto.
    - Retorna 503 estruturado se ambos os modos Aurora falharem
      (o email admin já foi despachado dentro de `coach_ask`).
    """
    user_id = user.get("user_id") or user.get("id")
    if not user_id:
        raise HTTPException(401, "Utilizador inválido.")

    conversation_id = body.conversation_id or _new_conversation_id()

    # Histórico da conversa (para o prompt Aurora)
    history: list[dict[str, Any]] = []
    if body.conversation_id:
        cursor = db.coach_messages.find(
            {"conversation_id": conversation_id, "user_id": user_id},
            {"_id": 0, "role": 1, "content": 1, "ts": 1},
        ).sort("ts", 1).limit(HISTORY_FETCH_LIMIT)
        history = await cursor.to_list(length=None)

    # Persiste msg utilizador imediatamente (perguntas ficam registadas mesmo em falha)
    user_msg_id = _new_message_id()
    await db.coach_messages.insert_one({
        "message_id": user_msg_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "project_id": body.project_id,
        "role": "user",
        "content": body.message,
        "ts": _now_iso(),
    })

    # Chamar Aurora
    plan = user_plan(user)
    try:
        answer = await coach_ask(
            project_id=body.project_id,
            user_message=body.message,
            conversation_history=history,
            user_id=user_id,
            db=db,
            use_web_search=body.use_web_search,
            plan=plan,
        )
    except CoachUnavailableError as e:
        logger.warning(
            "coach unavailable | user=%s conversation=%s primary=%s fallback=%s",
            user_id[:12], conversation_id,
            e.primary_meta.get("error") or e.primary_meta.get("code"),
            e.fallback_meta.get("error") or e.fallback_meta.get("code"),
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "coach_unavailable",
                "message": (
                    "O assistente IA está temporariamente indisponível. "
                    "O administrador foi notificado. Tente novamente em alguns minutos."
                ),
                "conversation_id": conversation_id,
            },
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("coach unexpected error: %s", type(e).__name__)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "coach_unexpected",
                "message": "Erro inesperado no assistente IA.",
            },
        )

    # Persistir resposta do assistente
    assistant_msg_id = _new_message_id()
    meta = {
        "provider": answer.get("provider"),
        "model": answer.get("model"),
        "mode_used": answer.get("mode_used"),
        "request_id": answer.get("request_id"),
        "latency_ms": answer.get("latency_ms"),
        "web_enriched": answer.get("web_enriched"),
        "web_search_mode": answer.get("web_search_mode"),
        "web_search_reason": answer.get("web_search_reason"),
        "web_search_fallback": answer.get("web_search_fallback"),
        "citations": answer.get("citations") or [],
    }
    await db.coach_messages.insert_one({
        "message_id": assistant_msg_id,
        "conversation_id": conversation_id,
        "user_id": user_id,
        "project_id": body.project_id,
        "role": "assistant",
        "content": answer["text"],
        "ts": _now_iso(),
        "meta": meta,
    })

    # Headers de rate-limit (total + web) + plano
    total_limit = TOTAL_LIMITS.get("coach", {}).get(plan, 0)
    web_limit = WEB_LIMITS.get("coach", {}).get(plan, 0)
    web_remaining_v = web_search_remaining(user_id, plan, "coach", web_limit)
    response.headers["X-RateLimit-Flow"] = "coach"
    response.headers["X-RateLimit-Plan"] = plan
    response.headers["X-RateLimit-Limit-Total"] = str(total_limit)
    response.headers["X-RateLimit-Limit-Web"] = str(web_limit)
    response.headers["X-RateLimit-Remaining-Web"] = str(web_remaining_v)

    return {
        "reply": answer["text"],
        "conversation_id": conversation_id,
        "message_id": assistant_msg_id,
        "meta": meta,
        "rate_limit": {
            "plan": plan,
            "total_limit": total_limit,
            "web_limit": web_limit,
            "web_remaining": web_remaining_v,
        },
    }


@router.get("/conversations/{conversation_id}")
async def coach_history(
    conversation_id: str,
    user=Depends(current_user),
) -> dict[str, Any]:
    """Devolve histórico completo (max 200 msgs) de uma conversa do utilizador."""
    user_id = user.get("user_id") or user.get("id")
    cursor = db.coach_messages.find(
        {"conversation_id": conversation_id, "user_id": user_id},
        {"_id": 0},
    ).sort("ts", 1).limit(200)
    msgs = await cursor.to_list(length=None)
    return {"conversation_id": conversation_id, "count": len(msgs), "messages": msgs}


@router.get("/conversations")
async def coach_list_conversations(
    user=Depends(current_user),
) -> dict[str, Any]:
    """Lista conversas do utilizador (última msg + timestamp por conversa)."""
    user_id = user.get("user_id") or user.get("id")
    pipeline = [
        {"$match": {"user_id": user_id}},
        {"$sort": {"ts": -1}},
        {"$group": {
            "_id": "$conversation_id",
            "last_ts": {"$first": "$ts"},
            "last_role": {"$first": "$role"},
            "last_content": {"$first": "$content"},
            "project_id": {"$first": "$project_id"},
            "count": {"$sum": 1},
        }},
        {"$sort": {"last_ts": -1}},
        {"$limit": 50},
    ]
    convs = await db.coach_messages.aggregate(pipeline).to_list(length=None)
    return {
        "count": len(convs),
        "conversations": [
            {
                "conversation_id": c["_id"],
                "last_ts": c["last_ts"],
                "last_role": c["last_role"],
                "preview": (c.get("last_content") or "")[:140],
                "project_id": c.get("project_id"),
                "messages_count": c["count"],
            }
            for c in convs
        ],
    }
