"""O catálogo do modo demo offline (frontend/src/fixtures/demo/missions_catalog.json) acompanha o motor."""
import json
from pathlib import Path

from engines.missions import OPTIONS

FX = Path(__file__).resolve().parents[2] / "frontend" / "src" / "fixtures" / "demo" / "missions_catalog.json"


def test_catalogo_demo_igual_ao_motor():
    opts = json.loads(FX.read_text("utf-8"))["options"]
    assert [o["key"] for o in opts] == list(OPTIONS)
    for o in opts:
        assert o["name"] == OPTIONS[o["key"]]["name"]
