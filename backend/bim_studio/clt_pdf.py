"""Extract dimension evidence from vector PDFs without inferring missing geometry."""
from __future__ import annotations

import hashlib
import base64
import re
from threading import Lock

import fitz

_NUMBER = r"([0-9]+(?:[.,][0-9]+)?)"
_AREA = re.compile(_NUMBER + r"\s*m(?:²|2|�)(?!\w)", re.I)
_HEIGHT = re.compile(r"\bceiling\s+height\s+" + _NUMBER + r"\s*mm\b", re.I)
_OPENING = re.compile(r"\b(?:opening|aperture|vão)\s*" + _NUMBER + r"\s*[x×]\s*" + _NUMBER + r"\s*H\b", re.I)
_LAYER = re.compile(r"\b(?:CLT(?:\s+Panel|\s+wall)?\s*(?:5s\s*)?\d|Plasterboard\b|\bXPS\s*\d|\bMineral\s*\d)", re.I)
_PDF_LOCK = Lock()


def _rect(page, bounds):
    r = fitz.Rect(bounds) * page.rotation_matrix
    return [round(v, 6) for v in (r.x0 / page.rect.width, r.y0 / page.rect.height,
                                  r.x1 / page.rect.width, r.y1 / page.rect.height)]


def _reading_lines(page):
    for block in page.get_text("dict", flags=fitz.TEXTFLAGS_TEXT)["blocks"]:
        lines = block.get("lines", [])
        for i, line in enumerate(lines):
            text = " ".join(span["text"] for span in line["spans"]).strip()
            if re.search(r"ceiling\s+height\s*$", text, re.I) and i + 1 < len(lines):
                following = lines[i + 1]
                next_text = " ".join(span["text"] for span in following["spans"]).strip()
                if re.fullmatch(_NUMBER + r"\s*mm", next_text, re.I):
                    yield text + " " + next_text, fitz.Rect(line["bbox"]) | fitz.Rect(following["bbox"])
                    continue
            yield text, line["bbox"]


def inspect_pdf(data, *, max_pages=30, include_review_images=False):
    if not data.startswith(b"%PDF-"):
        raise ValueError("O ficheiro não é um PDF.")
    from bim_studio.home_a_takeoff import SOURCE_SHA256, review_page

    checksum = hashlib.sha256(data).hexdigest()
    with _PDF_LOCK, fitz.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass or not 1 <= len(doc) <= max_pages:
            raise ValueError(f"Use um PDF sem senha, com 1 a {max_pages} folhas.")
        pages = []
        for page in doc:
            records = []
            for text, bounds in _reading_lines(page):
                candidates = (
                    ("declared_area", _AREA, "m²"),
                    ("ceiling_height", _HEIGHT, "mm"),
                    ("opening_dimensions", _OPENING, "mm"),
                    ("material_note", _LAYER, None),
                )
                for kind, pattern, unit in candidates:
                    for match in pattern.finditer(text):
                        if len(records) >= 500:
                            raise ValueError("Folha com mais de 500 referências. Divida o PDF.")
                        values = [] if kind == "material_note" else [
                            float(g.replace(",", ".")) for g in match.groups()
                        ]
                        if any(value <= 0 for value in values):
                            continue
                        records.append({
                            "id": f"p{page.number + 1}-{len(records) + 1}", "kind": kind,
                            "text": text[:250], "values": values, "unit": unit,
                            "rect": _rect(page, bounds), "source": "documented",
                            "requires_unit_confirmation": kind == "declared_area" and "�" in match.group(),
                        })
            info = {"page": page.number + 1, "width": page.rect.width, "height": page.rect.height,
                    "rotation": page.rotation, "evidence": records}
            if checksum == SOURCE_SHA256:
                info["review"] = review_page(page, records)
                if include_review_images:
                    scale = min(1.5, 1200 / max(page.rect.width, page.rect.height))
                    preview = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
                    jpeg = base64.b64encode(preview.tobytes("jpeg", jpg_quality=83)).decode("ascii")
                    info["image"] = "data:image/jpeg;base64," + jpeg
                    info["label"] = f"Folha {page.number + 1} · {info['review']['floor']}"
            pages.append(info)
    extras = None
    if checksum == SOURCE_SHA256:
        from bim_studio.home_a_takeoff import estimate_extras
        extras = estimate_extras(pages)
    return {"sha256": checksum, "pages": pages, "estimate_extras": extras,
            "status": "review_required", "fabrication_ready": False}


def render_page(data, number):
    with _PDF_LOCK, fitz.open(stream=data, filetype="pdf") as doc:
        if doc.needs_pass or not 1 <= number <= len(doc) <= 30:
            raise ValueError("Folha indisponível.")
        page = doc[number - 1]
        scale = min(1.5, 1280 / max(page.rect.width, page.rect.height))
        return page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False).tobytes("png")
