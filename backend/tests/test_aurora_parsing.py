"""Testes unitários do contrato Aurora `/ask`.

Corre com: `cd /app/backend && python -m pytest tests/test_aurora_parsing.py -v`
"""
from __future__ import annotations

import pytest

from engines.aurora_contract import (
    AURORA_ANSWER_SCHEMA,
    AuroraCompanyAnswer,
    AuroraContractError,
    parse_aurora_company_answer,
)


def _valid_payload(text: str = "AURORA_API_OK") -> dict:
    return {
        "schema": AURORA_ANSWER_SCHEMA,
        "text": text,
        "model": "gpt-5.6-luna",
        "mode": "fast",
        "route": "openai/gpt-5.6-luna",
        "project_id": "prj_test",
        "resources_used": [],
        "external_ai_used": True,
        "deterministic": False,
        "family": "canonical_intelligence_router",
        "operation": "company.ask",
        "read_only": True,
        "side_effects": False,
    }


def test_valid_payload_parses_text():
    ans = parse_aurora_company_answer(_valid_payload("olá mundo"))
    assert isinstance(ans, AuroraCompanyAnswer)
    assert ans.text == "olá mundo"
    assert ans.model == "gpt-5.6-luna"
    assert ans.route == "openai/gpt-5.6-luna"
    assert ans.read_only is True


def test_empty_text_is_valid():
    """text='' é legítimo (modelo não gerou output) — não deve levantar."""
    ans = parse_aurora_company_answer(_valid_payload(""))
    assert ans.text == ""
    assert ans.schema_ == AURORA_ANSWER_SCHEMA


def test_missing_schema_raises():
    p = _valid_payload()
    del p["schema"]
    with pytest.raises(AuroraContractError, match="unexpected schema"):
        parse_aurora_company_answer(p)


def test_wrong_schema_raises():
    p = _valid_payload()
    p["schema"] = "openai.chat.completion"
    with pytest.raises(AuroraContractError, match="unexpected schema"):
        parse_aurora_company_answer(p)


def test_missing_text_raises():
    p = _valid_payload()
    del p["text"]
    with pytest.raises(AuroraContractError, match="missing required field 'text'"):
        parse_aurora_company_answer(p)


def test_non_string_text_raises():
    p = _valid_payload()
    p["text"] = 42
    with pytest.raises(AuroraContractError, match="must be str"):
        parse_aurora_company_answer(p)


def test_non_dict_raises():
    with pytest.raises(AuroraContractError, match="expected dict"):
        parse_aurora_company_answer("not a dict")
    with pytest.raises(AuroraContractError, match="expected dict"):
        parse_aurora_company_answer(None)


def test_extra_fields_preserved():
    """Aurora pode adicionar campos futuros — não devem quebrar o parsing."""
    p = _valid_payload()
    p["_future_field"] = "xpto"
    ans = parse_aurora_company_answer(p)
    assert ans.text == "AURORA_API_OK"


def test_openai_choices_format_rejected():
    """Formato OpenAI `choices[0].message.content` NÃO deve ser aceite."""
    openai_like = {
        "choices": [{"message": {"content": "hello"}}],
        "model": "gpt-4",
    }
    with pytest.raises(AuroraContractError, match="unexpected schema"):
        parse_aurora_company_answer(openai_like)


def test_model_and_route_preserved():
    p = _valid_payload()
    p["model"] = "claude-sonnet-4"
    p["route"] = "anthropic/claude-sonnet-4"
    ans = parse_aurora_company_answer(p)
    assert ans.model == "claude-sonnet-4"
    assert ans.route == "anthropic/claude-sonnet-4"
