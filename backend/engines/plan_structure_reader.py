"""Lecture de plan structure/gros œuvre — pipeline PDF → géométrie → métré fiable.

1. Extraction vectorielle (PyMuPDF) : textes OCR + positions, échelle, rendu image HD.
2. Vision IA (Gemini 3 Pro) : qualification des éléments (semelles, poteaux, murs…).
3. SemanticReasoningEngine : règles dures (déduction de hauteur) + métré béton/acier
   déterministe + arrêt poli (MissingDataRequest) si donnée indispensable absente.
"""
from __future__ import annotations

import base64
import re

_SCALE_RE = re.compile(r"\b1\s*[:/]\s*(\d{1,4})\b")


class PlanVisionError(Exception):
    """Échec de la passe de lecture IA (quota/clé LLM, image illisible) — distinct d'un bug métier."""


def extract_vector_context(pdf_bytes: bytes) -> dict:
    """Textes + positions + échelle d'un PDF (idéalement vectoriel)."""
    import fitz  # PyMuPDF
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    texts: list[dict] = []
    raw_parts: list[str] = []
    vector = False
    for page in doc:
        d = page.get_text("dict")
        for block in d.get("blocks", []):
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    t = (span.get("text") or "").strip()
                    if not t:
                        continue
                    vector = True
                    bbox = span.get("bbox") or [0, 0, 0, 0]
                    texts.append({"text": t, "x": round(bbox[0], 1), "y": round(bbox[1], 1)})
                    raw_parts.append(t)
    raw_text = " ".join(raw_parts)
    m = _SCALE_RE.search(raw_text)
    scale = f"1/{m.group(1)}" if m else None
    page_count = doc.page_count
    doc.close()
    return {"vector": vector, "scale_detected": scale, "raw_text": raw_text[:8000],
            "texts": texts[:600], "page_count": page_count}


def render_pages_png(pdf_bytes: bytes, dpi: int = 170, max_pages: int = 3) -> list[str]:
    """Rendu base64 PNG des premières pages (pour la vision IA)."""
    import fitz
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    out: list[str] = []
    for page in list(doc)[:max_pages]:
        pix = page.get_pixmap(matrix=mat, alpha=False)
        out.append(base64.b64encode(pix.tobytes("png")).decode())
    doc.close()
    return out


def aggregate_metre(result) -> dict:
    """Totaux déterministes (béton m³, acier kg connu, comptages) depuis un ReasoningResult."""
    beton = 0.0
    acier = 0.0
    acier_complet = True
    nb_semelles = nb_poteaux = 0
    ml_lineaire = 0.0
    surface_murs = 0.0
    for f in result.fondations:
        if f.volume_beton_m3:
            beton += f.volume_beton_m3
        if f.armature and f.armature.total_kg is not None:
            acier += f.armature.total_kg
        else:
            acier_complet = False
        if f.type.startswith("semelle"):
            nb_semelles += f.nombre
        elif f.type == "poteau":
            nb_poteaux += f.nombre
        elif f.type in ("longrine", "chainage") and f.longueur_m:
            ml_lineaire += f.longueur_m
    for mur in result.murs:
        if mur.volume_m3:
            beton += mur.volume_m3
        if mur.surface_m2:
            surface_murs += mur.surface_m2
    return {
        "beton_total_m3": round(beton, 3),
        "acier_total_kg": round(acier, 1),
        "acier_complet": acier_complet,
        "nb_semelles": nb_semelles,
        "nb_poteaux": nb_poteaux,
        "lineaire_longrines_ml": round(ml_lineaire, 2),
        "surface_murs_m2": round(surface_murs, 2),
    }


async def read_plan(pdf_bytes: bytes, steel_ratios: dict | None = None) -> dict:
    """Pipeline complet. Retourne un dict sérialisable (jamais d'exception vers l'appelant)."""
    from fastapi.concurrency import run_in_threadpool
    from engines.ai import analyze_structure_plan
    from engines.semantic_reasoning import SemanticReasoningEngine, MissingDataError

    ctx = await run_in_threadpool(extract_vector_context, pdf_bytes)
    images = await run_in_threadpool(render_pages_png, pdf_bytes)
    try:
        vision = await analyze_structure_plan(images, ctx.get("raw_text", ""))
    except Exception as exc:  # noqa: BLE001
        raise PlanVisionError(str(exc)) from exc

    geometry = {
        "raw_text": vision.get("raw_text") or ctx.get("raw_text", ""),
        "texts": ctx.get("texts", []),
        "elements": vision.get("elements") or [],
        "murs": vision.get("murs") or [],
    }
    engine = SemanticReasoningEngine()
    # use_llm=False : la vision a déjà fait la classification ; ici règles dures + métré.
    try:
        result = await engine.reason(geometry, steel_ratios=steel_ratios, use_llm=False)
        complete = True
    except MissingDataError as e:
        result = e.partial
        complete = False

    return {
        "complete": complete,
        "scale_detected": vision.get("scale_detected") or ctx.get("scale_detected"),
        "vector": ctx.get("vector", False),
        "notes": vision.get("notes") or "",
        "fondations": [f.model_dump() for f in result.fondations],
        "murs": [m.model_dump() for m in result.murs],
        "missing_data": [md.model_dump() for md in result.missing_data],
        "deductions": result.deductions,
        "metre": aggregate_metre(result),
    }


async def recompute(fondations: list[dict], murs: list[dict], steel_ratios: dict | None) -> dict:
    """Recalcul déterministe après édition utilisateur (règles dures + métré + contrôle acier)."""
    from engines.semantic_reasoning import SemanticReasoningEngine, MissingDataError

    geometry = {"elements": fondations or [], "murs": murs or [], "raw_text": ""}
    engine = SemanticReasoningEngine()
    try:
        result = await engine.reason(geometry, steel_ratios=steel_ratios, use_llm=False)
        complete = True
    except MissingDataError as e:
        result = e.partial
        complete = False
    return {
        "complete": complete,
        "fondations": [f.model_dump() for f in result.fondations],
        "murs": [m.model_dump() for m in result.murs],
        "missing_data": [md.model_dump() for md in result.missing_data],
        "deductions": result.deductions,
        "metre": aggregate_metre(result),
    }
