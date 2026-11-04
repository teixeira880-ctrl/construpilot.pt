"""Lot 72 — niveaux : cote décimale ≠ numéro d'étage ; « Étage » seul en titre = R+1 (maison R+1)."""
from engines.plan_page_context import level_candidates, page_context

COUPE = ("COUPE A-A (y = 5,85)\n-2.40  Sous-sol\n±0.00  Rez-de-chaussée\n+3.10  Étage\n"
         "+6.10  égout / plancher combles\nConstruction d'une maison individuelle R+1 sur sous-sol\n1:100\n")
ETAGE = ("ÉTAGE — niveau fini +3,10\nPlan d'exécution gros œuvre — Étage\n"
         "Construction d'une maison individuelle R+1 sur sous-sol, combles aménageables\n1:75\n")


def test_decimal_elevation_is_not_a_storey():
    labels = [x["level_label"] for x in level_candidates(COUPE)]
    assert "R+10" not in labels and "R+1" in labels


def test_real_storeys_still_read():
    assert [x["level_index"] for x in level_candidates("Plan du 2e étage")] == [2]
    assert [x["level_index"] for x in level_candidates("PLAN R+4")] == [4]
    assert 3 in [x["level_index"] for x in level_candidates("3ème étage")]


def test_bare_etage_title_is_r1_in_r1_house():
    ctx = page_context(ETAGE)
    assert ctx["level_label"] == "R+1"


def test_bare_etage_title_not_forced_when_taller_building():
    ctx = page_context("Plan d'exécution — Étage\nImmeuble R+4\n1:50\n")
    assert ctx["level_label"] != "R+1"
