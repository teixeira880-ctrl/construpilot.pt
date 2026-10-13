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
                "note": f'DXF ilegível automaticamente ({str(e)[:80]}). Ficheiro guardado; introdução manual da geometria necessária.', "summary": {}}
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
        "note": "Inventário bruto das entidades DXF (reconhecimento NÃO verificado). Confirme as camadas resistentes e a escala numa cota conhecida antes de qualquer uso.",
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
                "note": "PDF guardado para referência. O reconhecimento de objetos vetoriais não está disponível em PDF nesta versão — acerte a escala numa cota conhecida e preencha a geometria através do questionário.", "summary": {}}
    if ext in ("png", "jpg", "jpeg", "webp"):
        return {"kind": "image", "objects_detected": False,
                "note": "Imagem guardada para referência. Uma ampliação ou fotografia não constitui uma medição fiável: preencha as cotas a partir de um levantamento.", "summary": {}}
    if ext in ("dwg", "ifc"):
        return {"kind": ext, "objects_detected": False,
                "note": f'Formato {ext.upper()}: conector não qualificado nesta versão. Ficheiro guardado para referência.', "summary": {}}
    return {"kind": ext or "bin", "objects_detected": False,
            "note": "Formato não reconhecido automaticamente. Ficheiro guardado.", "summary": {}}
