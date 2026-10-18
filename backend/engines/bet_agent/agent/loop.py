"""Loop ReAct do Reader BET-PT.

Alterna entre:
    - envio de página render (PNG base64) + texto vectorial + prompt caching
    - leitura de `response.content` com blocos text / tool_use
    - dispatch de cada tool_use via `handle_tool_use` (ver `tools.py`)
    - devolver `tool_result` content blocks ao modelo
    - continua até `stop_reason == "end_turn"` OU `finish` tool chamado OU
      max_turns atingido

Regras:
    - **Prompt caching ephemeral** nos blocos system + tools (menor custo).
    - **Zero chamadas reais em CI**: client é injectado via `AsyncLLMClient`
      protocol — mocks são trivially passíveis em testes.
    - **Metering obrigatório** via `DossierMeter`: cada response.usage é
      acumulado.
    - **ask_user bloqueante** interrompe o loop e devolve controlo ao chamador
      (que apresenta a pergunta ao utilizador e re-arranca com a resposta).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

from engines.bet_agent.agent.tools import (
    READER_TOOLS,
    ToolDispatchResult,
    handle_tool_use,
)
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.models.building import BuildingModel
from engines.bet_agent.registry.pricing_claude import Usage

logger = logging.getLogger(__name__)


MAX_TURNS_DEFAULT = 40


# ---------------------------------------------------------------------------
# Protocolo de cliente (permite mock em CI)
# ---------------------------------------------------------------------------

class AsyncLLMClient(Protocol):
    """Interface mínima que o loop requer. Compatível com SDK Anthropic +
    com mocks em testes."""

    async def create_message(
        self,
        *,
        model: str,
        system: list[dict[str, Any]] | str,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
        max_tokens: int,
    ) -> dict[str, Any]:
        """Devolve dict com forma:
            {
                "stop_reason": "end_turn" | "tool_use" | "max_tokens",
                "content": [
                    {"type": "text", "text": "..."},
                    {"type": "tool_use", "id": "...", "name": "...", "input": {...}},
                    ...
                ],
                "usage": {
                    "input_tokens": int,
                    "output_tokens": int,
                    "cache_creation_input_tokens": int,
                    "cache_read_input_tokens": int,
                },
            }
        """
        ...


# ---------------------------------------------------------------------------
# Resultado do loop
# ---------------------------------------------------------------------------

@dataclass
class LoopResult:
    building: BuildingModel
    pending_questions: list[dict[str, Any]] = field(default_factory=list)
    zoom_requests: list[dict[str, Any]] = field(default_factory=list)
    turns_used: int = 0
    stopped_reason: str = "end_turn"
    finished_via_tool: bool = False


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def _system_blocks(prompt: str) -> list[dict[str, Any]]:
    """System prompt com cache_control ephemeral (reduz custo em cada turno)."""
    return [{
        "type": "text",
        "text": prompt,
        "cache_control": {"type": "ephemeral"},
    }]


def _tools_with_cache_control(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Marca o último tool com cache_control ephemeral — tudo acima é cached."""
    if not tools:
        return tools
    out = [dict(t) for t in tools]
    out[-1] = dict(out[-1], cache_control={"type": "ephemeral"})
    return out


async def run_reader_loop(
    client: AsyncLLMClient,
    system_prompt: str,
    initial_user_content: list[dict[str, Any]],
    project_id: str,
    meter: DossierMeter,
    model: str = "claude-opus-5-5",
    max_turns: int = MAX_TURNS_DEFAULT,
    max_tokens_per_call: int = 4096,
    stop_on_user_question: bool = True,
) -> LoopResult:
    """Loop ReAct completo.

    - `initial_user_content` é a primeira user message (lista de content blocks:
      texto + imagens em base64).
    - `stop_on_user_question=True` → ao receber tool_use `ask_user`, pára o loop
      e devolve controlo ao chamador. Default True (interactividade bloqueante
      conforme decisão do fundador).
    """
    building = BuildingModel(project_id=project_id)
    result = LoopResult(building=building)

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": list(initial_user_content)},
    ]
    tools = _tools_with_cache_control(READER_TOOLS)
    system = _system_blocks(system_prompt)

    for turn in range(max_turns):
        resp = await client.create_message(
            model=model, system=system, tools=tools,
            messages=messages, max_tokens=max_tokens_per_call,
        )
        result.turns_used = turn + 1

        usage = resp.get("usage") or {}
        meter.record(
            model=model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
        )
        # Nota: `cache_creation_input_tokens` do SDK não é input "normal",
        # fica fora do metering `input_tokens` acima e deve ser contabilizado
        # pelo `estimate_cost_eur` quando usado. Aqui mantemos simples e
        # agregamos como "input" conservador se existir:
        extra_create = int(usage.get("cache_creation_input_tokens", 0))
        if extra_create > 0:
            meter.record(model=model, input_tokens=extra_create,
                         output_tokens=0, cache_read_tokens=0)

        content_blocks = resp.get("content") or []
        stop_reason = resp.get("stop_reason") or "end_turn"
        result.stopped_reason = stop_reason

        # Guarda assistant message no histórico (regra Anthropic).
        messages.append({"role": "assistant", "content": content_blocks})

        tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]
        if not tool_uses:
            # Modelo não quer mais tools → fecha.
            return result

        # Dispatch de cada tool_use em sequência; recolhe tool_result blocks.
        tool_result_blocks: list[dict[str, Any]] = []
        hit_blocking = False

        for tu in tool_uses:
            name = tu.get("name") or ""
            tu_id = tu.get("id") or ""
            tu_input = tu.get("input") or {}
            res: ToolDispatchResult = handle_tool_use(
                name=name, raw_input=tu_input,
                building=building, pending_questions=result.pending_questions,
            )
            tool_result_blocks.append({
                "type": "tool_result",
                "tool_use_id": tu_id,
                "content": res.tool_result_payload,
                "is_error": not res.ok,
            })

            if res.zoom_request:
                result.zoom_requests.append(res.zoom_request)
            if res.user_question and stop_on_user_question:
                hit_blocking = True
            if res.finish_signal:
                result.finished_via_tool = True
                hit_blocking = True

        # Envia tool_result em uma única user message (padrão Anthropic).
        messages.append({"role": "user", "content": tool_result_blocks})

        if hit_blocking:
            return result

    result.stopped_reason = "max_turns"
    return result
