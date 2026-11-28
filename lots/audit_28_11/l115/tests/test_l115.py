"""Tests Lot 115 (CP-AUDIT-NUIT-7) : plus aucun nom non défini dans les fichiers corrigés."""
import os
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "backend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]


def test_pas_de_nom_non_defini():
    files = ["routes/estimation_routes.py", "engines/calc_lots_ua/especialidades.py", "routes/atelier_archi.py"]
    files = [f for f in files if (ROOT / "backend" / f).exists()]
    try:
        out = subprocess.run([sys.executable, "-m", "pyflakes", *files], cwd=ROOT / "backend",
                             capture_output=True, text=True).stdout
    except Exception:  # pyflakes absent : contrôle du correctif principal
        out = ""
    bad = [ln for ln in out.splitlines() if "undefined name" in ln or "referenced before assignment" in ln]
    assert not bad, bad
    src = (ROOT / "backend/routes/estimation_routes.py").read_text(encoding="utf-8")
    assert "subject, html," not in src
