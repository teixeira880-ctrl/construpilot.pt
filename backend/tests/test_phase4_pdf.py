"""Tests PDF dossier."""
from stair_engine import StairInput, compute_straight, ConcreteAnalysisInput, compute_concrete_analysis
from stair_engine.pdf_dossier import generate_dossier_pdf


def _sample_result():
    return compute_straight(StairInput(
        floor_height_mm=2800, available_length_mm=5000,
        available_width_mm=1500, stair_width_mm=900,
    ))


def test_pdf_without_concrete():
    r = _sample_result()
    pdf = generate_dossier_pdf(
        project_name="Test projet",
        stair_input={"floor_height_mm": 2800, "stair_width_mm": 900},
        stair_result=r.model_dump(mode="json"),
    )
    assert pdf[:4] == b"%PDF", "Magic bytes PDF manquants"
    assert len(pdf) > 3000
    assert len(pdf) < 500_000  # <500KB


def test_pdf_with_concrete():
    r = _sample_result()
    ca = compute_concrete_analysis(ConcreteAnalysisInput(stair_result=r, stair_type="straight"))
    pdf = generate_dossier_pdf(
        project_name="Test complet",
        stair_input={"floor_height_mm": 2800, "stair_width_mm": 900},
        stair_result=r.model_dump(mode="json"),
        concrete_analysis=ca.model_dump(mode="json"),
        author="BE Dupont",
    )
    assert pdf[:4] == b"%PDF"
    # Avec concrete, le PDF doit être significativement plus grand
    pdf_light = generate_dossier_pdf(
        project_name="Test", stair_input={"floor_height_mm": 2800, "stair_width_mm": 900},
        stair_result=r.model_dump(mode="json"),
    )
    assert len(pdf) > len(pdf_light)


def test_pdf_with_alerts_and_special_chars():
    r = _sample_result()
    pdf = generate_dossier_pdf(
        project_name="Projet École — Réf #42",
        stair_input={"floor_height_mm": 2800, "stair_width_mm": 900},
        stair_result=r.model_dump(mode="json"),
        author="Cabinet Béton Étude",
    )
    assert pdf[:4] == b"%PDF"
