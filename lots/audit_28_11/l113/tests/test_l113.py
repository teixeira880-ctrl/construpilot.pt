"""Tests Lot 113 (CP-AUDIT-NUIT-5) : les contours parasites n'entrent pas dans le moteur MEP."""
import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("CP_ROOT", "/app"))
if not (ROOT / "backend").exists():
    ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))


def test_contours_parasites_ignores():
    from engines.mep import adapter
    ppm = 100.0
    plan = {"calibrations": {"0": {"pixels_per_meter": ppm}}, "rooms": [
        {"room_id": "r1", "page_index": 0, "name": "Séjour", "points": [[0, 0], [480, 0], [480, 760], [0, 760]]},
        {"room_id": "r2", "page_index": 0, "name": "Vide de mur", "points": [[480, 0], [490, 0], [490, 760], [480, 760]]},
        {"room_id": "r3", "page_index": 0, "name": "Lettre", "points": [[0, 0], [15, 0], [15, 20], [0, 20]]},
    ]}
    model = adapter.from_takeoff(plan)
    rooms = [r for lv in model["levels"] for r in lv["rooms"]]
    assert [r["id"] for r in rooms] == ["r1"]
