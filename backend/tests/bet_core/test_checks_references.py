"""Item A — contrôle de complétude/cohérence des renvois (checks.check_references).

Un relevé incomplet ou incohérent doit produire une anomalie REF-* bloquante CLAIRE
(pas un CALC-00 ni un plantage muet) et court-circuiter les autres contrôles.
"""
import copy
import json
from pathlib import Path

from engines.bet_core import checks
from engines.bet_core import model as M

_CASE = Path(__file__).resolve().parent.parent.parent / "engines" / "bet_core" / "cases" / "moradia_pt_demo.json"
_RAW = json.loads(_CASE.read_text(encoding="utf-8"))


def _blocks(raw):
    return [a for a in checks.run_all(M.from_dict(raw)) if a["level"] == checks.BLOCK]


def test_valid_model_has_no_reference_block():
    assert not any(a["code"].startswith("REF-") for a in _blocks(copy.deepcopy(_RAW)))


def test_missing_geotech_is_ref_block_not_calc():
    raw = copy.deepcopy(_RAW)
    raw.pop("geotech", None)
    codes = {a["code"] for a in _blocks(raw)}
    assert "REF-GEOTECH" in codes
    assert not any(c.startswith("CALC") for c in codes)


def test_missing_stair_is_ref_block():
    raw = copy.deepcopy(_RAW)
    raw["stair"] = None
    assert "REF-STAIR" in {a["code"] for a in _blocks(raw)}


def test_reference_to_deleted_level_is_ref_level():
    raw = copy.deepcopy(_RAW)
    raw["levels"] = [lv for lv in raw["levels"] if lv["id"] != "A1"]
    blocks = _blocks(raw)
    assert any(a["code"] == "REF-LEVEL" for a in blocks)
    # relevé incomplet : on ne lance pas les autres contrôles (court-circuit)
    assert {a["code"] for a in blocks} <= {"REF-LEVEL", "REF-ENVELOPE", "REF-LEVELS", "REF-ROOF",
                                           "REF-OPENINGS", "REF-STAIR", "REF-ROOMS", "REF-INTERIOR_WALLS", "REF-GEOTECH"}
