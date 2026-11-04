"""Lot 82 — synthèse de l'étude PC : délai adapté au dossier, message clair en cas de dépassement."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_synthesis_timeout_scales_with_pages():
    src = (ROOT / "engines" / "study_dossier_ai.py").read_text(encoding="utf-8")
    assert "timeout=min(600, 240 + 20 * len(analyses))" in src
    assert "payload), timeout=180)" not in src
    assert min(600, 240 + 20 * 11) == 460


def test_timeout_gets_clear_message():
    src = (ROOT / "engines" / "study_dossier_jobs.py").read_text(encoding="utf-8")
    assert "isinstance(exc, asyncio.TimeoutError)" in src
    import engines.study_dossier_jobs  # noqa: F401  (le module s'importe)
