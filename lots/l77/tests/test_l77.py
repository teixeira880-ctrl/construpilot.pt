"""Lot 77 — titres de plans de niveau reconnus."""
from engines.plan_page_context import page_context


def test_storey_plan_titles():
    for t, lvl in (("PLAN DU 1er ETAGE - futur\nPLAN DE R+1 projet\n1:50\n", 1),
                   ("PLAN DU REZ-DE-CHAUSSEE - existant\n1:50\n", 0),
                   ("PLAN DE R+2\n1:100\n", 2),
                   ("PLAN DU SOUS-SOL\n1:50\n", -1)):
        ctx = page_context(t)
        assert ctx["view_kind"] == "floor_plan", t
        assert ctx["level_index"] == lvl, t


def test_site_and_roof_plans_not_storey_plans():
    for t in ("PLAN DE MASSE projet\n1:200\n", "PLAN DE SITUATION\n1:5000\n", "PLAN DE TOITURE - futur\n1:50\n"):
        assert page_context(t)["view_kind"] != "floor_plan", t
