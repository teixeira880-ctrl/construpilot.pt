"""Núcleo do Assistente BTP: classificador de modos + loop function calling + SSE.

Pipeline:
    1. `classificar_modo()` → 'plano' | 'calculo' | 'conversa'
    2. Modo 'conversa' → `gemini-flash-latest` + Google Search grounding,
       streaming nativo → eventos `thinking` + `text_chunk` + `final`.
    3. Modos 'plano' / 'calculo' → `gemini-pro-latest` + function
       declarations → loop:
         a. Pedir resposta ao Gemini.
         b. Se `function_call`, converter para `ToolCall`, executar,
            emitir eventos `tool_call` + `tool_result`.
         c. Reenviar `function_response` ao Gemini.
         d. Parar quando o modelo devolve texto final.
    4. Persistência: cada turno gravado em `btp_assistant_conversations`
       (bytes dos anexos NÃO são persistidos — só metadata).
"""
from __future__ import annotations

import logging
import re
import time
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Literal

from core.db import db
from engines.btp_assistant.gemini_client import (
    MODELO_FLASH,
    MODELO_PRO,
    gerar_com_ferramentas,
    gerar_stream,
)
from engines.btp_assistant.system_prompt import SYSTEM_PROMPT_PT
from engines.btp_assistant.tools.executors import executar_tool_call
from engines.btp_assistant.tools.registry import (
    NOMES_FERRAMENTAS_COM_CONFIRMACAO,
    TOOLS,
)
from engines.btp_assistant.types import (
    AgentEvent,
    AgentResponse,
    Attachment,
    MissingDataRequest,
    ToolCall,
    ToolResult,
)

logger = logging.getLogger("btp_assistant.router")

Modo = Literal["plano", "calculo", "conversa"]

# Palavras-chave em PT-PT que empurram para o modo cálculo (prioritárias)
_PATTERNS_CALCULO = re.compile(
    r"\b(or[çc]amento|or[çc]ar|calcul\w*|metrado|estim\w*|custo|custa|pre[çc]o|"
    r"abr(e|ir)|exportar?|excel|adicion\w*|pdf|export|cri(a|ar|e)\b)\b",
    re.IGNORECASE,
)
# Palavras-chave para modo plano (quando NÃO há anexos)
_PATTERNS_PLANO = re.compile(
    r"\b(planta|plan[oa] pro|cad|dwg|rvt|revit|autodesk|geom(e|é)trica)\b",
    re.IGNORECASE,
)


def classificar_modo(
    *,
    user_prompt: str,
    anexos: list[Attachment] | None,
) -> Modo:
    """Decide o modo com heurística rápida. Pode ser substituído por um
    classifier Flash no futuro.
    """
    if anexos:
        # Qualquer anexo → modo plano (pode conter planta, PDF técnico, etc.)
        return "plano"
    if _PATTERNS_CALCULO.search(user_prompt or ""):
        return "calculo"
    if _PATTERNS_PLANO.search(user_prompt or ""):
        return "plano"
    return "conversa"


def _ev(tipo, **data) -> AgentEvent:
    return AgentEvent(type=tipo, data=data)


