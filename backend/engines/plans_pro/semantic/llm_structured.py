"""Chamada LLM com structured outputs — zero JSON patching.

Contrato (Fase 1):
    * Entrada: imagem base64 + metadata APS + hint do projecto.
    * Saída: instância Pydantic `AnalisePlanta` validada.
    * Ordem de fallback **específica deste motor**: OpenAI → Claude.
      Razão: OpenAI tem `response_format={"type":"json_schema", strict=True}`
      nativo (determinante aqui); Claude é fallback via tool-use.
    * O router global `ai_providers` continua Claude-primário para o
      Coach e Assistente de Obras — NÃO é alterado aqui.

Regra dura: se o LLM devolver JSON malformado ou que não valide no
`AnalisePlanta`, levantamos `SchemaValidationError`. NÃO tentamos
remendar — a rota converte para `MissingDataRequest` ao utilizador.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from pydantic import ValidationError

from engines.ai_providers.base import AIProviderError
from engines.ai_providers.router import ai_router
from engines.plans_pro.semantic.exceptions import (
    SchemaValidationError,
    VisionAnalysisError,
)
from engines.plans_pro.semantic.schemas import AnalisePlanta

logger = logging.getLogger("plans_pro.llm_structured")


# ---------------------------------------------------------------------------
# System prompt (metreur-vérificateur PT)
# ---------------------------------------------------------------------------
SYSTEM_PROMPT_PT = (
    "És um metreur-vérificateur sénior em Portugal (RGEU, Eurocódigos, "
    "REH, REBAP). Analisas plantas BTP para extrair elementos "
    "estruturais com rigor — zero invenção.\n\n"
    "Entrada que recebes:\n"
    "  1. Metadata Autodesk APS (categorias, layers, bbox).\n"
    "  2. Imagem da planta (thumbnail/preview).\n"
    "  3. Contexto do projecto (opcional).\n\n"
    "Produzes APENAS JSON válido respeitando o JSON Schema fornecido. "
    "Nunca envolvas em markdown ```json. Nunca adiciones campos extra.\n\n"
    "Regras duras:\n"
    "  * Se não vires um dado com confiança ≥0.6, deixa o campo `None` "
    "e adiciona o aviso em PT-PT ao `warnings` do elemento.\n"
    "  * NUNCA inventes rácios (ex.: kg/m³ de aço), classes de betão, "
    "nem dimensões — se faltar, deixa `null` e segue.\n"
    "  * Cruza OCR do texto visível, geometria aparente e classificação "
    "APS antes de atribuir `tipo` e `confidence` a um elemento.\n"
    "  * `source` reflecte a origem: 'ocr' | 'geometria' | "
    "'aps_classification' | 'llm' | 'deducao_heuristica' | 'cross_check'.\n"
    "  * Todas as strings em PT-PT (sem FR, sem EN).\n"
    "  * `plan_id` deve ecoar o valor fornecido no prompt.\n"
    "  * `confidence_global` ∈ [0,1] é a média ponderada por elemento.\n"
    "  * `requires_human_review` = true se não tiveres confiança suficiente.\n"
)


def _schema_openai_strict() -> dict[str, Any]:
    """Devolve o JSON Schema do `AnalisePlanta` adaptado ao modo strict
    da OpenAI (`additionalProperties: false` em TODOS os níveis +
    `required` com todos os campos declarados).
    """
    schema = AnalisePlanta.model_json_schema()
    _patch_strict(schema)
    return schema


def _patch_strict(obj: Any) -> None:
    """Caminha recursivamente e força `additionalProperties: false` +
    `required` com TODAS as propriedades em cada nó do tipo `object`.
    """
    if isinstance(obj, dict):
        if obj.get("type") == "object" or "properties" in obj:
            obj["additionalProperties"] = False
            props = obj.get("properties") or {}
            if props:
                # strict mode da OpenAI exige que todos os campos declarados
                # estejam em `required` (os `None` vêm explícitos no JSON).
                obj["required"] = list(props.keys())
        for v in obj.values():
            _patch_strict(v)
    elif isinstance(obj, list):
        for v in obj:
            _patch_strict(v)


def _construir_prompt(
    *,
    plan_id: str,
    filename: str,
    metadata: dict[str, Any],
    project_hint: str | None,
) -> str:
    """Monta o prompt de utilizador. Mantém-se curto — o schema vai
    separado via `response_format`."""
    quantities = metadata.get("quantities") or {}
    bbox = metadata.get("bbox") or {}
    hint = project_hint or "N/A"
    partes = [
        f"[plan_id] {plan_id}",
        f"[ficheiro] {filename}",
        f"[projecto] {hint}",
        "[APS_METADATA_quantities]",
        json.dumps(quantities, ensure_ascii=False, indent=2)[:3500],
    ]
    if bbox:
        partes.append("[APS_METADATA_bbox]")
        partes.append(json.dumps(bbox, ensure_ascii=False)[:400])
    partes.append(
        "Devolve o JSON `AnalisePlanta` conforme schema. "
        "`plan_id` deve ser exactamente o acima."
    )
    return "\n".join(partes)


async def _call_openai(
    *,
    prompt: str,
    image_data_uri: str | None,
    schema: dict[str, Any],
) -> str:
    """Chama OpenAI gpt-4o com `response_format=json_schema` strict.

    Devolve o `text` cru. Levanta `VisionAnalysisError` em erro de rede/API.
    """
    provider = ai_router.openai_vision or ai_router.openai_coach
    if provider is None:
        raise VisionAnalysisError(
            "OpenAI não configurado para structured outputs.",
            provider="openai",
        )
    kwargs: dict[str, Any] = {
        "prompt": prompt,
        "system": SYSTEM_PROMPT_PT,
        "max_tokens": 3000,
        "temperature": 0.0,
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "AnalisePlanta",
                "schema": schema,
                "strict": True,
            },
        },
    }
    if image_data_uri:
        kwargs["image_url"] = image_data_uri
    try:
        r = await provider.ask(**kwargs)
    except AIProviderError as e:
        raise VisionAnalysisError(
            f"OpenAI falhou: {e.code} ({str(e)[:200]})",
            provider="openai",
        ) from e
    if r.is_empty:
        raise VisionAnalysisError(
            "OpenAI devolveu resposta vazia.", provider="openai"
        )
    return r.text


async def _call_claude(
    *,
    prompt: str,
    schema: dict[str, Any],
) -> str:
    """Chama Claude como fallback (sem imagem — Claude 5.5 vision ainda
    não é usado neste motor). Pedimos tool-use estrito via prompt +
    `temperature=0`.

    Devolve o `text` cru. Levanta `VisionAnalysisError` em erro.
    """
    provider = ai_router.claude
    if provider is None:
        raise VisionAnalysisError(
            "Claude não configurado como fallback.", provider="claude"
        )
    # Claude não tem response_format nativo igual à OpenAI;
    # pedimos JSON directo no system e verificamos a seguir.
    system = (
        SYSTEM_PROMPT_PT
        + "\n\n[JSON SCHEMA ESPERADO]\n"
        + json.dumps(schema, ensure_ascii=False)[:4000]
        + "\n\nResponde SÓ com o JSON (sem markdown, sem comentários)."
    )
    try:
        r = await provider.ask(
            prompt=prompt,
            system=system,
            max_tokens=3000,
            temperature=0.0,
        )
    except AIProviderError as e:
        raise VisionAnalysisError(
            f"Claude falhou: {e.code} ({str(e)[:200]})", provider="claude"
        ) from e
    if r.is_empty:
        raise VisionAnalysisError(
            "Claude devolveu resposta vazia.", provider="claude"
        )
    return r.text


def _parse_strict(raw: str) -> AnalisePlanta:
    """Parse JSON + valida em `AnalisePlanta`. SEM remendos.

    Diferença chave vs. legado:
        * Legado: `_extract_json` tentava fechar brackets, remover vírgulas
          finais, extrair substring. Isto podia inventar estruturas vazias.
        * Novo: um `json.loads(raw)` ou falha → `SchemaValidationError`.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise SchemaValidationError(
            f"JSON inválido: {e}", raw_response=raw,
        ) from e
    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"Esperava dict JSON, recebi {type(data).__name__}.",
            raw_response=raw,
        )
    try:
        return AnalisePlanta.model_validate(data)
    except ValidationError as e:
        raise SchemaValidationError(
            f"Falha validação Pydantic: {e.error_count()} erros.",
            raw_response=raw,
        ) from e


