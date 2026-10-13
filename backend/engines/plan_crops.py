"""Legible crops of a plan region: vector re-render (DXF analysis PDF / original PDF) when available, raster fallback."""
import base64
from io import BytesIO

from PIL import Image

TARGET_PX = 1000


def _norm_box(box, pad):
    x0, y0, x1, y1 = [min(1.0, max(0.0, float(v))) for v in box]
    # padding proportional to the box itself (a dimension a few metres long), never a fixed share of the sheet
    pad = min(pad, max(0.0008, 0.8 * max(abs(x1 - x0), abs(y1 - y0))))
    left, top = max(0.0, min(x0, x1) - pad), max(0.0, min(y0, y1) - pad)
    right, bottom = min(1.0, max(x0, x1) + pad), min(1.0, max(y0, y1) + pad)
    if right - left < 0.002:
        right = min(1.0, left + 0.002)
    if bottom - top < 0.002:
        bottom = min(1.0, top + 0.002)
    return left, top, right, bottom, (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))


def _relative(inner, outer):
    left, top, right, bottom = outer
    w, h = (right - left) or 1e-9, (bottom - top) or 1e-9
    return [(inner[0] - left) / w, (inner[1] - top) / h, (inner[2] - left) / w, (inner[3] - top) / h]


async def load_vector_pdf(db, plan_id: str, user_id: str) -> str | None:
    """Vector source when the plan came from CAD (cad_render) or a vector PDF (original_pdf); None for images/scans."""
    from engines.plan_sources import load_plan_source
    try:
        src = await load_plan_source(db, plan_id, user_id)
    except Exception:  # noqa: BLE001
        return None
    if src and src.get("mime") == "application/pdf" and src.get("source_kind") in ("cad_render", "original_pdf"):
        return src["data_b64"]
    return None


def crop_region(plan: dict, page_doc: dict, box: list[float], *, pad: float = 0.03) -> tuple[Image.Image, list[float]] | None:
    """Returns (crop image, box relative to the crop) or None. plan['vector_pdf_b64'] (see load_vector_pdf) enables a legible re-render."""
    left, top, right, bottom, inner = _norm_box(box, pad)
    rel = _relative(inner, (left, top, right, bottom))
    pdf_b64 = plan.get("vector_pdf_b64")
    if pdf_b64:
        import pymupdf
        with pymupdf.open(stream=base64.b64decode(pdf_b64), filetype="pdf") as doc:
            pg = doc[min(page_doc.get("index") or 0, len(doc) - 1)]
            rect = pg.rect
            clip = pymupdf.Rect(rect.x0 + left * rect.width, rect.y0 + top * rect.height, rect.x0 + right * rect.width, rect.y0 + bottom * rect.height)
            zoom = min(40.0, max(1.0, TARGET_PX / max(clip.width, clip.height)))
            pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=clip, alpha=False)
            return Image.open(BytesIO(pix.tobytes("png"))).convert("RGB"), rel
    b64 = page_doc.get("image_png_b64")
    if not b64:
        return None
    img = Image.open(BytesIO(base64.b64decode(b64))).convert("RGB")
    w, h = img.size
    crop = img.crop((int(left * w), int(top * h), max(int(right * w), int(left * w) + 4), max(int(bottom * h), int(top * h) + 4)))
    scale = min(4.0, max(1.0, 900 / max(crop.size)))
    if scale > 1:
        crop = crop.resize((int(crop.size[0] * scale), int(crop.size[1] * scale)), Image.LANCZOS)
    return crop, rel
