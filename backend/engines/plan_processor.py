"""Plan Processor — extraction PDF/image pour ConstruPilot PLAN.

Deux pipelines :
- **PDF vectoriel** : extrait lignes, rectangles, textes, échelle via PyMuPDF.
- **PDF/JPG/PNG/WEBP raster** : convertit en images PNG par page pour affichage.

Retourne une structure normalisée (pages, texts, vectors, size, dpi).
"""
from __future__ import annotations

import io
import base64
import logging
import re

import pymupdf  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

def _detect_level_from_text(text: str) -> tuple[int, str] | None:
    """Renvoie (level_index, level_label) trouvé dans le texte de la page."""
    from engines.plan_page_context import level_candidates
    levels = level_candidates(text)
    return (levels[0]["level_index"], levels[0]["level_label"]) if len(levels) == 1 else None

# Regex pour repérer des cotes (dimensions en m ou cm) — sans les extraire, juste pour comptage
DIM_PATTERN = re.compile(r"\b\d{1,3}[.,]\d{1,2}\s*(?:m|cm|mm)\b", re.IGNORECASE)


def _detect_scale_from_text(text: str) -> int | None:
    """Cherche une échelle 1:X dans le texte extrait — retourne X ou None."""
    from engines.plan_page_context import scale_denominators
    scales = scale_denominators(text)
    return scales[0] if len(scales) == 1 else None


def _pil_to_png_bytes(img: Image.Image, max_side: int = 2400) -> bytes:
    """Redimensionne si trop grand + encode PNG."""
    w, h = img.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _encode_preview(img: Image.Image, max_side: int = 1800):
    """Encode l'aperçu d'une page en gardant le plus léger entre PNG (trait) et
    JPEG (photo). Retourne (b64, mime, final_w, final_h, ratio).

    Un plan multi-pages en PNG pleine résolution dépassait la limite BSON de
    16 Mo par document MongoDB → import KO. On redimensionne et on choisit le
    format le plus compact par page.
    """
    w, h = img.size
    ratio = 1.0
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((max(1, int(w * ratio)), max(1, int(h * ratio))), Image.LANCZOS)
    fw, fh = img.size
    pbuf = io.BytesIO()
    img.save(pbuf, format="PNG")
    png = pbuf.getvalue()
    jbuf = io.BytesIO()
    img.convert("RGB").save(jbuf, format="JPEG", quality=85, optimize=True)
    jpg = jbuf.getvalue()
    if len(jpg) < len(png):
        return _b64(jpg), "image/jpeg", fw, fh, ratio
    return _b64(png), "image/png", fw, fh, ratio


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def process_pdf(pdf_bytes: bytes, render_dpi: int = 200) -> dict:
    """Extrait pages + vecteurs + textes + rendu PNG d'un PDF."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages_out = []
    document_scales = set()
    # Résolution d'aperçu adaptée au nombre de pages (préserver la lisibilité des cotes
    # sur les plans 1 page, sans dépasser la limite BSON 16 Mo sur les PDF multi-pages).
    n_pages = doc.page_count
    max_side = 4200 if n_pages <= 3 else (2800 if n_pages <= 8 else 1800)
    for i, page in enumerate(doc):
        # --- Rendu image pour le viewer (JPEG/PNG adaptatif, redimensionné) ---
        pix = page.get_pixmap(dpi=render_dpi, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        img_b64, img_mime, fw, fh, ratio = _encode_preview(img, max_side=max_side)

        # --- Extraction texte ---
        text = page.get_text("text") or ""
        from engines.plan_page_context import scale_denominators
        document_scales.update(scale_denominators(text))

        # --- Extraction vectorielle (lignes / rectangles / dessins) ---
        vectors = []
        try:
            from engines.plan_vector_pdf import pdf_lines
            vectors = pdf_lines(page)
        except Exception as e:
            logger.warning(f"vector extract failed p{i}: {e}")

        # --- Textes localisés (pour OCR-like sans OCR) ---
        text_blocks = []
        try:
            from engines.plan_vector_pdf import pdf_text_blocks
            text_blocks = pdf_text_blocks(page)
        except Exception as e:
            logger.warning(f"text extract failed p{i}: {e}")

        # Import and refresh must share the same scale/view safeguards.
        from engines.plan_refresh import extract_pdf_page
        geometry = extract_pdf_page(page, render_dpi * ratio / 72, vectors=vectors, text_blocks=text_blocks)
        pages_out.append({
            **geometry,
            "index": i,
            "width_px": fw,
            "height_px": fh,
            "dpi": round(render_dpi * ratio, 2),
            "image_png_b64": img_b64,
            "img_mime": img_mime,
            "dimensions_count": len(DIM_PATTERN.findall(text)),
            "raw_text_length": len(text),
        })
    doc.close()
    return {
        "kind": "pdf",
        "page_count": len(pages_out),
        "pages": pages_out,
        "detected_scale_denominator": next(iter(document_scales)) if len(document_scales) == 1 else None,
    }


def process_image(image_bytes: bytes, mime: str) -> dict:
    """Traite une image simple (JPG/PNG/WEBP) — 1 seule page."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    original_size = img.size
    img_b64, img_mime, fw, fh, _ratio = _encode_preview(img, max_side=2400)
    return {
        "kind": "image",
        "page_count": 1,
        "pages": [{
            "index": 0,
            "width_px": fw,
            "height_px": fh,
            "dpi": 96,
            "image_png_b64": img_b64,
            "img_mime": img_mime,
            "vectors": [],
            "text_blocks": [],
            "dimensions_count": 0,
            "raw_text_length": 0,
            "source_mime": mime,
            "original_width_px": original_size[0],
            "original_height_px": original_size[1],
        }],
        "detected_scale_denominator": None,
    }


