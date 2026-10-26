"""Lote 25 : vigas que crescem muito (0,30 → 0,85) não podem consumir todas as iterações e deixar os pilares por dimensionar."""
import json
from pathlib import Path

from engines.bet_frame import calc, model
from engines.bet_frame.lang import use_lang

CASE = json.loads((Path(__file__).resolve().parents[2] / "engines" / "bet_frame" / "cases" / "immeuble_demo_pt.json").read_text(encoding="utf-8"))


def _run(monkeypatch=None, it=None):
    raw = json.loads(json.dumps(CASE))
    raw["structure"]["beam"] = [0.30, 0.30]
    raw["structure"]["column"] = [0.25, 0.25]
    if it:
        monkeypatch.setattr(calc, "MAX_ITER", it)
    with use_lang("pt"):
        return calc.compute(model.from_dict(raw))


def test_pilares_dimensionados_mesmo_com_vigas_a_crescer():
    r = _run()
    assert not [i for i in r["issues"] if i["code"] in ("CALC-ITER", "COL-NOK")]
    assert all(all(s.get("ok") for s in c["segs"]) for c in r["columns"])
    assert max(c["b"] for c in r["columns"]) >= 0.45
