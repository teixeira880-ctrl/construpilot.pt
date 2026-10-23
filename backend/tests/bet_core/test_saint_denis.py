"""Maison isolée à faîtage parallèle à la longueur, refend porteur, sous-sol garage, combles aménageables (PC de Saint-Denis
traduit en portugais + G2 d'exemple) : l'étude thermique RE2020 est faite AVANT les plans et fixe l'épaisseur des murs ;
un relevé IA incomplet (nulls, comble fantôme, pays PT) est complété au lieu de bloquer."""
import asyncio
import copy
import json
from pathlib import Path

from engines.bet_core import pipeline, reader, structure, thermal, timber
from engines.bet_core import checks
import importlib.util as _ilu
import pytest as _pt
_NO_RE2020 = _pt.mark.skipif(_ilu.find_spec("engines.calc_lots.re2020") is None, reason="motor RE2020 só existe no .fr")
_NO_PLANSRC = _pt.mark.skipif(_ilu.find_spec("engines.plan_sources") is None, reason="módulo Plans (plan_sources) só existe no .fr")


CASES = Path(__file__).parents[2] / "engines/bet_core/cases"
SD = json.loads((CASES / "saint_denis.json").read_text(encoding="utf-8"))
TEXT = ("utilise ce PC et G2 pro comme exemple, sous-sol parpaing banché, à partir du rdc brique iso brique, charpente "
        "traditionnelle tuiles, combles aménageables, étude complète respectant la RE2020, indique-moi l'isolation, "
        "pompe à chaleur réversible, chauffage au sol")


def _raw():
    raw = copy.deepcopy(SD)
    raw["user_hypotheses"]["_text"] = TEXT
    return raw


def test_structure_refend_trusses_and_beam():
    m, an = pipeline.validate(_raw())
    assert m is not None and not [a for a in an if a["level"] == checks.BLOCK]
    r = structure.compute(m)
    assert m.ridge_along_x and m.trusses == [5.0, 10.0]
    assert len(m.bays) == 2 and m.span_y_calc <= 4.1                       # refend : 2 travées ≤ 4 m au lieu de 7,70 m
    assert all(s["system"] == "16+4" for s in r["floors"]["slabs"])         # plancher 20 cm du PC tenu
    assert r["floors"]["slabs"][-1]["attic"]                                # plancher des combles aménageables calculé
    assert any(i["side"] == "RF1" for i in r["foundations"]["items"])       # semelle sous refend
    bm = r["lintels"]["beams"][0]
    assert bm["headroom"] >= 1.90 and bm["posts"]                           # poutre du garage avec poteau entre les places
    tim = timber.compute(m, r["loads"])
    assert tim["panne_section"] and len(tim["trusses"]) == 2 and tim["run"] == 4.0


@_NO_RE2020
def test_thermal_first_sets_wall_thickness_and_passes_re2020(tmp_path):
    res = pipeline.run(_raw(), tmp_path, "22/10/2026", "fr")
    assert res["status"] != "MODELE_INVALIDE", res["anomalies"]
    th = res["thermal"]
    assert th["Bbio"] <= th["Bbio_max"] and th["Cep_nr"] <= th["Cep_nr_max"] and th["Cep"] <= th["Cep_max"]
    assert th["wall_total"] >= 0.30 and th["classe"] in "ABC"
    assert Path(res["files"]["re2020_pdf"]).exists()
    assert any(code.startswith("CH-01") for code in res["sheets"])


@_NO_RE2020
def test_thermal_respects_requested_insulation():
    raw = _raw()
    raw["user_hypotheses"]["_text"] = "doublage 10+140, PAC réversible, plancher chauffant"
    m, _ = pipeline.validate(raw)
    th = thermal.size(m)
    assert th["wall_insulation_mm"] == 140 and th["forced"] == 140


def test_incomplete_ai_reading_is_completed_not_blocked():
    """Reproduit l'échec de production (OpenAI) : épaisseurs et HSP à null, niveau « R2 » fantôme, pays PT."""
    raw = _raw()
    raw["project"]["country"] = "PT"
    raw["project"]["address"] = "21 rue Georges Bizet, Saint Denis"
    raw["envelope"]["wall_total_thickness"] = None
    raw["levels"][0]["slab_thickness"] = None
    for lv in raw["levels"]:
        lv["ceiling_height"] = None
    raw["levels"].append({"id": "R2", "name": "Sótão", "floor_top": None, "slab_thickness": None, "ceiling_height": None, "use": None})
    raw["openings"][1]["height"] = "1,20"
    m, an = pipeline.validate(raw)
    assert m is not None and not [a for a in an if a["level"] == checks.BLOCK], an
    assert [lv.id for lv in m.levels] == ["SS", "RDC", "R1"]
    assert [lv.hsp for lv in m.levels] == [2.2, 2.9, 2.8] and m.levels[0].slab == 0.2
    assert raw["project"]["country"] == "FR" and raw["roof"]["attic_floor"]
    assert any("Sótão" in d for d in raw["_decisions"])


def test_reader_retries_openings_only(monkeypatch):
    first = _raw()
    first["openings"] = []
    ops = {"openings": copy.deepcopy(SD["openings"])}
    calls = []

    async def llm(system, text, images=None, model=None, max_tokens=0, **kw):
        calls.append(text)
        return json.dumps(ops) if "UNIQUEMENT les baies" in text else json.dumps(first)
    from tests.bet_core.test_decide_alone import _pdf
    pdf = _pdf(["PLANTA DO R/C", "CORTE", "ALÇADO DA RUA"])
    res = asyncio.run(reader.read_building([("PC.pdf", pdf)], TEXT, "FR", llm=llm, decide_alone=True))
    assert res["ok"], res["anomalies"]
    assert len(res["model"]["openings"]) == len(SD["openings"])
    assert any("UNIQUEMENT les baies" in t for t in calls)
