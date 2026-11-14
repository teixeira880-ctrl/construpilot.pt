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


def estimate_input(report: dict) -> dict | None:
    """Complete estimate input of the reviewed sheets (server-side twin of floorsFromReport on the CLT page): walls by
    thickness, CLT panels, linings and façade areas, rooms, windows, run rectangles and lintels. None when the report
    has no reviewed sheets."""
    pages = [p for p in report["pages"] if (p.get("review") or {}).get("in_scope")]
    offsets = next((p["review"]["structural_offsets"] for p in report["pages"] if (p.get("review") or {}).get("structural_offsets")), None)
    if not pages or not offsets:
        return None
    keys, floors = ["RDC", "+1"], []

    def interior_faces(run, runs, width, height):
        x, y, X, Y = run["rect"]
        others = [r for r in runs if r is not run]
        if (X - x) * width > (Y - y) * height:
            m = (x + X) / 2
            hit = lambda test: any(r["rect"][0] <= m <= r["rect"][2] and test(r["rect"]) for r in others)
            return int(hit(lambda r: r[3] <= y + 1e-6)) + int(hit(lambda r: r[1] >= Y - 1e-6))
        m = (y + Y) / 2
        hit = lambda test: any(r["rect"][1] <= m <= r["rect"][3] and test(r["rect"]) for r in others)
        return int(hit(lambda r: r[2] <= x + 1e-6)) + int(hit(lambda r: r[0] >= X - 1e-6))

    for i, page in enumerate(pages):
        key = keys[i] if i < len(keys) else page["review"]["floor"]
        ceilings = [e["values"][0] / 1000 for e in page["evidence"] if e["kind"] == "ceiling_height"]
        extra = offsets.get(key) or offsets[keys[-1]]
        runs = [m for m in page["review"]["markers"] if m.get("length_m")]
        by = {}
        for m in runs:
            t = round(m["drawing_width_mm"] / 10) * 10
            by[t] = by.get(t, 0.0) + m["length_m"]
        height = max(ceilings) + extra["floor_buildup_m"] + extra["ceiling_zone_m"] if ceilings else 0
        inner = sum(m["length_m"] * interior_faces(m, runs, page["width"], page["height"]) for m in runs)
        h = height or (3 if i == 0 else 2.5)
        faces = inner * h
        outer = (2 * sum(m["length_m"] for m in runs) - inner) * h
        more = ((report.get("estimate_extras") or {}).get("floors") or {}).get(key) or {}
        ceiling = more.get("ceiling_m2") or 0
        floors.append({
            "name": key, "height_m": f"{height:.3f}" if height else None,
            "walls": [{"thickness_mm": str(t), "layers": 5, "length_m": f"{length:.3f}"} for t, length in by.items()],
            "panels": [{**p, "thickness_mm": str(p["thickness_mm"]), "layers": p["layers"], "area_m2": str(p["area_m2"])} for p in more.get("panels") or []],
            "board_layers_m2": f"{2 * faces:.2f}", "paint_m2": f"{faces + ceiling:.2f}", "ceiling_m2": f"{ceiling:.2f}",
            "slab_buildup_m2": str(more.get("slab_buildup_m2") or 0), "roof_buildup_m2": str(more.get("roof_buildup_m2") or 0),
            "facade_m2": f"{outer:.2f}", "steel_beam_m": str(more.get("steel_beam_m") or 0),
            "rooms": more.get("rooms") or [], "windows": more.get("windows") or [], "interior_doors": more.get("interior_doors") or 0,
            "ceiling_height_m": more.get("ceiling_height_m"), "riser_m": more.get("riser_m"),
            "segments": [{"ref": m["id"], "thickness_mm": str(round(m["drawing_width_mm"] / 10) * 10), "length_m": f"{m['length_m']:.3f}",
                          "rect_m": m.get("plan_rect_m")} for m in runs],
            "lintels": [{"ref": m["id"], "rect_m": m["plan_rect_m"], "head_m": m["head_m"], "thickness_mm": m.get("thickness_mm")}
                        for m in page["review"]["markers"] if m["id"].startswith("lintel-") and m.get("plan_rect_m") and m.get("head_m")]})
    return {"floors": floors}
