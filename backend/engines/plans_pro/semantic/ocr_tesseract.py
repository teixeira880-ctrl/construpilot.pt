"""OCR Tesseract-PT para thumbnails de plantas Autodesk (Fase E · Plans Pro).

Extrai texto PT de imagens de plantas, com pré-processamento (grayscale +
contraste + upscale), antes do pipeline LLM. Elementos deterministicamente
reconhecidos pelo léxico PT-BTP ganham `source="ocr"` em `AnalisePlanta`.

Fallback graceful: se `pytesseract` falhar ou não estiver disponível,
devolve `OCRResult(disponivel=False)` sem lançar excepções.
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from PIL import Image, ImageEnhance, ImageOps
from pydantic import BaseModel, Field

try:
    import pytesseract
    _TESS_DISPONIVEL = True
except ImportError:  # pragma: no cover
    _TESS_DISPONIVEL = False

logger = logging.getLogger(__name__)


class LinhaOCR(BaseModel):
    texto: str
    confidence: float  # 0-100 do Tesseract
    bbox: Optional[list[int]] = None  # [x, y, w, h]


class OCRResult(BaseModel):
    texto_completo: str
    linhas: list[LinhaOCR] = Field(default_factory=list)
    confidence_media: float = 0.0
    lingua: str = "por"
    disponivel: bool = True


def extrair_texto_thumbnail(image_bytes: bytes, lang: str = "por") -> OCRResult:
    """Extrai texto PT de uma thumbnail. Nunca lança excepção."""
    if not _TESS_DISPONIVEL or not image_bytes:
        return OCRResult(texto_completo="", confidence_media=0.0, disponivel=False)
    try:
        img = Image.open(BytesIO(image_bytes))
        # Pré-processamento: grayscale → contraste 1.5× → upscale (DPI alvo ~300)
        img = ImageOps.grayscale(img)
        img = ImageEnhance.Contrast(img).enhance(1.5)
        if img.width < 1200:
            escala = 1600 / max(img.width, 1)
            img = img.resize(
                (int(img.width * escala), int(img.height * escala)),
                Image.LANCZOS,
            )
        data = pytesseract.image_to_data(
            img, lang=lang, output_type=pytesseract.Output.DICT,
        )
        linhas: list[LinhaOCR] = []
        confs: list[float] = []
        for i, texto in enumerate(data["text"]):
            texto = (texto or "").strip()
            if not texto:
                continue
            try:
                conf = float(data["conf"][i])
            except (TypeError, ValueError):
                conf = 0.0
            if conf <= 0:
                continue
            linhas.append(LinhaOCR(
                texto=texto, confidence=conf,
                bbox=[
                    int(data["left"][i]), int(data["top"][i]),
                    int(data["width"][i]), int(data["height"][i]),
                ],
            ))
            confs.append(conf)
        texto_completo = " ".join(l.texto for l in linhas)
        confidence_media = sum(confs) / len(confs) if confs else 0.0
        return OCRResult(
            texto_completo=texto_completo, linhas=linhas,
            confidence_media=confidence_media, lingua=lang, disponivel=True,
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("OCR Tesseract falhou: %s — a continuar sem OCR", e)
        return OCRResult(texto_completo="", confidence_media=0.0, disponivel=False)


__all__ = ["LinhaOCR", "OCRResult", "extrair_texto_thumbnail"]
