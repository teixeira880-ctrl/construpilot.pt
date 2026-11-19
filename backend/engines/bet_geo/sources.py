"""Documentos do estudo com o ORIGINAL agarrado (imagem, DXF, DWG, IFC).

O resto do estudo BET continua a receber tuplos (nome, pdf_bytes); o motor bet_geo lê o
original exato quando existe. Compatível com todo o código que desempacota `for name, data in docs`.
"""
from __future__ import annotations

import hashlib
import io

IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp", ".gif", ".heic", ".heif")
_DXF_CACHE: dict[str, bytes] = {}          # sha256(DWG) → DXF já convertido (evita 2.ª conversão)


class Doc(tuple):
    """(nome, pdf) + .raw (bytes do original) + .kind ("image"|"dxf"|"dwg"|"ifc"|None)."""
    raw: bytes | None = None
    kind: str | None = None


def make(name: str, pdf: bytes, raw: bytes | None = None, kind: str | None = None) -> Doc:
    d = Doc((name, pdf))
    d.raw, d.kind = raw, kind
    return d


def kind_of(name: str, data: bytes) -> str | None:
    n = (name or "").lower()
    head = data[:64]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"ISO-10303-21") or n.endswith(".ifc"):
        return "ifc"
    if head[:4] == b"AC10" or n.endswith(".dwg"):
        return "dwg"
    if n.endswith(".dxf") or head.startswith(b"AutoCAD Binary DXF") or b"SECTION" in data[:200]:
        return "dxf"
    if n.endswith(IMAGE_EXT) or head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or head[:4] in (b"RIFF", b"II*\x00", b"MM\x00*"):
        return "image"
    return None


def image_to_pdf(data: bytes) -> bytes:
    """Imagem → PDF de uma página. Usa a resolução gravada na imagem se existir (digitalizações),
    senão 150 dpi; o tamanho de papel só é usado como escala se corresponder a um formato de desenho."""
    import pymupdf
    from PIL import Image

    try:
        from pillow_heif import register_heif_opener  # type: ignore
        register_heif_opener()
    except Exception:  # noqa: BLE001
        pass
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Exception as exc:  # noqa: BLE001
        raise ValueError("imagem ilegível — reimporte a fotografia ou a digitalização da planta") from exc
    dpi = im.info.get("dpi", (150, 150))[0] or 150
    im = im.convert("L")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    w_pt, h_pt = im.width / float(dpi) * 72, im.height / float(dpi) * 72
    out = pymupdf.open()
    page = out.new_page(width=w_pt, height=h_pt)
    page.insert_image(page.rect, stream=buf.getvalue())
    return out.tobytes()


def remember_dxf(dwg: bytes, dxf: bytes) -> None:
    if len(_DXF_CACHE) > 32:
        _DXF_CACHE.pop(next(iter(_DXF_CACHE)))
    _DXF_CACHE[hashlib.sha256(dwg).hexdigest()] = dxf


def cached_dxf(dwg: bytes) -> bytes | None:
    return _DXF_CACHE.get(hashlib.sha256(dwg).hexdigest())


def dedupe(docs: list) -> list:
    """Remove anexos repetidos mantendo o objeto (e o original agarrado)."""
    seen, out = set(), []
    for d in docs:
        h = hashlib.sha256(d[1]).hexdigest()
        if h not in seen:
            seen.add(h)
            out.append(d)
    return out


def ifc_preview_pdf(data: bytes) -> bytes:
    """IFC → planta PDF (A3, escala real 1:50–1:200) para os passos do estudo que só leem PDF."""
    from reportlab.lib.pagesizes import A3, landscape
    from reportlab.pdfgen import canvas

    from .cad import read_ifc

    b = read_ifc(data)
    W, H = landscape(A3)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    if b is not None:
        x0, y0, x1, y1 = b.footprint.bounds
        scale = next((s for s in (50, 100, 150, 200, 500) if (x1 - x0) * 1000 / s <= 380 and (y1 - y0) * 1000 / s <= 240), 500)
        k = 72 / 0.0254 / scale
        ox, oy = 20, 40

        def path(poly, fill):
            for ring in [poly.exterior, *poly.interiors]:
                pth = c.beginPath()
                cs = list(ring.coords)
                pth.moveTo(ox + cs[0][0] * k, oy + cs[0][1] * k)
                for x, y in cs[1:]:
                    pth.lineTo(ox + x * k, oy + y * k)
                pth.close()
                c.drawPath(pth, stroke=1, fill=fill)
        c.setFillGray(0.4)
        for w in b.walls:
            path(w.line.buffer(w.t / 2, cap_style=2), 1)
        c.setFillGray(1)
        path(b.footprint, 0)
        c.setFont("Helvetica", 12)
        c.drawString(W - 300, 40, f"PLANTA DO PISO 0 (modelo IFC)   ESCALA 1:{scale}")
    c.showPage()
    c.save()
    return buf.getvalue()
