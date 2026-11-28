"""Tests Lot 111 (CP-AUDIT-NUIT-3)."""
import io
import os
import pathlib
import sys

import openpyxl

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "backend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def test_dpgf_colonne_u():
    from engines.dpgf_engine import parse_workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    for r in (["N°", "Désignation", "U", "Qté", "PU HT", "Total HT"], ["05", "LOT 05 - PLÂTRERIE", "", "", "", ""],
              ["05.1", "Cloison 72/48 BA13", "m²", 120, "", ""], ["05.2", "Bande de calfeutrement", "ml", 40, "", ""]):
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    rows = parse_workbook(buf.getvalue())["rows"]
    assert [(x["unit"], x["qty"]) for x in rows] == [("m²", 120.0), ("ml", 40.0)]


def test_auth_reessaie():
    src = (ROOT / "frontend/src/context/AuthContext.jsx").read_text(encoding="utf-8")
    assert "checkAuth(attempt + 1)" in src