# ---------------------------------------------------------------------------
# Observabilidade (Fase C) — grava métricas por turno sem PII
# ---------------------------------------------------------------------------
async def _gravar_metrica(
    *,
    conv_id: str,
    user_id: str,
    modo: Modo,
    modelo: str,
    final_ev: AgentEvent | None,
    acc_eventos: list[AgentEvent],
    missing_data_count: int,
    tool_results: list[dict[str, Any]],
    had_error: bool,
    attachments_count: int,
) -> None:
    """Grava 1 doc em `btp_assistant_metrics`. ZERO PII (sem prompt/texto)."""
    duracao_s = (final_ev.data.get("duration_s") if final_ev else None) or 0.0
    duracao_ms = int(float(duracao_s) * 1000)
    tools_called = [
        e.data.get("name") for e in acc_eventos if e.type == "tool_call"
    ]
    tool_errors = sum(
        1 for tr in tool_results if tr.get("status") == "error"
    )
    awaiting = bool((final_ev.data.get("awaiting_confirmation") if final_ev else False))
    if had_error:
        status = "error"
    elif awaiting:
        status = "awaiting_confirmation"
    else:
        status = "success"
    # Plano do utilizador (consulta leve ao users; não bloqueante se falhar)
    user_plan = "free"
    try:
        u = await db.users.find_one({"user_id": user_id}, {"_id": 0, "plan": 1, "account_type": 1})
        if u:
            user_plan = (u.get("plan") or u.get("account_type") or "free").lower()
    except Exception:  # noqa: BLE001
        pass

    doc = {
        "conversation_id": conv_id,
        "user_id": user_id,  # NÃO é PII — é ID interno aleatório; já guardado em outras colecções
        "user_plan": user_plan,
        "modo": modo,
        "modelo": modelo,
        "duracao_ms": duracao_ms,
        "events_count": len(acc_eventos),
        "tools_called": tools_called,
        "tool_errors": tool_errors,
        "grounding_used": (modo == "conversa"),  # Google Search activo em conversa
        "missing_data_count": missing_data_count,
        "attachments_count": attachments_count,
        "status": status,
        "created_at": datetime.now(timezone.utc),
    }
    await db.btp_assistant_metrics.insert_one(doc)
def _extrair_function_calls(response: Any) -> list[tuple[str, dict[str, Any]]]:
    """Devolve `[(name, args), ...]` extraídos do candidato Gemini."""
    try:
        cands = getattr(response, "candidates", None) or []
        if not cands:
            return []
        content = getattr(cands[0], "content", None)
        parts = getattr(content, "parts", None) or []
    except Exception:  # noqa: BLE001
        return []
    out: list[tuple[str, dict[str, Any]]] = []
    for p in parts:
        fc = getattr(p, "function_call", None)
        if fc and getattr(fc, "name", None):
            # SDK devolve `args` como MapComposite → convertemos para dict
            try:
                args = dict(fc.args) if fc.args else {}
            except Exception:  # noqa: BLE001
                args = {}
            # args pode conter MapComposite nested — serializa via json round-trip
            import json as _json
            try:
                args = _json.loads(_json.dumps(args, default=lambda o: dict(o) if hasattr(o, "keys") else list(o)))
            except Exception:  # noqa: BLE001
                pass
            out.append((fc.name, args))
    return out


def _extrair_texto(response: Any) -> str:
    """Devolve o texto concatenado das `parts` sem function_call."""
    try:
        cands = getattr(response, "candidates", None) or []
        if not cands:
            return ""
        parts = getattr(cands[0].content, "parts", None) or []
    except Exception:  # noqa: BLE001
        return ""
    out = []
    for p in parts:
        if getattr(p, "function_call", None):
            continue
        t = getattr(p, "text", None)
        if t:
            out.append(t)
    return "".join(out).strip()


# ---------------------------------------------------------------------------
# Modo conversa (streaming)
# ---------------------------------------------------------------------------
async def _executar_modo_conversa(
    *,
    user_prompt: str,
    anexos: list[Attachment] | None,
    historial: list[dict[str, Any]],
    turn_id: str,
    conversation_id: str,
) -> AsyncIterator[AgentEvent]:
    t0 = time.time()
    yield _ev("thinking", mode="conversa", model=MODELO_FLASH)
    acc = []
    try:
        async for chunk in gerar_stream(
            modelo=MODELO_FLASH,
            system=SYSTEM_PROMPT_PT,
            user_prompt=user_prompt,
            anexos=anexos,
            historial=historial,
            enable_google_search=True,
            temperature=0.35,
            max_output_tokens=2048,
        ):
            texto = getattr(chunk, "text", None) or ""
            if texto:
                acc.append(texto)
                yield _ev("text_chunk", text=texto)
    except Exception as e:  # noqa: BLE001
        logger.exception("modo conversa falhou")
        yield _ev("error", message_pt=(
            "Falha temporária ao gerar resposta. Tente novamente."
        ), detail=f"{type(e).__name__}")
        return
    texto_final = "".join(acc).strip()
    yield _ev(
        "final",
        conversation_id=conversation_id,
        turn_id=turn_id,
        text_pt=texto_final,
        mode="conversa",
        model=MODELO_FLASH,
        duration_s=round(time.time() - t0, 3),
    )


