"""Tests Lot 117 (CP-AUDIT-NUIT-9) : numéro repris après import."""
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "backend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def test_numero_apres_import():
    from routes.documents import _seq_from_number as f
    assert f("F202600106") == 106
    assert f("DEV-2026-0042") == 42
    assert f("D-123") == 123
    assert f("") == 0
