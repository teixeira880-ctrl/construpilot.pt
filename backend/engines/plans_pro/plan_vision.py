"""Cascade IA para análise de plantas Autodesk (Fase 1 — blindado).

Pipeline (novo):
    1. `analisar_com_structured_output` (OpenAI → Claude) devolve
       `AnalisePlanta` tipado — nunca JSON livre.
    2. `cross_check` compara APS metadata ↔ Vision LLM e produz
       `CrossCheckWarning`.
    3. `aplicar_warnings` funde no resultado, ajusta `confidence_global`
       e `requires_human_review`.

Alterações vs. legado:
    * `full_analysis` devolve agora `AnalisePlanta` (não `dict`).
    * O `_extract_json` tolerante **permanece neste ficheiro apenas como
      helper DEPRECATED** — não é chamado no caminho principal. Será
      removido na Fase 3.
    * Perplexity (normas PT) foi deslocado para `norms_fetch` opcional
      que o chamador pode invocar separadamente; não contamina mais a
      estrutura semântica.
"""
from __future__ import annotations

import base64
import json
import logging
import re
import time
from typing import Any

from engines.ai_providers.router import ai_router
from engines.plans_pro.semantic.cross_check import aplicar_warnings, cross_check
from engines.plans_pro.semantic.exceptions import (
    MissingDataError,
    SchemaValidationError,
    VisionAnalysisError,
)
from engines.plans_pro.semantic.llm_structured import (
    analisar_com_structured_output,
)
from engines.plans_pro.semantic.schemas import (
    AnalisePlanta,
    MissingDataRequest,
)

logger = logging.getLogger("plans_pro.vision")


# ---------------------------------------------------------------------------
# DEPRECATED Fase 1 — não usar no fluxo principal. Remover na Fase 3.
# Mantido apenas para não quebrar imports externos ou testes legados.
# ---------------------------------------------------------------------------
def _extract_json(text: str) -> dict | None:
    """DEPRECATED Fase 1 — JSON patching tolerante. Não chamar no fluxo
    principal. O novo caminho usa `semantic.llm_structured._parse_strict`
    que rejeita JSON malformado em vez de inventar estrutura.
    """
    if not text:
        return None
    text = re.sub(r"^```(?:json)?\s*", "", text.strip())
    text = re.sub(r"\s*```\s*$", "", text)
    try:
        return json.loads(text)
    except Exception:
        pass
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Normas PT (Perplexity) — opcional, fora da `AnalisePlanta`
# ---------------------------------------------------------------------------
async def _norms_perplexity(elementos_resumo: list[str]) -> dict | None:
    """Devolve `{"text", "citations"}` ou `None` se Perplexity não configurado."""
    pplx = ai_router.perplexity
    if not pplx:
        return None
    key = [e for e in elementos_resumo if e][:6]
    question = (
        "Quais são as normas portuguesas e europeias aplicáveis a uma obra "
        f"que inclui: {', '.join(key) or 'estrutura corrente'}? "
        "Lista RGEU, Eurocódigos, REH, REBAP, DL aplicáveis em PT-PT."
    )
    try:
        r = await pplx.ask(prompt=question, system=None, max_tokens=800, temperature=0.1)
    except Exception as e:  # noqa: BLE001 — Perplexity é opcional
        logger.info("perplexity falhou (opcional): %s", type(e).__name__)
        return None
    return {
        "text": r.text,
        "citations": [c.url if hasattr(c, "url") else str(c)
                      for c in (r.citations or [])][:10],
    }


# ---------------------------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------------------------
async def full_analysis(
    *,
    plan_id: str,
    filename: str,
    metadata: dict[str, Any],
    thumbnail_bytes: bytes | None,
    thumbnail_mime: str = "image/png",
    project_hint: str | None = None,
    include_web_norms: bool = False,
) -> AnalisePlanta:
    """Pipeline completo. Devolve `AnalisePlanta` tipado — sempre.

    Em caso de erro no LLM, embala o problema como `MissingDataRequest`
    de criticidade 'bloqueante' em vez de rebentar. Isto permite à UI
    mostrar modal ao utilizador em vez de HTTP 500.

    Raises:
        VisionAnalysisError: todos os providers LLM falharam HTTP/vazio
            (ou seja, nem conseguimos tentar schema validation).
    """
    trace: dict[str, Any] = {
        "plan_id": plan_id,
        "filename": filename,
        "started_at_ts": time.time(),
    }

    # 1. Preparar imagem
    data_uri: str | None = None
    if thumbnail_bytes:
        b64 = base64.b64encode(thumbnail_bytes).decode()
        data_uri = f"data:{thumbnail_mime};base64,{b64}"
        trace["has_thumbnail"] = True
    else:
        trace["has_thumbnail"] = False

    # 2. Chamar LLM com structured output
    missing_bloqueante: list[MissingDataRequest] = []
    try:
        analise, llm_trace = await analisar_com_structured_output(
            plan_id=plan_id,
            filename=filename,
            metadata=metadata,
            image_data_uri=data_uri,
            project_hint=project_hint,
        )
        trace.update(llm_trace)
    except SchemaValidationError as e:
        # LLM devolveu JSON que não valida → embalar como pergunta
        logger.exception("structured output rejeitado por schema")
        trace["schema_error"] = str(e)[:300]
        missing_bloqueante.append(
            MissingDataRequest(
                question_pt=(
                    "A análise automática do plano falhou (resposta IA "
                    "não validada). Pode confirmar/completar manualmente "
                    "os dados principais do projecto?"
                ),
                field="plano.analise_llm",
                unit=None,
                element_id=None,
                suggested_default=None,
                criticidade="bloqueante",
            )
        )
        analise = AnalisePlanta(
            plan_id=plan_id,
            elementos=[],
            missing_data=missing_bloqueante,
            warnings=[],
            confidence_global=0.0,
            requires_human_review=True,
            trace={},
        )

    # 3. Cross-check APS ↔ Vision
    warnings = cross_check(metadata or {}, analise)
    analise = aplicar_warnings(analise, warnings)

    # 4. Perplexity opcional (fora de `AnalisePlanta` por design)
    if include_web_norms and analise.elementos:
        tipos = sorted({el.tipo for el in analise.elementos})
        norms = await _norms_perplexity(tipos)
        if norms:
            trace["norms_citations_count"] = len(norms.get("citations", []))

    # 5. Finalizar trace
    trace["duration_s"] = round(time.time() - trace["started_at_ts"], 3)
    trace["warnings_count"] = len(analise.warnings)
    trace["missing_data_count"] = len(analise.missing_data)
    trace["confidence_global"] = analise.confidence_global
    trace["requires_human_review"] = analise.requires_human_review
    # Trace permite apenas tipos primitivos no schema; convertemos tudo
    # para str/int/float/bool/None onde necessário
    trace_safe = {
        k: (v if isinstance(v, (int, float, bool, str)) or v is None else str(v))
        for k, v in trace.items()
    }
    return analise.model_copy(update={"trace": trace_safe})


__all__ = ["full_analysis", "MissingDataError"]
