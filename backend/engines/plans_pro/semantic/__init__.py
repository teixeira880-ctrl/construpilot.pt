"""Camada semântica do motor Plans Pro — Fase 1.

Blindagem contra alucinações do LLM:
    * Esquemas Pydantic v2 estritos (`extra="forbid"`, `strict=True`).
    * Léxico PT-BTP determinístico (zero LLM) para abreviaturas, classes de
      betão/aço, varões, isolamento.
    * Verificação cruzada APS ↔ LLM com severidade.
    * Excepções tipadas com stacktrace preservado.
    * Chamada LLM com structured outputs (OpenAI JSON Schema → Claude tool).

Preferir falhar explicitamente com `MissingDataRequest` do que devolver
dados inventados.
"""
from engines.plans_pro.semantic.exceptions import (
    AutodeskError,
    MissingDataError,
    OCRError,
    PlansProError,
    SchemaValidationError,
    VisionAnalysisError,
)
from engines.plans_pro.semantic.schemas import (
    Abertura,
    AnalisePlanta,
    Armadura,
    CrossCheckWarning,
    Dimensao,
    ElementoBase,
    Laje,
    Material,
    MissingDataRequest,
    MuroSoubassement,
    Pilar,
    Sapata,
    Viga,
)

__all__ = [
    "AnalisePlanta",
    "Material",
    "Dimensao",
    "ElementoBase",
    "Sapata",
    "MuroSoubassement",
    "Armadura",
    "Laje",
    "Pilar",
    "Viga",
    "Abertura",
    "MissingDataRequest",
    "CrossCheckWarning",
    "PlansProError",
    "AutodeskError",
    "VisionAnalysisError",
    "SchemaValidationError",
    "MissingDataError",
    "OCRError",
]
