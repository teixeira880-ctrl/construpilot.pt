"""Lucarnes : géométrie, chevêtre justifié, présentes en plan de comble, en coupe et en charpente."""
from pathlib import Path

from engines.bet_core import mep, model, sheets, structure, timber

CASE = Path(__file__).parents[2] / "engines/bet_core/cases/la_courneuve.json"


def test_dormers_everywhere():
    m = model.load(CASE)
    r = structure.compute(m)
    tim = timber.compute(m, r["loads"])
    assert len(tim["dormers"]) == 4
    for d in tim["dormers"]:
        g = d["geometry"]
        assert 0 < g["de"] < g["dr"] < g["run"]
        assert d["chevetre_section"] and d["chevetre_section"]["ratio_M"] < 1
    shs = sheets.all_sheets(m, r, tim, mep.electrical(m), mep.plumbing(m))
    by = {s.code: s for s in shs}
    txt = lambda s: " ".join(str(it[3]) for it in s.items if it[0] == "text")
    top = next(s for s in shs if s.title.endswith(m.levels[-1].name))
    assert txt(top).count("lucarne") == 4                      # jouées dessinées sur le plan du comble
    sec = next(s for s in shs if s.title.startswith("Coupes"))
    assert "LUC" in txt(sec)                                   # la coupe A-A passe par les lucarnes
    assert all(f"LUC{i}" in txt(by["CH-01"]) for i in range(1, 5))
