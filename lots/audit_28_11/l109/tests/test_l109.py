"""Tests Lot 109 (CP-AUDIT-NUIT) — à lancer après apply_l109.py : python3 -m pytest -q lots/l109/tests/test_l109.py"""
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "backend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from stair_engine import StairInput, compute_straight  # noqa: E402


def _stair(h, length):
    return compute_straight(StairInput(floor_height_mm=h, available_length_mm=length, available_width_mm=1000,
                                       stair_width_mm=900, slab_thickness_mm=200, tread_thickness_mm=30,
                                       has_risers=True, direction="right"))


def test_escalier_ideal_inchange():
    r = _stair(2800, 4500)
    assert (r.num_steps, round(r.riser_height_mm, 1), r.tread_depth_mm) == (16, 175.0, 280.0)
    assert not any(a.code == "COMPACT_CONFIG" for a in r.alerts)


def test_escalier_compact_dans_le_reculement():
    r = _stair(2800, 3500)
    assert r.is_buildable is True
    assert r.stair_run_mm <= 3500
    assert r.riser_height_mm <= 195 and r.tread_depth_mm >= 220
    assert 580 <= r.blondel_value_mm <= 660 and r.slope_deg <= 40
    assert any(a.code == "COMPACT_CONFIG" for a in r.alerts)


def test_escalier_vraiment_impossible_reste_refuse():
    r = _stair(2700, 3000)   # pente > 40° quelle que soit la découpe
    assert r.is_buildable is False
    assert any(a.code == "STAIR_RUN_TOO_LONG" for a in r.alerts)


def test_fichiers_patches():
    txt = (ROOT / "backend/routes/plans_crud.py").read_text(encoding="utf-8")
    assert '"pages.vectors": 0' in txt
    txt = (ROOT / "backend/routes/plans_analysis.py").read_text(encoding="utf-8")
    assert "filtered_slivers" in txt
    bim = (ROOT / "frontend/src/pages/BimViewer.jsx").read_text(encoding="utf-8")
    assert "const atelierId" in bim
    assert "disabled={loadingConversation}" not in (ROOT / "frontend/src/pages/Assistant.jsx").read_text(encoding="utf-8")
    assert "persist: false" in (ROOT / "frontend/src/pages/LandingPortugal.jsx").read_text(encoding="utf-8")