# ---------------------------------------------------------------------------
# Modo plano/calculo (function calling loop)
# ---------------------------------------------------------------------------
async def _executar_modo_com_ferramentas(
    *,
    modo: Modo,
    user_prompt: str,
    anexos: list[Attachment] | None,
    historial: list[dict[str, Any]],
    turn_id: str,
    conversation_id: str,
    user_id: str,
    max_rondas: int = 4,
) -> AsyncIterator[AgentEvent]:
    t0 = time.time()
    yield _ev("thinking", mode=modo, model=MODELO_PRO)
    tool_results_payload: list[dict[str, Any]] = []
    tool_calls_acc: list[ToolCall] = []
    tool_results_acc: list[ToolResult] = []
    missing_data_acc: list[MissingDataRequest] = []
    texto_final = ""

    for ronda in range(max_rondas):
        try:
            response = await gerar_com_ferramentas(
                modelo=MODELO_PRO,
                system=SYSTEM_PROMPT_PT,
                user_prompt=user_prompt if ronda == 0 else "(continuar)",
                anexos=anexos if ronda == 0 else None,
                historial=historial,
                function_declarations=TOOLS,
                tool_results=tool_results_payload or None,
                enable_google_search=False,  # tools + search raramente coexistem bem
                temperature=0.1,
                max_output_tokens=4096,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("gerar_com_ferramentas falhou ronda=%d", ronda)
            yield _ev("error", message_pt=(
                "Falha temporária ao gerar resposta. Tente novamente."
            ), detail=f"{type(e).__name__}")
            return

        fcs = _extrair_function_calls(response)
        texto_parcial = _extrair_texto(response)

        if texto_parcial:
            texto_final = texto_parcial
            yield _ev("text_chunk", text=texto_parcial)

        if not fcs:
            # Sem mais function calls → terminou
            break

        # Executar cada function call
        tool_results_payload = []
        for name, args in fcs:
            call = ToolCall(
                id=f"tc_{uuid.uuid4().hex[:8]}",
                name=name, arguments=args,
                requires_user_confirmation=(
                    name in NOMES_FERRAMENTAS_COM_CONFIRMACAO
                ),
            )
            tool_calls_acc.append(call)
            yield _ev(
                "tool_call",
                id=call.id, name=call.name, arguments=call.arguments,
                requires_user_confirmation=call.requires_user_confirmation,
            )

            # Para acções que exigem confirmação, NÃO executamos no backend —
            # devolvemos para a UI confirmar e o utilizador reenvia depois.
            if call.requires_user_confirmation:
                result = ToolResult(
                    tool_call_id=call.id,
                    status="needs_user_confirmation",
                    payload={"call": call.model_dump()},
                    user_message_pt=(
                        "A ferramenta precisa de confirmação do utilizador "
                        "antes de executar."
                    ),
                )
                tool_results_acc.append(result)
                yield _ev(
                    "tool_result",
                    tool_call_id=call.id,
                    status=result.status,
                    payload=result.payload,
                    user_message_pt=result.user_message_pt,
                )
                # Emitir final e sair do ciclo — a UI decidirá
                yield _ev(
                    "final",
                    conversation_id=conversation_id,
                    turn_id=turn_id,
                    text_pt=texto_final,
                    mode=modo,
                    model=MODELO_PRO,
                    duration_s=round(time.time() - t0, 3),
                    tool_calls_count=len(tool_calls_acc),
                    missing_data_count=len(missing_data_acc),
                    awaiting_confirmation=True,
                )
                return

            # Executar realmente
            result = await executar_tool_call(call, user_id=user_id)
            tool_results_acc.append(result)
            if result.status == "needs_user_input":
                missing_data_acc.extend(result.missing_data)
                for md in result.missing_data:
                    yield _ev("missing_data", **md.model_dump())
            yield _ev(
                "tool_result",
                tool_call_id=call.id,
                status=result.status,
                payload=result.payload,
                user_message_pt=result.user_message_pt,
            )
            tool_results_payload.append({
                "name": name,
                "response": {"content": result.model_dump()},
            })

        # Se qualquer ferramenta pediu dados → parar ciclo e devolver ao user
        if missing_data_acc:
            break

    yield _ev(
        "final",
        conversation_id=conversation_id,
        turn_id=turn_id,
        text_pt=texto_final,
        mode=modo,
        model=MODELO_PRO,
        duration_s=round(time.time() - t0, 3),
        tool_calls_count=len(tool_calls_acc),
        missing_data_count=len(missing_data_acc),
    )


def _emitir_final(**kw):
    """Helper síncrono para devolver via `return` dentro de async gen —
    não é yield-able; esta função é um placeholder removido."""
    return None# ---------------------------------------------------------------------------
# API pública: route_user_request
# ---------------------------------------------------------------------------
async def route_user_request(
    *,
    user_prompt: str,
    user_id: str,
    conversation_id: str | None = None,
    attachments: list[Attachment] | None = None,
) -> AsyncIterator[AgentEvent]:
    """Entrada única do agente. Devolve `AsyncIterator[AgentEvent]`.

    * Classifica o modo.
    * Carrega historial da conversa (últimos 20 turnos).
    * Despacha para o executor correcto.
    * Persiste o turno no final.
    """
    conv_id = conversation_id or f"conv_{uuid.uuid4().hex[:12]}"
    turn_id = f"turn_{uuid.uuid4().hex[:10]}"
    modo = classificar_modo(user_prompt=user_prompt, anexos=attachments)

    # Historial (texto apenas, sem anexos antigos)
    conv = await db.btp_assistant_conversations.find_one(
        {"conversation_id": conv_id, "user_id": user_id}, {"_id": 0},
    )
    historial: list[dict[str, Any]] = []
    if conv:
        for t in (conv.get("turns") or [])[-20:]:
            historial.append({"role": "user", "text": t.get("user_prompt", "")})
            ag = (t.get("agent_response") or {}).get("text_pt")
            if ag:
                historial.append({"role": "assistant", "text": ag})

    # Executar modo
    acc_eventos: list[AgentEvent] = []
    if modo == "conversa":
        gen = _executar_modo_conversa(
            user_prompt=user_prompt, anexos=attachments,
            historial=historial, turn_id=turn_id,
            conversation_id=conv_id,
        )
    else:
        gen = _executar_modo_com_ferramentas(
            modo=modo, user_prompt=user_prompt, anexos=attachments,
            historial=historial, turn_id=turn_id,
            conversation_id=conv_id, user_id=user_id,
        )
    async for ev in gen:
        acc_eventos.append(ev)
        yield ev

    # Persistir turno
    final_ev = next((e for e in reversed(acc_eventos) if e.type == "final"), None)
    texto_resp = ""
    if final_ev:
        texto_resp = final_ev.data.get("text_pt") or ""
    tool_calls_final = [
        e.data for e in acc_eventos if e.type == "tool_call"
    ]
    tool_results_final = [
        e.data for e in acc_eventos if e.type == "tool_result"
    ]
    missing_data_final = [
        e.data for e in acc_eventos if e.type == "missing_data"
    ]
    agent_resp = {
        "text_pt": texto_resp,
        "mode": modo,
        "model_used": MODELO_FLASH if modo == "conversa" else MODELO_PRO,
        "tool_calls": tool_calls_final,
        "tool_results": tool_results_final,
        "missing_data": missing_data_final,
    }
    agora = datetime.now(timezone.utc).isoformat()
    turn_doc = {
        "turn_id": turn_id,
        "user_prompt": user_prompt,
        "attachments_meta": [
            {"filename": a.filename, "mime_type": a.mime_type,
             "size_bytes": len(a.data_b64)}
            for a in (attachments or [])
        ],
        "agent_response": agent_resp,
        "created_at_iso": agora,
    }
    await db.btp_assistant_conversations.update_one(
        {"conversation_id": conv_id, "user_id": user_id},
        {
            "$setOnInsert": {
                "conversation_id": conv_id, "user_id": user_id,
                "created_at_iso": agora,
            },
            "$set": {"updated_at_iso": agora},
            "$push": {"turns": turn_doc},
        },
        upsert=True,
    )

    # Observabilidade — Fase C: gravar métricas (zero PII)
    try:
        await _gravar_metrica(
            conv_id=conv_id, user_id=user_id, modo=modo,
            modelo=agent_resp["model_used"],
            final_ev=final_ev, acc_eventos=acc_eventos,
            missing_data_count=len(missing_data_final),
            tool_results=tool_results_final,
            had_error=any(e.type == "error" for e in acc_eventos),
            attachments_count=len(attachments or []),
        )
    except Exception:  # noqa: BLE001
        logger.exception("falha a gravar métrica — não interrompe o turno")


# ---------------------------------------------------------------------------
# Convenience: variante não-streaming (agrega eventos)
# ---------------------------------------------------------------------------
async def route_user_request_sync(
    *,
    user_prompt: str,
    user_id: str,
    conversation_id: str | None = None,
    attachments: list[Attachment] | None = None,
) -> AgentResponse:
    """Executa `route_user_request` e devolve `AgentResponse` agregado."""
    eventos: list[AgentEvent] = []
    async for ev in route_user_request(
        user_prompt=user_prompt, user_id=user_id,
        conversation_id=conversation_id, attachments=attachments,
    ):
        eventos.append(ev)
    final_ev = next((e for e in reversed(eventos) if e.type == "final"), None)
    if not final_ev:
        # Devolve com texto vazio mas eventos preservados no trace
        return AgentResponse(
            conversation_id=conversation_id or "unknown",
            turn_id="turn_unknown", text_pt="",
            tool_calls=[], tool_results=[], missing_data=[],
            model_used=MODELO_PRO, mode="conversa",
            trace={"events_count": len(eventos),
                   "error": "sem evento final"},
        )
    conv_id = final_ev.data.get("conversation_id") or "unknown"
    turn_id = final_ev.data.get("turn_id") or "turn_unknown"
    modo = final_ev.data.get("mode") or "conversa"
    tool_calls = [
        ToolCall(**{
            "id": e.data["id"], "name": e.data["name"],
            "arguments": e.data["arguments"],
            "requires_user_confirmation": e.data.get("requires_user_confirmation", False),
        })
        for e in eventos if e.type == "tool_call"
    ]
    tool_results = [
        ToolResult(
            tool_call_id=e.data["tool_call_id"],
            status=e.data["status"],
            payload=e.data.get("payload") or {},
            user_message_pt=e.data.get("user_message_pt") or "",
        )
        for e in eventos if e.type == "tool_result"
    ]
    missing_data = [
        MissingDataRequest(**{
            k: v for k, v in e.data.items()
            if k in ("question_pt", "field", "unit", "element_id",
                     "suggested_default", "criticidade")
        })
        for e in eventos if e.type == "missing_data"
    ]
    return AgentResponse(
        conversation_id=conv_id, turn_id=turn_id,
        text_pt=final_ev.data.get("text_pt", ""),
        tool_calls=tool_calls, tool_results=tool_results,
        missing_data=missing_data,
        model_used=final_ev.data.get("model") or MODELO_PRO,
        mode=modo,
        trace={
            "duration_s": final_ev.data.get("duration_s"),
            "events_count": len(eventos),
            "tool_calls_count": final_ev.data.get("tool_calls_count"),
        },
    )


__all__ = [
    "classificar_modo", "route_user_request", "route_user_request_sync",
]
