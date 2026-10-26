"""Lote 26 : patios, porches e terraços dentro da implantação são exteriores (sem piso radiante, VMC nem tomadas)."""
import json
from pathlib import Path

from engines.bet_core import hvac, mep, model

CASE = Path(__file__).resolve().parents[2] / "engines" / "bet_core" / "cases" / "la_courneuve.json"


def test_patio_excluido_das_redes():
    raw = json.loads(CASE.read_text(encoding="utf-8"))
    lid = raw["levels"][1]["id"]
    r0 = raw["rooms"][lid][0]
    raw["rooms"][lid].append({"name": "Patio", "type": "patio", "x0": r0["x0"], "y0": r0["y0"], "x1": r0["x1"], "y1": r0["y1"]})
    m = model.from_dict(raw)
    assert all(r["type"] != "patio" for r in m.rooms(lid)) and [r["name"] for r in m.exterior_spaces(lid)] == ["Patio"]
    hv = hvac.hvac(m, mep.plumbing(m)["stacks"])
    assert not any(x["room"] == "Patio" for x in hv["loss"]["rooms"])
    assert not any(c.get("room") == "Patio" for c in mep.electrical(m)["circuits"] if isinstance(c, dict))
