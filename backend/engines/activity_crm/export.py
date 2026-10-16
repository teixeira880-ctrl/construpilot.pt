"""Exportação CSV / XLSX para o CRM lite."""
from __future__ import annotations

import csv
import io
from typing import Iterable


CSV_COLUMNS = [
    "created_at", "kind", "state", "user_email", "user_name", "user_phone",
    "summary", "source_url", "assigned_to", "is_fr_project",
    "attachments_count", "notes_count",
]


def _row(doc: dict) -> dict:
    return {
        "created_at": doc.get("created_at", ""),
        "kind": doc.get("kind", ""),
        "state": doc.get("state", ""),
        "user_email": doc.get("user_email", ""),
        "user_name": doc.get("user_name", ""),
        "user_phone": doc.get("user_phone", "") or "",
        "summary": (doc.get("summary", "") or "").replace("\n", " ").replace("\r", " "),
        "source_url": doc.get("source_url", "") or "",
        "assigned_to": doc.get("assigned_to", "") or "",
        "is_fr_project": "sim" if doc.get("is_fr_project") else "não",
        "attachments_count": len(doc.get("attachments") or []),
        "notes_count": len(doc.get("internal_notes") or []),
    }


def to_csv(docs: Iterable[dict]) -> bytes:
    """Exporta para CSV UTF-8 BOM (compatível com Excel europeu)."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=CSV_COLUMNS, delimiter=";",
                            quoting=csv.QUOTE_MINIMAL)
    writer.writeheader()
    for d in docs:
        writer.writerow(_row(d))
    # BOM para Excel-PT reconhecer UTF-8
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def to_xlsx(docs: Iterable[dict]) -> bytes:
    """Exporta para XLSX via openpyxl (requerido no requirements.txt)."""
    try:
        from openpyxl import Workbook
    except ImportError as exc:
        raise RuntimeError("openpyxl não disponível no servidor") from exc
    wb = Workbook()
    ws = wb.active
    ws.title = "Pedidos"
    ws.append(CSV_COLUMNS)
    for d in docs:
        row = _row(d)
        ws.append([row[c] for c in CSV_COLUMNS])
    # Larguras razoáveis
    for col, width in zip("ABCDEFGHIJKL", [22, 14, 14, 32, 26, 18, 60, 32, 24, 10, 8, 8]):
        ws.column_dimensions[col].width = width
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
