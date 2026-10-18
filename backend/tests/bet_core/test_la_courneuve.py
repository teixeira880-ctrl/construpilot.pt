"""Non-régression sur le cas réel La Courneuve (incident du 18/10/2026)."""
import copy
import json
from pathlib import Path

from engines.bet_core import checks, mep, model, structure, timber

CASE = Path(__file__).resolve().parents[2] / "engines" / "bet_core" / "cases" / "la_courneuve.json"


def _m(mutate=None):
    raw = json.loads(CASE.read_text(encoding="utf-8"))
    if mutate:
        mutate(raw)
    p = Path("/tmp/_case.json")
    p.write_text(json.dumps(raw), encoding="utf-8")
    return model.load(p)


def test_model_clean():
    assert not [a for a in checks.run_all(_m()) if a["level"] == checks.BLOCK]


def test_duplicate_garage_door_is_blocking():
    def dup(raw):
        raw["openings"].append(dict(raw["openings"][2], id="B-RDC-R9"))
    assert any(a["code"] == "GEO-04" for a in checks.run_all(_m(dup)))


def test_invented_level_is_blocking():
    def lvl(raw):
        raw["levels"].insert(3, {"id": "X", "name": "Faux niveau", "floor_top": 5.0, "slab_thickness": 0.25, "ceiling_height": 1.0, "use": "habitation"})
    assert any(a["code"] in ("GEO-10", "GEO-11") for a in checks.run_all(_m(lvl)))


def test_wall_in_stairwell_is_blocking():
    def wall(raw):
        raw["interior_walls"]["RDC"].append({"x0": 6.40, "y0": 4.80, "x1": 6.60, "y1": 6.90, "kind": "refend fantôme"})
    assert any(a["code"] == "GEO-30" for a in checks.run_all(_m(wall)))


def test_user_hypotheses_respected():
    m = _m()
    r = structure.compute(m)
    assert r["floors"]["system"] == "poutrelles_hourdis"
    assert r["masonry"]["material"] == "brique_porotherme_20"
    assert not checks.check_hypotheses(m, r)


def test_foundations_follow_g2():
    r = structure.compute(_m())
    for it in r["foundations"]["items"]:
        assert it["B"] >= 0.60 and it["ratio_ELS"] <= 0.90 and it["ratio_ELU"] <= 0.90


def test_all_trades_produced():
    m = _m()
    r = structure.compute(m)
    t = timber.compute(m, r["loads"])
    e = mep.electrical(m)
    p = mep.plumbing(m)
    assert t["panne_section"] and t["chevron_section"]
    assert e["totals"]["pc"] > 30 and len(e["rcds"]) == 4
    assert len(p["fixtures"]) >= 18 and p["relevage"]["needed"]
