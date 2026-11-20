"""PDF grandes (> 30 folhas) → ficheiro ZIP com o PDF completo e partes de 30 folhas no máximo.

Pedido do Martinho (20/11): no telemóvel os processos de 50–60 páginas são pesados de abrir; o Assistente entrega
sempre também um ZIP. As partes conservam a ordem e dizem as folhas que contêm."""
from __future__ import annotations

import io
import re
import zipfile

MAX_PAGES = 30


def page_count(data: bytes) -> int:
    try:
        import pymupdf
        return pymupdf.open(stream=data, filetype="pdf").page_count
    except Exception:  # noqa: BLE001
        return 0


def split_zip(data: bytes, name: str, max_pages: int = MAX_PAGES, lang: str = "pt") -> bytes | None:
    """ZIP (PDF completo + partes ≤ max_pages) se o PDF tiver mais de max_pages folhas; senão None."""
    import pymupdf
    try:
        src = pymupdf.open(stream=data, filetype="pdf")
    except Exception:  # noqa: BLE001
        return None
    n = src.page_count
    if n <= max_pages:
        return None
    stem = re.sub(r"\.pdf$", "", name or "documento", flags=re.I)
    parts = (n + max_pages - 1) // max_pages
    word = {"fr": ("partie", "pages"), "en": ("part", "pages")}.get(lang[:2], ("parte", "folhas"))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"{stem}.pdf", data)
        for k in range(parts):
            a, b = k * max_pages, min(n, (k + 1) * max_pages)
            out = pymupdf.open()
            out.insert_pdf(src, from_page=a, to_page=b - 1)
            z.writestr(f"{stem}_{word[0]}_{k + 1}_de_{parts}_{word[1]}_{a + 1}-{b}.pdf", out.tobytes(garbage=3, deflate=True))
    return buf.getvalue()
