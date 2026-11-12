"""Uma recusa por limite / orçamento do plano nunca é contornada pelo recurso a outro fornecedor de IA."""
import os

from fastapi import HTTPException

os.environ.setdefault("STUDIES_MODEL_ANALYSIS", "x")
os.environ.setdefault("STUDIES_MODEL_LIGHT", "x")

from engines.assistant_fallback import friendly_error  # noqa: E402
from engines.openai_studies import QuotaError, StudiesError  # noqa: E402


def test_quota_error_is_a_studies_error_with_business_message():
    e = QuotaError("Orçamento mensal de IA do seu plano atingido.")
    assert isinstance(e, StudiesError) and friendly_error(e) == "Orçamento mensal de IA do seu plano atingido."
    assert friendly_error(HTTPException(402, "Orçamento IA esgotado")) == "Orçamento IA esgotado"


def test_assistant_route_skips_fallback_on_refusal():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "routes/assistant.py").read_text()
    assert 'refused = type(exc).__name__ == "QuotaError"' in src and "and not refused:" in src
