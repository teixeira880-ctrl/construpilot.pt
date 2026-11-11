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


# ---------------------------------------------------------------- estudo sempre até ao fim
import asyncio
import tempfile

import pytest


@pytest.mark.parametrize("case", ["moradia_pt_demo.json", "la_courneuve.json", "saint_denis.json"])
def test_empty_flights_and_missing_cage_walls_complete(case):
    raw = _case(case)
    raw["stair"]["flights"] = []
    raw["stair"].pop("cage_walls", None)
    m, an = pipeline.validate(raw)
    assert m is not None and not [a for a in an if a["level"] == checks.BLOCK]
    assert raw["stair"]["flights"] and len(raw["stair"]["cage_walls"]) == 2
    assert pipeline.dry_run(m) is None                    # antes: IndexError structure.py:787


def test_missing_stair_is_placed_without_wall_in_well():
    raw = _case("la_courneuve.json")
    raw.pop("stair")
    msg = reader.autofix_stair(raw, "FR")
    assert msg and "non relevé" in msg
    assert not _blocking(raw)


def test_force_turns_incoherence_into_warning(tmp_path):
    raw = _case("saint_denis.json")
    raw.pop("stair")
    reader.autofix_stair(raw, "FR")
    _, an = pipeline.validate(copy.deepcopy(raw))
    assert pipeline.forceable(an)
    raw["_force"] = {"lang": "fr"}
    res = pipeline.run(raw, str(tmp_path), None, "fr", None, None)
    assert res["status"] != "MODELE_INVALIDE" and res["files"].get("xlsx")
    assert any(a["code"].endswith("F") and "Incohérence" in a["message"] for a in res["anomalies"])


def test_calc_errors_are_never_forced():
    assert not pipeline.forceable([{"code": "CALC-00", "level": checks.BLOCK, "message": "x"}])


def test_price_overrides_and_origin_warning(tmp_path):
    raw = _case("moradia_pt_demo.json")
    raw["_price_overrides"] = {"escalier": {"pu": 4321.0, "src": "company_library", "ref": "Escada betão"},
                               "pc": {"pu": 33.0, "src": "market_web", "ref": "leroymerlin.pt"}}
    res = pipeline.run(raw, str(tmp_path), None, "pt", None, None)
    assert res["status"] != "MODELE_INVALIDE"
    prix = [a for a in res["anomalies"] if a["code"] == "PRIX-01"]
    assert prix and "biblioteca" in prix[0]["message"] and "online" in prix[0]["message"]


def test_resolver_library_then_market_then_reference(monkeypatch):
    from engines.bet_core import price_resolver

    async def lib(db, uid, lines):
        return {"escalier": {"pu": 3000.0, "src": "company_library", "ref": "Escada"}}

    async def market(lines, country, region=""):
        assert all(l["key"] != "escalier" for l in lines)  # só o que falta na biblioteca vai à pesquisa online
        return {"pc": {"pu": 70.0, "src": "market_web", "ref": "web"}}
    monkeypatch.setattr(price_resolver, "_library", lib)
    monkeypatch.setattr(price_resolver, "_market", market)
    raw = _case("moradia_pt_demo.json")
    s = asyncio.run(price_resolver.resolve(raw, None, "u1", "PT"))
    assert s["library"] == 1 and s["market_web"] == 1 and s["reference"] > 10
    assert raw["_price_overrides"]["escalier"]["pu"] == 3000.0


def test_resolver_never_blocks_when_sources_fail(monkeypatch):
    from engines.bet_core import price_resolver

    async def boom(*a, **k):
        raise RuntimeError("offline")
    monkeypatch.setattr(price_resolver, "_library", boom)
    monkeypatch.setattr(price_resolver, "_market", boom)
    raw = _case("moradia_pt_demo.json")
    s = asyncio.run(price_resolver.resolve(raw, None, "u1", "PT"))
    assert s["library"] == 0 and s["market_web"] == 0 and raw["_price_overrides"] == {}
