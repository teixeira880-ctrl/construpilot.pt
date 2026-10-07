"""Excepções tipadas do motor Plans Pro.

Objectivo:
    * Dar nome a cada família de erro (OpenAI, Autodesk, OCR, schema, ...).
    * Preservar o stacktrace completo via `logger.exception()` em `__init__`
      → resolve a queixa #10 da auditoria: `except Exception` com
      `logger.warning("foo: %s", type(e).__name__)` apagava a origem.

Regra: cada excepção DEVE ser levantada com `raise XxxError(...) from e`
quando encadeada a uma excepção anterior.
"""
from __future__ import annotations

import logging

from engines.plans_pro.semantic.schemas import MissingDataRequest

logger = logging.getLogger("plans_pro.exceptions")


class PlansProError(Exception):
    """Base de todas as excepções do motor Plans Pro.

    Loga automaticamente stacktrace completo (via `logger.exception`) no
    momento da construção, para auditoria em produção.
    """

    def __init__(self, message: str) -> None:
        super().__init__(message)
        # Loga o stacktrace completo. Capturamos stack_info=True para dar
        # contexto mesmo quando `from e` não é usado.
        logger.exception("PlansProError: %s", message, stack_info=False)


class AutodeskError(PlansProError):
    """Falha a comunicar com Autodesk APS (OSS, Model Derivative, ...)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        aps_message: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.aps_message = aps_message
        detail = f"{message} [status={status_code}, aps='{(aps_message or '')[:200]}']"
        super().__init__(detail)


class VisionAnalysisError(PlansProError):
    """Falha no provedor de visão (OpenAI gpt-4o, Claude vision, ...)."""

    def __init__(self, message: str, *, provider: str) -> None:
        self.provider = provider
        super().__init__(f"[{provider}] {message}")


class SchemaValidationError(PlansProError):
    """Resposta do LLM não bate certo com o schema Pydantic.

    O caminho antigo tentava reparar o JSON (`_extract_json` tolerante).
    O novo caminho REJEITA — se cair aqui, a rota devolve
    `missing_data` ao utilizador em vez de inventar.
    """

    def __init__(self, message: str, *, raw_response: str) -> None:
        # Trunca para não poluir logs
        self.raw_response = raw_response[:2000]
        super().__init__(f"{message} [raw_response_truncated={self.raw_response[:300]!r}]")


class MissingDataError(PlansProError):
    """Dado crítico em falta → embalado como pergunta para o utilizador.

    Esta excepção NÃO deve chegar à UI como 500. A rota apanha-a e
    traduz para `AnalisePlanta.missing_data` com HTTP 200.
    """

    def __init__(self, request: MissingDataRequest) -> None:
        self.request = request
        super().__init__(
            f"Dado em falta: {request.field} "
            f"(criticidade={request.criticidade}, pergunta='{request.question_pt[:120]}')"
        )


class OCRError(PlansProError):
    """Reservado para a Fase 2 (pipeline OCR dedicado).

    Mantemos a classe aqui para que o `routes/plans_pro.py` possa já
    apanhá-la com `except OCRError` sem futuras alterações estruturais.
    """

    def __init__(self, message: str) -> None:
        super().__init__(f"[OCR] {message}")


__all__ = [
    "PlansProError",
    "AutodeskError",
    "VisionAnalysisError",
    "SchemaValidationError",
    "MissingDataError",
    "OCRError",
]
