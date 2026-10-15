"""BET.6 — Importação resiliente de PDF do Pedido de Construção.

Devolve sempre uma estrutura previsível:
  {
    status: "ok" | "error",
    code:   "PARSED" | "CORRUPTED_PDF" | "OCR_FAILED" |
            "SIZE_LIMIT" | "SCANNED_NO_OCR" | "EMPTY_PAGES",
    remediation: str,
    details: dict,
    data?: dict,
  }

Nunca lança exceção à chamada — todas as falhas viram códigos estruturados.
"""
from io import BytesIO
from typing import Any

PDF_MAGIC = b"%PDF-"
MAX_PDF_BYTES = 50 * 1024 * 1024  # 50 MB


def _check_ocr_available() -> bool:
    """Verifica se o stack OCR (pytesseract + pdf2image) está instalado."""
    try:
        import pytesseract  # noqa: F401
        import pdf2image  # noqa: F401
        return True
    except ImportError:
        return False


def parse_pc_pdf_resilient(data: bytes) -> dict[str, Any]:
    """Lê bytes de PDF e devolve estrutura resiliente (sem levantar)."""
    # 1) Tamanho
    size = len(data) if data else 0
    if size == 0:
        return {
            "status": "error",
            "code": "CORRUPTED_PDF",
            "remediation": "Ficheiro vazio — reenviar o PDF.",
            "details": {"size_bytes": 0},
        }
    if size > MAX_PDF_BYTES:
        return {
            "status": "error",
            "code": "SIZE_LIMIT",
            "remediation": (
                "PDF excede o limite (50 MB). Comprimir, dividir em "
                "secções ou reduzir resolução das imagens."
            ),
            "details": {"size_bytes": size, "max_bytes": MAX_PDF_BYTES},
        }

    # 2) Magic bytes
    if data[:5] != PDF_MAGIC:
        return {
            "status": "error",
            "code": "CORRUPTED_PDF",
            "remediation": (
                "Cabeçalho inválido (%PDF- em falta). Reexportar o "
                "ficheiro do software de origem."
            ),
            "details": {
                "size_bytes": size,
                "head_hex": data[:8].hex() if size >= 8 else data.hex(),
            },
        }

    # 3) Parsing com pypdf (se disponível)
    try:
        from pypdf import PdfReader
    except ImportError:
        return {
            "status": "error",
            "code": "CORRUPTED_PDF",
            "remediation": (
                "Dependência `pypdf` ausente no servidor. "
                "Instalar `pypdf` para análise de PDF."
            ),
            "details": {"missing_dep": "pypdf"},
        }

    try:
        reader = PdfReader(BytesIO(data))
        pages = list(reader.pages)
    except Exception as exc:
        return {
            "status": "error",
            "code": "CORRUPTED_PDF",
            "remediation": (
                "PDF corrompido ou protegido. Reexportar ou remover "
                "proteção antes de reenviar."
            ),
            "details": {
                "error": type(exc).__name__,
                "message": str(exc)[:200],
            },
        }

    if not pages:
        return {
            "status": "error",
            "code": "EMPTY_PAGES",
            "remediation": "PDF sem páginas — reexportar o documento.",
            "details": {"num_pages": 0},
        }

    # 4) Extração de texto
    texts: list[str] = []
    for page in pages:
        try:
            txt = page.extract_text() or ""
        except Exception:
            txt = ""
        texts.append(txt)
    full = "\n".join(texts).strip()

    if not full:
        # Provavelmente PDF escaneado — avalia OCR disponível
        if _check_ocr_available():
            return {
                "status": "error",
                "code": "OCR_FAILED",
                "remediation": (
                    "OCR disponível mas sem texto extraível. "
                    "Reenviar PDF com camada de texto embutida."
                ),
                "details": {"num_pages": len(pages)},
            }
        return {
            "status": "error",
            "code": "SCANNED_NO_OCR",
            "remediation": (
                "PDF escaneado sem camada de texto e OCR não instalado. "
                "Instalar `pytesseract` + `pdf2image` no servidor OU "
                "fornecer PDF com texto nativo."
            ),
            "details": {"num_pages": len(pages)},
        }

    return {
        "status": "ok",
        "code": "PARSED",
        "remediation": "",
        "details": {
            "num_pages": len(pages),
            "text_length": len(full),
        },
        "data": {"text": full},
    }
