"""Validate real DXF output with ezdxf, without changing dimensions or units."""
import hashlib
import tempfile
from collections import Counter
from pathlib import Path

import ezdxf

from engines.autodesk_client import MAX_BYTES, AutodeskError


def inspect_dxf(data):
    if not data or len(data) > MAX_BYTES or b"\x00" in data[:4096] or b"SECTION" not in data[:4096]:
        raise AutodeskError("invalid_dxf", "Autodesk n'a pas produit de DXF texte reconnu.")
    try:
        with tempfile.TemporaryDirectory(prefix="cp-aps-validate-") as folder:
            path = Path(folder) / "output.dxf"
            path.write_bytes(data)
            doc = ezdxf.readfile(path)
            audit = doc.audit()
            if audit.has_errors:
                raise ValueError("DXF audit error")
            entities = Counter(entity.dxftype() for entity in doc.modelspace())
            return {"format_version": doc.dxfversion, "units_code": int(doc.header.get("$INSUNITS", 0)),
                    "entity_count": sum(entities.values()), "entity_types": dict(entities),
                    "layer_count": len(doc.layers), "output_sha256": hashlib.sha256(data).hexdigest(),
                    "output_size_bytes": len(data)}
    except Exception:  # noqa: BLE001 - untrusted CAD parser errors must not expose file contents.
        raise AutodeskError("invalid_dxf", "Le DXF Autodesk ne passe pas la validation géométrique.") from None