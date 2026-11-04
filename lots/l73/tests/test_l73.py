"""Lot 73 — titres d'élévation reconnus comme façades."""
from engines.plan_page_context import page_context


def test_elevation_titles():
    for t in ("-FORET\nELEVATION NORD\n 0.00\n+ 5.75\nELEVATION SUD\n", "ÉLÉVATION OUEST\n+6.00\n",
              "FAÇADE PRINCIPALE\n1:100\n", "Façade sur jardin\n", "ALÇADO FRONTAL\n1:100\n"):
        ctx = page_context(t)
        assert ctx["view_kind"] == "elevation", t
        assert ctx["interior_analysis_blocked"] is True


def test_floor_plan_with_elevation_word_in_note_unchanged():
    ctx = page_context("PLAN RDC\nNote : voir élévation des menuiseries\n1:50\n")
    assert ctx["view_kind"] == "floor_plan"
