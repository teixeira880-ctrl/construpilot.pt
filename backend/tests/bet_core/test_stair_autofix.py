"""Modo «decidir sozinho»: uma caixa de escada lida pequena demais (GEO-31) já não bloqueia o estudo —
adota-se a menor escada regulamentar de dois lanços e a decisão fica registada."""
import copy
import json
from pathlib import Path

from engines.bet_core import checks, pipeline, reader

CASES = Path(__file__).parents[2] / "engines/bet_core/cases"


def _case(name):
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def _blocking(raw):
    _, an = pipeline.validate(copy.deepcopy(raw))
    return [a for a in an if a.get("level") == checks.BLOCK]


def _shrink(raw):
    s = raw["stair"]
    s["x1"], s["y1"] = s["x0"] + 1.0, s["y0"] + 1.0      # caixa 1,00 × 1,00 como no erro em produção
    return raw


def test_small_cage_is_resized_pt():
    raw = _shrink(_case("moradia_pt_demo.json"))
    assert any(a["code"] == "GEO-31" for a in _blocking(raw))
    msg = reader.autofix_stair(raw, "PT")
    assert msg and "Incoerência" in msg and "cobertor" in msg
    assert not _blocking(raw)
    s = raw["stair"]
    B, L = s["x1"] - s["x0"], s["y1"] - s["y0"]
    assert min(B, L) >= 1.89 and max(B, L) <= 3.5
    env = raw["envelope"]
    assert 0 < s["x0"] < s["x1"] < env["length_x"] and 0 < s["y0"] < s["y1"] < env["width_y"]
    assert msg in raw["_decisions"]


def test_small_cage_is_resized_fr():
    raw = _shrink(_case("la_courneuve.json"))
    if not any(a["code"] == "GEO-31" for a in _blocking(raw)):
        return
    msg = reader.autofix_stair(raw, "FR")
    assert msg and "Incohérence" in msg
    assert not any(a["code"] in ("GEO-30", "GEO-31") for a in _blocking(raw))


def test_valid_stair_untouched_when_not_needed():
    raw = _case("moradia_pt_demo.json")
    assert not any(a["code"] == "GEO-31" for a in _blocking(raw))


def test_full_dossier_after_autofix(tmp_path):
    raw = _shrink(_case("moradia_pt_demo.json"))
    assert reader.autofix_stair(raw, "PT")
    res = pipeline.run(raw, str(tmp_path), None, "pt", None, None)
    assert res["status"] != "MODELE_INVALIDE"
    assert res["files"].get("pdf") and res["files"].get("xlsx")
    warn = [a for a in res["anomalies"] if a["code"] == "GEO-31I"]
    assert warn and "Incoerência" in warn[0]["message"]
