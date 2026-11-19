"""Imagens reais do edifício (geometria real) em TODOS os PDF do estudo: capa com a perspetiva principal e
página de vistas no processo. As imagens são as mesmas do orçamento (cache por geometria em db.house_renders)."""
from __future__ import annotations

import datetime as _dt
import io
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .outputs import _t

GREEN = colors.HexColor("#0f3d2e")
LABELS = {"main": "Perspetiva principal", "side": "Perspetiva lateral", "rear": "Perspetiva posterior", "aerial": "Vista aérea"}


def local_views(b, slab_h: float, keys=("main", "aerial")) -> dict[str, bytes]:
    """Sem base de dados (testes / falha): vistas calculadas da geometria real (sem IA)."""
    from . import views as V
    out = {}
    for k in keys:
        try:
            png, _ = V.computed_and_mask(b, k, 1600, 900)
            out[k] = png
        except Exception:  # noqa: BLE001
            continue
    return out


def _img(c, data: bytes, x, y, w, h):
    ir = ImageReader(io.BytesIO(data))
    iw, ih = ir.getSize()
    k = max(w / iw, h / ih)                       # preencher (corte ao centro)
    dw, dh = iw * k, ih * k
    c.saveState()
    p = c.beginPath()
    p.rect(x, y, w, h)
    c.clipPath(p, stroke=0, fill=0)
    c.drawImage(ir, x + (w - dw) / 2, y + (h - dh) / 2, dw, dh)
    c.restoreState()


def cover_pdf(images: dict[str, bytes], title: str, subtitle: str, meta: dict, lines: list[str], landscape_a3=False,
              caption: str = "") -> bytes:
    buf = io.BytesIO()
    size = landscape(A3) if landscape_a3 else A4
    W, H = size
    c = canvas.Canvas(buf, pagesize=size)
    main = images.get("main") or next(iter(images.values()), None)
    c.setFillColor(GREEN)
    c.rect(0, H - 34 * mm, W, 34 * mm, stroke=0, fill=1)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(15 * mm, H - 12 * mm, _t(meta.get("company") or "ConstruPilot"))
    c.setFont("Helvetica-Bold", 20 if not landscape_a3 else 24)
    c.drawString(15 * mm, H - 25 * mm, _t(title))
    c.setFont("Helvetica", 10)
    c.drawRightString(W - 15 * mm, H - 12 * mm, _dt.date.today().strftime("%d/%m/%Y"))
    top = H - 40 * mm
    img_h = (H * 0.52) if not landscape_a3 else (H * 0.60)
    if main:
        _img(c, main, 15 * mm, top - img_h, W - 30 * mm, img_h)
        c.setFont("Helvetica-Oblique", 7.5)
        c.setFillColor(colors.HexColor("#4b5563"))
        c.drawString(15 * mm, top - img_h - 4 * mm, _t(caption or "Imagem do edifício calculada sobre a geometria real lida nas plantas (motores internos, sem IA generativa)."))
    y = top - img_h - 14 * mm
    c.setFillColor(colors.HexColor("#111827"))
    c.setFont("Helvetica-Bold", 14)
    c.drawString(15 * mm, y, _t(subtitle))
    y -= 8 * mm
    c.setFont("Helvetica", 10)
    for s in [f"Obra: {meta.get('obra', '-')}", f"Local: {meta.get('local') or '-'}"] + list(lines):
        c.drawString(15 * mm, y, _t(s)[:120])
        y -= 5.6 * mm
        if y < 25 * mm:
            break
    c.setFont("Helvetica", 7.5)
    c.setFillColor(colors.HexColor("#6b7280"))
    c.drawString(15 * mm, 12 * mm, _t("ConstruPilot — estudo gerado por motores determinísticos sobre a geometria real; "
                                    "a validar e assinar pelos técnicos responsáveis antes da execução."))
    c.showPage()
    c.save()
    return buf.getvalue()


def gallery_pdf(images: dict[str, bytes], meta: dict) -> bytes | None:
    keys = [k for k in ("main", "side", "rear", "aerial") if images.get(k)]
    if not keys:
        return None
    buf = io.BytesIO()
    W, H = A4
    c = canvas.Canvas(buf, pagesize=A4)
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(GREEN)
    c.drawString(15 * mm, H - 20 * mm, "Imagens do edifício — geometria real")
    slot_h = (H - 45 * mm) / max(2, len(keys)) - 8 * mm
    y = H - 28 * mm
    for k in keys:
        _img(c, images[k], 15 * mm, y - slot_h, W - 30 * mm, slot_h)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#374151"))
        c.drawString(15 * mm, y - slot_h - 4 * mm, _t(LABELS.get(k, k)))
        y -= slot_h + 9 * mm
    c.showPage()
    c.save()
    return buf.getvalue()


def prepend(pdf: Path, cover: bytes) -> Path:
    import pymupdf
    doc = pymupdf.open(str(pdf))
    cov = pymupdf.open(stream=cover, filetype="pdf")
    cov.insert_pdf(doc)
    tmp = pdf.with_suffix(".tmp.pdf")
    cov.save(str(tmp), garbage=3, deflate=True)
    tmp.replace(pdf)
    return pdf


def merge(parts: list, out: Path) -> Path:
    """parts: caminhos ou bytes de PDF, por ordem."""
    import pymupdf
    doc = pymupdf.open()
    for p in parts:
        if p is None:
            continue
        src = pymupdf.open(stream=p, filetype="pdf") if isinstance(p, (bytes, bytearray)) else pymupdf.open(str(p))
        doc.insert_pdf(src)
    doc.save(str(out), garbage=3, deflate=True)
    return out
