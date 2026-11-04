"""Lot 56 — niveaux et type de vue lus sur les vrais PDF clients (FR + PT)."""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from engines.plan_page_context import level_candidates, page_context, scale_denominators  # noqa: E402


def _lv(text):
    return [x["level_index"] for x in level_candidates(text)]


def test_scale_then_etage_is_not_level_50():
    assert _lv("validées par des études\n1 : 50\nEtage 1\nSUR MESURE") == [1]
    assert _lv("Echelle 1/50 2e étage") == [2]
    assert _lv("PLAN DU 3ème étage") == [3]


def test_coffrage_plan_with_section_marker_is_structural_and_title_level_wins():
    text = ("Coupe 12\nP-R+4 12\nle sous-sol est à considérer comme inondable\nAccès combles\n"
            "Plan coffrage PH R+4\nLOT P4\n1/50\n")
    ctx = page_context(text)
    assert ctx["view_kind"] == "structural_plan"
    assert ctx["level_index"] == 4
    assert ctx["detected_scale_denominator"] == 50


def test_real_section_title_still_detected():
    assert page_context("COUPE AA\n1/100\n")["view_kind"] == "section"
    assert page_context("COUPE 1-1\n1/100\n")["view_kind"] == "section"


def test_portuguese_plans():
    assert page_context("CORTE AA\nEsc. 1/100\n")["view_kind"] == "section"
    assert page_context("ALÇADO NORTE\n1:100\n")["view_kind"] == "elevation"
    ctx = page_context("PLANTA DO PISO 1\nEscala 1:100\ncave para arrumos\n")
    assert ctx["view_kind"] == "floor_plan" and ctx["level_index"] == 1
    assert page_context("PLANTA DE COFRAGEM\n1/50\n")["view_kind"] == "structural_plan"
    assert _lv("Planta R/C") == [0]
    assert _lv("Planta do 2.º andar") == [2]
    assert _lv("Planta do sótão") == [99]


def test_no_false_scale():
    assert scale_denominators("pente 1/50 Echelle 1/100") == [100]
