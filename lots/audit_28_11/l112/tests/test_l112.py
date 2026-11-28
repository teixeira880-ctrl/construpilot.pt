"""Tests Lot 112 (CP-AUDIT-NUIT-4) — vérifie que les correctifs sont posés."""
import os
import pathlib

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "frontend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_sondages_allégés():
    assert "document.hidden" in (ROOT / "frontend/src/components/AgentsRunning.jsx").read_text(encoding="utf-8")
    assert "document.hidden" in (ROOT / "frontend/src/components/StudyRunning.jsx").read_text(encoding="utf-8")


def test_projet_singulier():
    assert '"projet", "projets"' in (ROOT / "frontend/src/pages/Dashboard.jsx").read_text(encoding="utf-8")
