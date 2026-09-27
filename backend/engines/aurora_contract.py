"""Contrato tipado da resposta Aurora Company API `/ask`.

Aurora devolve sempre um envelope com `schema=aurora.company-answer.v1` e
`text` (string, pode ser vazia legitimamente se o modelo não gerou output).
Todo o parsing DEVE passar por `parse_aurora_company_answer` — nunca ler
`choices[0]`, `message.content`, `output_text` ou similares (formatos de outros
providers).
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

AURORA_ANSWER_SCHEMA: str = "aurora.company-answer.v1"


class AuroraContractError(RuntimeError):
    """Resposta Aurora não respeita o contrato `aurora.company-answer.v1`."""


class AuroraAPIError(RuntimeError):
    """Erro HTTP/rede/negócio ao chamar Aurora. Nunca devolver texto vazio como sucesso."""

    def __init__(self, message: str, *, status: int | None = None,
                 code: str | None = None, correlation_id: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.correlation_id = correlation_id


class AuroraCompanyAnswer(BaseModel):
    """Envelope Aurora `/ask` (schema: aurora.company-answer.v1)."""

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    schema_: Literal["aurora.company-answer.v1"] = Field(alias="schema")
    text: str
    model: str | None = None
    route: str | None = None
    mode: str | None = None
    read_only: bool | None = None
    side_effects: bool | None = None
    project_id: str | None = None
    resources_used: list[Any] | None = None
    external_ai_used: bool | None = None
    deterministic: bool | None = None
    family: str | None = None
    operation: str | None = None


def parse_aurora_company_answer(data: Any) -> AuroraCompanyAnswer:
    """Parsing defensivo.

    - Exige `schema == "aurora.company-answer.v1"`.
    - Exige `text: str` (aceita string vazia — pode ser legítimo).
    - Nunca faz fallback silencioso para outros formatos.
    """
    if not isinstance(data, dict):
        raise AuroraContractError(f"expected dict, got {type(data).__name__}")

    got_schema = data.get("schema")
    if got_schema != AURORA_ANSWER_SCHEMA:
        raise AuroraContractError(
            f"unexpected schema: got={got_schema!r} expected={AURORA_ANSWER_SCHEMA!r}"
        )

    if "text" not in data:
        raise AuroraContractError("missing required field 'text'")
    if not isinstance(data["text"], str):
        raise AuroraContractError(
            f"'text' must be str, got {type(data['text']).__name__}"
        )

    try:
        return AuroraCompanyAnswer.model_validate(data)
    except ValidationError as e:  # noqa: BLE001
        raise AuroraContractError(f"validation failed: {e.errors()[:2]}") from e
