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
from typing import Iterable

import pymupdf  # PyMuPDF
from PIL import Image

logger = logging.getLogger(__name__)

# Regex pour repérer les échelles courantes dans le texte du plan
SCALE_PATTERNS = [
    re.compile(r"1\s*[:/]\s*(\d{2,4})"),
    re.compile(r"éch(?:elle)?\s*[:.]?\s*1\s*[:/]\s*(\d{2,4})", re.IGNORECASE),
    re.compile(r"scale\s*[:.]?\s*1\s*[:/]\s*(\d{2,4})", re.IGNORECASE),
]

# Détection de niveaux (RDC, R+1, R+2, sous-sol, combles) dans le texte d'une page
LEVEL_PATTERNS = [
    (re.compile(r"\bsous[\s-]?sol\b|\bcave\b|\bs[\s-]?sol\b", re.IGNORECASE), -1, "Sous-sol"),
    (re.compile(r"\brdc\b|\brez[\s-]?de[\s-]?chauss[éeè]e?\b", re.IGNORECASE), 0, "RDC"),
    (re.compile(r"\br\s*\+\s*(\d)\b|\b(\d)[eè]?[re]?\s*[eé]tage\b", re.IGNORECASE), None, None),
    (re.compile(r"\bcombles?\b|\bgrenier\b", re.IGNORECASE), 99, "Combles"),
]


def _detect_level_from_text(text: str) -> tuple[int, str] | None:
    """Renvoie (level_index, level_label) trouvé dans le texte de la page."""
    if not text:
        return None
    for rx, lvl, label in LEVEL_PATTERNS:
        m = rx.search(text)
        if m:
            if lvl is not None:
                return (lvl, label)
            # Cas R+X ou X étage
            for g in m.groups():
                if g and g.isdigit():
                    n = int(g)
                    return (n, f"R+{n}" if n > 0 else "RDC")
    return None

# Regex pour repérer des cotes (dimensions en m ou cm) — sans les extraire, juste pour comptage
DIM_PATTERN = re.compile(r"\b\d{1,3}[.,]\d{1,2}\s*(?:m|cm|mm)\b", re.IGNORECASE)


def _detect_scale_from_text(text: str) -> int | None:
    """Cherche une échelle 1:X dans le texte extrait — retourne X ou None."""
    for rx in SCALE_PATTERNS:
        m = rx.search(text)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                continue
    return None


def _pil_to_png_bytes(img: Image.Image, max_side: int = 2400) -> bytes:
    """Redimensionne si trop grand + encode PNG."""
    w, h = img.size
    if max(w, h) > max_side:
        ratio = max_side / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def process_pdf(pdf_bytes: bytes, render_dpi: int = 150) -> dict:
    """Extrait pages + vecteurs + textes + rendu PNG d'un PDF."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    pages_out = []
    detected_scale = None
    for i, page in enumerate(doc):
        # --- Rendu PNG pour le viewer ---
        pix = page.get_pixmap(dpi=render_dpi, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        png = _pil_to_png_bytes(img)

        # --- Extraction texte ---
        text = page.get_text("text") or ""
        if not detected_scale:
            detected_scale = _detect_scale_from_text(text)

        # --- Extraction vectorielle (lignes / rectangles / dessins) ---
        vectors = []
        try:
            drawings = page.get_drawings()
            for d in drawings:
                for item in d.get("items", []):
                    op = item[0]
                    if op == "l":  # line
                        p1, p2 = item[1], item[2]
                        vectors.append({"type": "line",
                                        "p1": [p1.x, p1.y], "p2": [p2.x, p2.y]})
                    elif op == "re":  # rectangle
                        r = item[1]
                        vectors.append({"type": "rect",
                                        "x": r.x0, "y": r.y0,
                                        "w": r.width, "h": r.height})
        except Exception as e:
            logger.warning(f"vector extract failed p{i}: {e}")

        # --- Textes localisés (pour OCR-like sans OCR) ---
        text_blocks = []
        try:
            for t in page.get_text("dict").get("blocks", []):
                if t.get("type") != 0:  # text block
                    continue
                for line in t.get("lines", []):
                    for span in line.get("spans", []):
                        s = (span.get("text") or "").strip()
                        if not s:
                            continue
                        bbox = span.get("bbox", [0, 0, 0, 0])
                        text_blocks.append({
                            "text": s,
                            "x": bbox[0], "y": bbox[1],
                            "w": bbox[2] - bbox[0], "h": bbox[3] - bbox[1],
                        })
        except Exception as e:
            logger.warning(f"text extract failed p{i}: {e}")

        pages_out.append({
            "index": i,
            "width_px": pix.width,
            "height_px": pix.height,
            "dpi": render_dpi,
            "image_png_b64": _b64(png),
            "vectors": vectors[:5000],   # cap pour éviter payloads énormes
            "text_blocks": text_blocks[:2000],
            "dimensions_count": len(DIM_PATTERN.findall(text)),
            "raw_text_length": len(text),
            "level_index": (_detect_level_from_text(text) or (None, None))[0],
            "level_label": (_detect_level_from_text(text) or (None, None))[1],
        })
    doc.close()
    return {
        "kind": "pdf",
        "page_count": len(pages_out),
        "pages": pages_out,
        "detected_scale_denominator": detected_scale,
    }


def process_image(image_bytes: bytes, mime: str) -> dict:
    """Traite une image simple (JPG/PNG/WEBP) — 1 seule page."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    original_size = img.size
    png = _pil_to_png_bytes(img)
    # Charge la taille finale (après resize éventuel)
    final = Image.open(io.BytesIO(png))
    return {
        "kind": "image",
        "page_count": 1,
        "pages": [{
            "index": 0,
            "width_px": final.width,
            "height_px": final.height,
            "dpi": 96,
            "image_png_b64": _b64(png),
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


def process_upload(data: bytes, filename: str, mime: str, deskew: bool = False) -> dict:
    """Point d'entrée : dispatch vers PDF / DXF / image selon le mime type.
    Si `deskew` est True et que c'est une image, tente une correction de perspective.
    """
    lower = (filename or "").lower()
    if mime == "application/pdf" or lower.endswith(".pdf"):
        return process_pdf(data)
    if lower.endswith(".dxf") or mime in ("application/dxf", "image/vnd.dxf"):
        from engines.plan_dxf import process_dxf  # lazy import
        return process_dxf(data, filename)
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