def process_upload(data: bytes, filename: str, mime: str, deskew: bool = False, cad_unit: str | None = None) -> dict:
    """Point d'entrée : dispatch vers PDF / DXF / image selon le mime type.
    Si `deskew` est True et que c'est une image, tente une correction de perspective.
    """
    lower = (filename or "").lower()
    if mime == "application/pdf" or lower.endswith(".pdf"):
        return process_pdf(data)
    if lower.endswith(".dxf") or mime in ("application/dxf", "image/vnd.dxf"):
        from engines.plan_dxf import process_dxf  # lazy import
        return process_dxf(data, filename, unit_override=cad_unit)
    if lower.endswith(".dwg") or mime in ("application/acad", "image/vnd.dwg"):
        from engines.plan_dxf import process_dwg
        return process_dwg(data, filename)  # raises helpful ValueError
    if mime in ("image/png", "image/jpeg", "image/jpg", "image/webp") or \
       lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
        if deskew:
            try:
                from engines.plan_cv import deskew_photo
                out = deskew_photo(data)
                if out["applied"]:
                    # Remplace les bytes par l'image warpée
                    data = base64.b64decode(out["image_png_b64"])
                    mime = "image/png"
            except Exception:
                pass  # si deskew échoue, on continue avec l'image originale
        return process_image(data, mime or "image/png")
    raise ValueError(f"Format non supporté : {mime or filename}")


# ============ Auto échelle en pixels/mètre (méthode A) ============

def auto_calibration_from_pdf_scale(scale_denominator: int, dpi: int) -> float | None:
    """Sur un PDF rendu à `dpi` avec une échelle 1:N détectée, calcule pixels_per_meter.

    À `dpi` = 150, 1 pouce papier = 150 px. Or 1 pouce = 0.0254 m.
    Donc 1 m PAPIER = 150 / 0.0254 = 5905.5 px.
    Le plan à 1:N signifie : 1 m réel = 1/N m papier = 5905.5/N pixels.
    """
    if not scale_denominator or scale_denominator <= 0 or dpi <= 0:
        return None
    px_per_paper_meter = dpi / 0.0254
    return round(px_per_paper_meter / scale_denominator, 4)
