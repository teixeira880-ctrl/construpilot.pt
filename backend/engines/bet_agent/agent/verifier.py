"""Verificador independente (L1.5 — Decisão 7 do fundador).

Sessão **nova**, zero histórico, Claude Opus 5.5. Recebe o `BuildingModel` +
`list[Anomaly]` dos checks determinísticos e devolve `list[Anomaly]` adicionais
(ou corroboração) via tool-use.

Ferramenta única: `report_anomaly` para registar anomalias; chamada `finish`
para fechar o ciclo.

Em CI usa mock (injectado como `AsyncLLMClient`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from engines.bet_agent.agent.loop import AsyncLLMClient
from engines.bet_agent.agent.prompts import VERIFIER_SYSTEM_PT
from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.models.building import BuildingModel
from engines.bet_agent.models.summary import (
    Anomaly,
    AnomalySeverity,
    AnomalySource,
)


VERIFIER_TOOLS: list[dict[str, Any]] = [
    {
        "name": "report_anomaly",
        "description": (
            "Reporta uma anomalia detectada pelo verificador. Severidade: "
            "bloqueante / grave / aviso. Mensagem em PT-PT."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "code": {"type": "string",
                         "description": "Código próprio ex: 'VER-001'."},
                "severity": {"type": "string",
                             "enum": ["bloqueante", "grave", "aviso"]},
                "message_pt": {"type": "string"},
                "remediation": {"type": "string"},
                "page": {"type": "integer"},
            },
            "required": ["code", "severity", "message_pt"],
        },
    },
    {
        "name": "finish_verification",
        "description": "Chamar após analisar o modelo todo.",
        "input_schema": {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        },
    },
]


@dataclass
class VerifierResult:
    additional_anomalies: list[Anomaly] = field(default_factory=list)
    turns_used: int = 0
    finished: bool = False


async def run_verifier(
    client: AsyncLLMClient,
    building: BuildingModel,
    existing_anomalies: list[Anomaly],
    meter: DossierMeter,
    model: str = "claude-opus-5-5",
    max_turns: int = 10,
) -> VerifierResult:
    """Corre o verificador numa sessão nova.

    - Sem histórico: envia só o BuildingModel + lista de anomalias existentes
      como contexto.
    - Metering continuo no mesmo `DossierMeter` do dossier (conta no
      alerta >€10).
    """
    building_json = building.model_dump_json(indent=2)
    anomalies_summary = "\n".join(
        f"- [{a.severity.value}] {a.code}: {a.message_pt}"
        for a in existing_anomalies
    ) or "(nenhuma anomalia reportada pelos checks determinísticos)"

    initial_text = (
        "Modelo estrutural lido (BuildingModel JSON):\n"
        f"```json\n{building_json}\n```\n\n"
        "Anomalias já detectadas pelos checks determinísticos:\n"
        f"{anomalies_summary}\n\n"
        "Analisa e reporta anomalias adicionais via `report_anomaly`. "
        "Quando terminares, chama `finish_verification`."
    )

    messages: list[dict[str, Any]] = [
        {"role": "user", "content": [{"type": "text", "text": initial_text}]},
    ]
    system = [{
        "type": "text", "text": VERIFIER_SYSTEM_PT,
        "cache_control": {"type": "ephemeral"},
    }]
    tools = [dict(VERIFIER_TOOLS[0]), dict(VERIFIER_TOOLS[1], cache_control={"type": "ephemeral"})]

    result = VerifierResult()

    for turn in range(max_turns):
        resp = await client.create_message(
            model=model, system=system, tools=tools,
            messages=messages, max_tokens=4096,
        )
        result.turns_used = turn + 1

        usage = resp.get("usage") or {}
        meter.record(
            model=model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cache_read_tokens=int(usage.get("cache_read_input_tokens", 0)),
        )

        content_blocks = resp.get("content") or []
        messages.append({"role": "assistant", "content": content_blocks})
        tool_uses = [b for b in content_blocks if b.get("type") == "tool_use"]

        if not tool_uses:
            return result

        tool_results: list[dict[str, Any]] = []
        hit_finish = False
        for tu in tool_uses:
            name = tu.get("name") or ""
            tu_id = tu.get("id") or ""
            tu_input = tu.get("input") or {}

            if name == "report_anomaly":
                try:
                    sev = AnomalySeverity(tu_input.get("severity"))
                    page = tu_input.get("page")
                    anom = Anomaly(
                        severity=sev,
                        code=tu_input.get("code") or "VER-UNDEF",
                        message_pt=tu_input.get("message_pt") or "",
                        source=AnomalySource(page=page) if page else AnomalySource(),
                        remediation=tu_input.get("remediation"),
                    )
                    result.additional_anomalies.append(anom)
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tu_id,
                        "content": '{"status":"ok"}',
                    })
                except Exception as exc:  # noqa: BLE001
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tu_id,
                        "content": json.dumps({"error": str(exc)}),
                        "is_error": True,
                    })
            elif name == "finish_verification":
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tu_id,
                    "content": '{"status":"finished"}',
                })
                hit_finish = True
            else:
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tu_id,
                    "content": f'{{"error":"unknown_tool","name":"{name}"}}',
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})
        if hit_finish:
            result.finished = True
            return result

    return result
