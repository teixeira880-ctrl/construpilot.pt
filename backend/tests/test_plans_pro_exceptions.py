"""Testes das excepções tipadas do motor Plans Pro.

Verifica que cada excepção:
    * Herda de `PlansProError`.
    * Loga stacktrace (via `logger.exception`) na construção.
    * Preserva informação específica (`provider`, `raw_response`, ...).
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("JWT_SECRET", "test-secret")

from engines.plans_pro.semantic.exceptions import (  # noqa: E402
    AutodeskError,
    MissingDataError,
    OCRError,
    PlansProError,
    SchemaValidationError,
    VisionAnalysisError,
)
from engines.plans_pro.semantic.schemas import MissingDataRequest  # noqa: E402


class TestHierarquia:
    def test_todas_herdam_de_plans_pro_error(self):
        subclasses = (
            AutodeskError, VisionAnalysisError, SchemaValidationError,
            OCRError,
        )
        for cls in subclasses:
            assert issubclass(cls, PlansProError)


class TestAutodeskError:
    def test_preserva_status_e_message(self):
        err = AutodeskError(
            "falha ao traduzir",
            status_code=502,
            aps_message="BAD_GATEWAY",
        )
        assert err.status_code == 502
        assert err.aps_message == "BAD_GATEWAY"
        assert "502" in str(err)
        assert "BAD_GATEWAY" in str(err)


class TestVisionAnalysisError:
    def test_preserva_provider(self):
        err = VisionAnalysisError("timeout", provider="openai")
        assert err.provider == "openai"
        assert "[openai]" in str(err)


class TestSchemaValidationError:
    def test_trunca_raw_response(self):
        enorme = "a" * 5000
        err = SchemaValidationError("falha", raw_response=enorme)
        assert len(err.raw_response) <= 2000

    def test_preserva_inicio_raw(self):
        err = SchemaValidationError("falha", raw_response="{inicio_relevante}")
        assert "{inicio_relevante}" in err.raw_response


class TestMissingDataError:
    def test_preserva_request(self):
        req = MissingDataRequest(
            question_pt="Qual é o rácio?",
            field="x", unit=None, element_id=None,
            suggested_default=None, criticidade="bloqueante",
        )
        err = MissingDataError(req)
        assert err.request is req
        assert "x" in str(err)
        assert "bloqueante" in str(err)


class TestOCRError:
    def test_prefixo(self):
        err = OCRError("texto não legível")
        assert "[OCR]" in str(err)


class TestLoggingStacktrace:
    """Verifica que a construção da excepção loga via `logger.exception`."""

    def test_logger_exception_e_chamado(self, caplog):
        caplog.set_level(logging.ERROR, logger="plans_pro.exceptions")
        try:
            raise ValueError("origem")
        except ValueError as e:
            try:
                raise AutodeskError("wrapper", status_code=500) from e
            except AutodeskError:
                pass
        # Entrada ERROR foi registada pelo construtor
        assert any(
            r.name == "plans_pro.exceptions" and r.levelno >= logging.ERROR
            for r in caplog.records
        ), "PlansProError devia chamar logger.exception na construção"

    def test_schema_error_tambem_loga(self, caplog):
        caplog.set_level(logging.ERROR, logger="plans_pro.exceptions")
        SchemaValidationError("falha", raw_response="x" * 100)
        assert any(
            r.name == "plans_pro.exceptions" and r.levelno >= logging.ERROR
            for r in caplog.records
        )
