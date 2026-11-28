"""Tests Lot 114 : atelierId transmis à BimPlanViewer."""
import os
import pathlib

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "frontend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_bimviewer_atelier_prop():
    src = (ROOT / "frontend/src/pages/BimViewer.jsx").read_text(encoding="utf-8")
    assert "function BimPlanViewer({ planId, atelierId," in src and "atelierId={atelierId}" in src