async def analisar_com_structured_output(
    *,
    plan_id: str,
    filename: str,
    metadata: dict[str, Any],
    image_data_uri: str | None,
    project_hint: str | None = None,
) -> tuple[AnalisePlanta, dict[str, Any]]:
    """Executa a análise LLM e devolve `(AnalisePlanta, trace)`.

    Ordem para este motor específico: OpenAI → Claude (ver docstring do
    módulo). Cada tentativa valida o schema; a primeira que validar vence.

    Levanta:
        * `VisionAnalysisError` se TODOS os providers falharem HTTP/vazio.
        * `SchemaValidationError` se TODOS devolverem JSON inválido.
    """
    schema = _schema_openai_strict()
    prompt = _construir_prompt(
        plan_id=plan_id,
        filename=filename,
        metadata=metadata,
        project_hint=project_hint,
    )
    trace: dict[str, Any] = {
        "providers_attempted": [],
        "providers_used": None,
        "schema_errors": [],
    }

    # 1. OpenAI (primário neste motor)
    t0 = time.time()
    try:
        raw = await _call_openai(
            prompt=prompt, image_data_uri=image_data_uri, schema=schema
        )
        trace["providers_attempted"].append("openai")
        trace["openai_latency_ms"] = int((time.time() - t0) * 1000)
        try:
            parsed = _parse_strict(raw)
        except SchemaValidationError as se:
            trace["schema_errors"].append({"provider": "openai", "detail": str(se)[:200]})
            logger.info("openai schema inválido, fallback claude: %s", se)
            raise  # dispara ao bloco Claude abaixo
        trace["providers_used"] = "openai"
        return parsed, trace
    except (VisionAnalysisError, SchemaValidationError) as e_openai:
        logger.info("openai falhou: %s", type(e_openai).__name__)

    # 2. Claude (fallback)
    t1 = time.time()
    try:
        raw = await _call_claude(prompt=prompt, schema=schema)
        trace["providers_attempted"].append("claude")
        trace["claude_latency_ms"] = int((time.time() - t1) * 1000)
        parsed = _parse_strict(raw)  # erro aqui propaga como SchemaValidationError
        trace["providers_used"] = "claude"
        return parsed, trace
    except SchemaValidationError as se:
        trace["schema_errors"].append({"provider": "claude", "detail": str(se)[:200]})
        raise
    except VisionAnalysisError:
        raise


__all__ = [
    "analisar_com_structured_output",
    "SYSTEM_PROMPT_PT",
]
