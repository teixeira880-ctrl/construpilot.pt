"""Tests Lots 116/118/119 (audit de nuit) — correctifs posés."""
import os
import pathlib

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "frontend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_cotes_verdict_nd():
    src = (ROOT / "frontend/src/pages/CotesControl.jsx").read_text(encoding="utf-8")
    assert "nd:" in src and "VERDICT.nd)" in src


def test_aide_gras():
    assert "boldMd(" in (ROOT / "frontend/src/components/HelpChatbot.jsx").read_text(encoding="utf-8")
