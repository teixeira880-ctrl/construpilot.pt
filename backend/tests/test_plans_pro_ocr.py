"""Testes da integração OCR Tesseract-PT no pipeline Plans Pro (Fase E)."""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engines.plans_pro.semantic.materials_pt import reconhecer_material  # noqa: E402
from engines.plans_pro.semantic.ocr_tesseract import (  # noqa: E402
    OCRResult, extrair_texto_thumbnail,
)


FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "plans_pro"
    / "thumbnail_moradia_sintetica.png"
)


def _bytes_fixture() -> bytes:
    # Garante que a fixture existe (idempotente)
    if not FIXTURE.exists():
        from scripts.gerar_fixture_ocr import gerar  # noqa: WPS433
        gerar(force=True)
    return FIXTURE.read_bytes()


def test_ocr_extrai_texto_pt_de_fixture_sintetica():
    img = _bytes_fixture()
    r = extrair_texto_thumbnail(img, lang="por")
    assert r.disponivel is True
    assert r.confidence_media > 40, f"confidence insuficiente: {r.confidence_media}"
    texto_up = r.texto_completo.upper()
    # Pelo menos um dos marcadores PT-BTP tem de ser detectado
    assert any(marker in texto_up for marker in (
        "PLANTA", "MORADIA", "COBERTURA", "TELHA", "SAPATA", "AREA",
        "C25", "A500", "VAR", "PP",
    )), f"nenhum marcador PT-BTP detectado em: {r.texto_completo!r}"
    assert len(r.linhas) > 0


def test_lexico_pt_btp_reconhece_material_do_ocr():
    mat = reconhecer_material("PP e=20")
    assert mat is not None, "'PP e=20' deveria mapear a alvenaria 20 cm"
    assert mat.categoria.lower() in ("alvenaria", "parede")


def test_ocr_fallback_quando_tesseract_indisponivel():
    """Com `_TESS_DISPONIVEL=False`, devolve `disponivel=False` sem crash."""
    with patch("engines.plans_pro.semantic.ocr_tesseract._TESS_DISPONIVEL", False):
        r = extrair_texto_thumbnail(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    assert isinstance(r, OCRResult)
    assert r.disponivel is False
    assert r.texto_completo == ""
    assert r.confidence_media == 0.0


def test_ocr_bytes_vazios_graceful():
    r = extrair_texto_thumbnail(b"")
    assert r.disponivel is False
    assert r.texto_completo == ""


@pytest.mark.anyio
async def test_plan_vision_integra_ocr_no_trace():
    """Mocka o LLM e confirma que o trace contém `ocr_disponivel`."""
    from engines.plans_pro import plan_vision
    from engines.plans_pro.semantic.schemas import AnalisePlanta

    analise_fake = AnalisePlanta(
        plan_id="p1",
        elementos=[],
        missing_data=[],
        warnings=[],
        confidence_global=0.8,
        requires_human_review=False,
    )

    async def _fake_llm(**_kw):
        return analise_fake, {"model_used": "fake", "duration_s": 0.01}

    with patch.object(plan_vision, "analisar_com_structured_output", _fake_llm):
        res = await plan_vision.full_analysis(
            plan_id="p1", filename="t.pdf",
            metadata={"views": [{"name": "P0"}]},
            thumbnail_bytes=_bytes_fixture(),
            thumbnail_mime="image/png",
            project_hint="moradia T3",
        )
    assert "ocr_disponivel" in res.trace
    # Com fixture real, OCR deve ter funcionado
    assert res.trace["ocr_disponivel"] is True
    assert res.trace["ocr_linhas_count"] > 0
    assert "ocr_confidence_media" in res.trace
