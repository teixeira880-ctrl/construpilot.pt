"""Moradia de um só piso (sem escada): o estudo BET vai sempre até ao fim (laje de cobertura = nível técnico COB)."""
import copy
import json
import tempfile
from pathlib import Path

import pytest


def _plain_pied():
    raw = json.loads((Path(__file__).resolve().parents[2] / "engines/bet_core/cases/moradia_pt_demo.json").read_text())
    lv = raw["levels"][0]
    raw["levels"] = [lv]
    raw["openings"] = [o for o in raw["openings"] if o.get("level") == lv["id"]]
    for k in ("rooms", "interior_walls"):
        raw[k] = {kk: v for kk, v in raw[k].items() if kk == lv["id"]}
    raw["roof"] = {"type": "terrasse", "eaves_level": 3.0, "ridge_level": 3.0}
    return raw


@pytest.mark.parametrize("stair", [None, "quart tournant", [], {"type": "x", "flights": [{"from": "RC", "to": "COB"}]}])
def test_single_storey_house_study_completes(stair):
    from engines.bet_core import pipeline
    raw = _plain_pied()
    if stair is None:
        raw.pop("stair", None)
    else:
        raw["stair"] = copy.deepcopy(stair)
    r = pipeline.run(raw, tempfile.mkdtemp(), None, "pt", None, None)
    assert r["status"].startswith("PRÊT"), r.get("anomalies")
    assert all(r["files"].get(k) for k in ("pdf", "plans_pdf", "xlsx", "re2020_pdf"))
