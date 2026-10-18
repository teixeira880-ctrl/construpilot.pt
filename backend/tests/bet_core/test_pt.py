"""Profil Portugal : dossier complet en PT-PT, normas portuguesas, ação sísmica (NP EN 1998-1)."""
import json
import re
from pathlib import Path

import pymupdf
import pytest

from engines.bet_core import checks, i18n, model, pipeline, profiles, structure

CASES = Path(__file__).resolve().parents[2] / "engines" / "bet_core" / "cases"
FR_WORDS = {"les", "des", "avec", "pour", "dans", "sous", "semelle", "semelles", "plancher", "planchers", "linteau", "linteaux",
            "poteau", "chaînage", "chaînages", "façade", "étage", "prises", "éclairage", "charpente", "pannes", "chevrons", "faîtage",
            "devis", "béton", "acier", "voile", "voiles", "dallage", "escalier", "trémie", "cloisons", "toiture", "réactions", "cotées"}


def _raw(name):
    return json.loads((CASES / name).read_text(encoding="utf-8"))


def test_profiles():
    fr, pt = profiles.profile("FR"), profiles.profile("PT")
    assert fr["vat"] == 0.20 and pt["vat"] == 0.23
    assert pt["steel"] == "A500NR" and "RTIEBT" in pt["electrical"] and "23/95" in pt["plumbing"]
    assert profiles.price("PT", "semelle", 430.0) < 430.0


def test_tr_fr_is_identity_and_pt_converts_notation():
    s = "Chaînage horizontal 20×30 4HA10 + cadres HA6 e=20 en tête des murs sous chaque plancher."
    assert i18n.tr(s, "fr") == s
    out = i18n.tr(s, "pt")
    assert "4Ø10" in out and "Ø6//0,20" in out and "Cinta" in out
    assert "B500B" not in i18n.tr("acier B500B", "pt")


def test_pt_demo_model_clean_and_seismic():
    m = model.from_dict(_raw("moradia_pt_demo.json"))
    assert not [a for a in checks.run_all(m) if a["level"] == checks.BLOCK]
    r = structure.compute(m)
    sz = r["seismic"]
    assert sz["Fb_kN"] > 0 and 0.1 < sz["T1"] < 0.4 and sz["ok"]
    assert {a["type"] for a in sz["actions"]} == {1, 2}
    assert all(f["excentric"] is False for f in r["foundations"]["items"])   # moradia isolada : sapatas centradas
    assert not r["basement"]["walls"]


def test_fr_case_has_no_seismic_block():
    m = model.from_dict(_raw("la_courneuve.json"))
    assert "seismic" not in structure.compute(m)


def test_pt_dossier_fully_portuguese(tmp_path):
    res = pipeline.run(_raw("moradia_pt_demo.json"), tmp_path, lang="pt", date="18/10/2026")
    assert res["blocking"] == 0 and res["lang"] == "pt"
    txt = "\n".join(p.get_text() for p in pymupdf.open(res["files"]["pdf"]))
    words = {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]+", txt)}
    assert not (words & FR_WORDS), sorted(words & FR_WORDS)
    for k in ("NP EN 1998-1", "A500NR", "RTIEBT", "23/95", "Ação sísmica", "IVA 23 %", "Sapata", "Laje"):
        assert k in txt, k
    codes = [s.split()[0] for s in res["sheets"]]
    assert "GO-06a" in codes and "GO-06b" in codes      # 4 alçados com vãos → 2 folhas
    assert res["devis_ttc"] == pytest.approx(res["devis_ht"] * 1.23, rel=1e-6)
