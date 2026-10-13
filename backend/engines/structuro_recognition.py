"""StructuroPilot — reconnaissance de plans importés (première passe, honnête).

DXF : inventaire brut des entités via ezdxf (types, calques, unités, étendue) — marqué
« reconnaissance non vérifiée ». PDF/image : aucun objet vectoriel fiable extrait
automatiquement → document stocké pour référence, l'utilisateur cale l'échelle sur une
cote connue. Aucune cote n'est déduite d'un agrandissement ou d'un trait.
"""
from __future__ import annotations

import io


def _recognize_dxf(data: bytes) -> dict:
    try:
        import ezdxf
        doc = ezdxf.read(io.StringIO(data.decode("utf-8", "ignore")))
    except Exception as e:
        return {"kind": "dxf", "objects_detected": False,
                "note": f"DXF illisible automatiquement ({str(e)[:80]}). Fichier stocké ; "
                        "saisie manuelle de la géométrie requise.", "summary": {}}
    msp = doc.modelspace()
    counts: dict[str, int] = {}
    for e in msp:
        counts[e.dxftype()] = counts.get(e.dxftype(), 0) + 1
    try:
        from engines.cad_geometry import resolve_units
        unit_to_m = resolve_units(doc)
    except Exception:
        unit_to_m = None
    layers = sorted({l.dxf.name for l in doc.layers})[:40]
    return {
        "kind": "dxf",
        "objects_detected": True,
        "verified": False,
        "note": "Inventaire brut des entités DXF (reconnaissance NON vérifiée). "
                "Confirmez les calques porteurs et l'échelle sur une cote connue avant tout usage.",
        "summary": {
            "entities_total": sum(counts.values()),
            "by_type": counts,
            "layers_count": len(doc.layers),
            "layers_sample": layers,
            "unit_to_m": unit_to_m,
        },
    }


def recognize(data: bytes, filename: str) -> dict:
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "").lower()
    if ext == "dxf":
        return _recognize_dxf(data)
    if ext == "pdf":
        return {"kind": "pdf", "objects_detected": False,
                "note": "PDF stocké pour référence. La reconnaissance d'objets vectoriels n'est "
                        "pas disponible sur PDF dans cette version — calez l'échelle sur une cote "
                        "connue et renseignez la géométrie via le questionnaire.", "summary": {}}
    if ext in ("png", "jpg", "jpeg", "webp"):
        return {"kind": "image", "objects_detected": False,
                "note": "Image stockée pour référence. Un agrandissement ou une photo ne constitue "
                        "pas une mesure fiable : renseignez les cotes depuis un relevé.", "summary": {}}
    if ext in ("dwg", "ifc"):
        return {"kind": ext, "objects_detected": False,
                "note": f"Format {ext.upper()} : connecteur non qualifié dans cette version. "
                        "Fichier stocké pour référence.", "summary": {}}
    return {"kind": ext or "bin", "objects_detected": False,
            "note": "Format non reconnu automatiquement. Fichier stocké.", "summary": {}}
