"""Extração ligeira de DXF para envio a Aurora `/ask`.

Diferente de `plan_dxf.process_dxf()` (que renderiza preview PNG + bounds),
esta função devolve apenas dados estruturados compactos para caber no
budget de contexto do Aurora (~700-1000 chars).
"""
from __future__ import annotations

import io
from collections import Counter
from typing import Any


def extract_dxf_summary(dxf_bytes: bytes) -> dict[str, Any]:
    """Devolve resumo compacto de um DXF (entidades, layers, textos, bounds).

    Nunca levanta exceção — em caso de erro devolve `{"error": "..."}`.
    """
    try:
        import ezdxf
        from ezdxf.recover import read as recover_read
    except ImportError:
        return {"error": "ezdxf não instalado."}

    # ezdxf lê a partir de stream de texto; usar recover para maior tolerância
    try:
        doc, auditor = recover_read(io.BytesIO(dxf_bytes))
    except Exception as e:  # noqa: BLE001
        try:
            # fallback: tentar leitura direta
            text_stream = io.StringIO(dxf_bytes.decode("utf-8", errors="ignore"))
            doc = ezdxf.read(text_stream)
        except Exception as e2:  # noqa: BLE001
            return {"error": f"dxf_parse_failed: {type(e2).__name__}"}

    msp = doc.modelspace()

    counters: Counter = Counter()
    texts: list[str] = []
    layers = [layer.dxf.name for layer in doc.layers][:30]
    dims: list[str] = []
    min_x = min_y = float("inf")
    max_x = max_y = float("-inf")

    def _update_bbox(x: float, y: float) -> None:
        nonlocal min_x, min_y, max_x, max_y
        if x < min_x: min_x = x
        if x > max_x: max_x = x
        if y < min_y: min_y = y
        if y > max_y: max_y = y

    for e in msp:
        dtype = e.dxftype()
        counters[dtype] += 1

        # texto
        if dtype in ("TEXT", "MTEXT"):
            try:
                content = e.dxf.text if dtype == "TEXT" else e.text
                content = str(content or "").strip()
                if content and len(texts) < 40:
                    # limpar tags DXF de MTEXT (\P, \A, {, }, etc.)
                    clean = content.replace("\\P", " ").replace("\\A1;", "")
                    clean = clean.replace("{", "").replace("}", "")
                    if len(clean) <= 120:
                        texts.append(clean)
            except Exception:  # noqa: BLE001
                pass

        # dimensão (mostra measure)
        if "DIMENSION" in dtype:
            try:
                if hasattr(e, "get_measurement"):
                    m = e.get_measurement()
                    if m and len(dims) < 20:
                        dims.append(f"{float(m):.2f}")
            except Exception:  # noqa: BLE001
                pass

        # bbox — só endpoints das entidades comuns
        try:
            if dtype == "LINE":
                _update_bbox(e.dxf.start.x, e.dxf.start.y)
                _update_bbox(e.dxf.end.x, e.dxf.end.y)
            elif dtype == "CIRCLE":
                cx, cy, r = e.dxf.center.x, e.dxf.center.y, e.dxf.radius
                _update_bbox(cx - r, cy - r)
                _update_bbox(cx + r, cy + r)
            elif dtype in ("LWPOLYLINE", "POLYLINE"):
                if hasattr(e, "get_points"):
                    for pt in e.get_points():
                        _update_bbox(float(pt[0]), float(pt[1]))
                elif hasattr(e, "points"):
                    for pt in e.points():
                        _update_bbox(float(pt[0]), float(pt[1]))
        except Exception:  # noqa: BLE001
            pass

    width = height = None
    if min_x != float("inf"):
        width = round(max_x - min_x, 3)
        height = round(max_y - min_y, 3)

    return {
        "num_entities": sum(counters.values()),
        "entity_counts": dict(counters.most_common(12)),
        "num_layers": len(doc.layers),
        "layers_sample": layers,
        "texts_sample": texts,
        "dimensions_sample": dims,
        "bbox": (
            {"min_x": round(min_x, 3), "min_y": round(min_y, 3),
             "max_x": round(max_x, 3), "max_y": round(max_y, 3),
             "width": width, "height": height}
            if min_x != float("inf") else None
        ),
        "dxf_version": getattr(doc, "dxfversion", None),
        "units_raw": getattr(doc.header, "get", lambda *_: None)("$INSUNITS", None),
    }


def summarize_for_prompt(summary: dict[str, Any], max_chars: int = 700) -> str:
    """Serializa o summary para texto plano compacto (~500-700 chars) para prompt Aurora."""
    if "error" in summary:
        return f"[erro extração DXF: {summary['error']}]"

    lines: list[str] = []
    ec = summary.get("entity_counts") or {}
    if ec:
        top = ", ".join(f"{k}:{v}" for k, v in list(ec.items())[:8])
        lines.append(f"Entidades: {top}")
    bbox = summary.get("bbox")
    if bbox and bbox.get("width") is not None:
        lines.append(f"Bounds: {bbox['width']:.1f}×{bbox['height']:.1f} unid")
    layers = summary.get("layers_sample") or []
    if layers:
        lines.append(f"Layers({len(layers)}): {', '.join(layers[:10])}")
    texts = summary.get("texts_sample") or []
    if texts:
        joined = " · ".join(texts[:12])[:280]
        lines.append(f"Textos: {joined}")
    dims = summary.get("dimensions_sample") or []
    if dims:
        lines.append(f"Cotas: {', '.join(dims[:8])}")

    out = " | ".join(lines)
    return out[:max_chars]
