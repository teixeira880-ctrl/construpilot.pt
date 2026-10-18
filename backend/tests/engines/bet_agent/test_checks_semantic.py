"""Testes dos checks semânticos."""
from __future__ import annotations

from engines.bet_agent.brief import parse_user_brief
from engines.bet_agent.checks.semantic import run_semantic_checks
from engines.bet_agent.models.building import (
    ExtractionMethod,
    FloorKind,
    OpeningKind,
    StructuralKind,
    WallKind,
)
from engines.bet_agent.models.summary import AnomalySeverity
from engines.bet_agent.testing import (
    mk_bbox,
    mk_building,
    mk_floor,
    mk_opening,
    mk_source,
    mk_stair,
    mk_structural,
    mk_wall,
)


def test_sem001_slab_type_user_imposed_triggers_anomaly_on_contradiction() -> None:
    """Utilizador impôs aligeirada; laje lida com thickness=100mm é incoerente."""
    ub = parse_user_brief({"materials": {"slab_type": "aligeirada_vigotas_abobadilhas"}})
    bm = mk_building(
        floors=[mk_floor()],
        structural_elements=[mk_structural(thickness_mm=100)],
    )
    anoms = run_semantic_checks(bm, ub)
    assert any(a.code == "SEM-001" and a.severity == AnomalySeverity.GRAVE for a in anoms)


def test_sem001_slab_type_user_imposed_respected_when_consistent() -> None:
    ub = parse_user_brief({"materials": {"slab_type": "aligeirada_vigotas_abobadilhas"}})
    bm = mk_building(
        floors=[mk_floor()],
        structural_elements=[mk_structural(thickness_mm=250)],
    )
    anoms = run_semantic_checks(bm, ub)
    assert not any(a.code == "SEM-001" for a in anoms)


def test_sem002_sotao_habitable_requires_criteria() -> None:
    """Sótão marcado habitável mas sem janelas nem escada => GRAVE."""
    ub = parse_user_brief({})
    bm = mk_building(
        floors=[mk_floor(fid="F-S", kind=FloorKind.SOTAO, height_clear_m=1.9, habitable=True)],
    )
    anoms = run_semantic_checks(bm, ub)
    assert any(a.code == "SEM-002" and a.severity == AnomalySeverity.GRAVE for a in anoms)


def test_sem002_sotao_habitable_satisfied_passes() -> None:
    ub = parse_user_brief({})
    sotao = mk_floor(fid="F-S", kind=FloorKind.SOTAO, height_clear_m=2.1, habitable=True)
    rc = mk_floor(fid="F-R0", kind=FloorKind.RC, height_clear_m=2.7)
    wall = mk_wall(wid="W-S-01", floor_id="F-S")
    janela = mk_opening(oid="O-S-01", wall_id="W-S-01", kind=OpeningKind.JANELA,
                        width_m=0.6, height_m=0.9)
    stair = mk_stair(sid="S-01", floor_from_id="F-R0", floor_to_id="F-S",
                     opening_length_m=3.6)
    bm = mk_building(floors=[rc, sotao], walls=[wall], openings=[janela], stairs=[stair])
    anoms = run_semantic_checks(bm, ub)
    assert not any(a.code == "SEM-002" for a in anoms)


def test_sem003_floor_vision_low_confidence_is_bloqueante() -> None:
    ub = parse_user_brief({})
    f_bad = mk_floor(
        fid="F-ghost", kind=FloorKind.PISO, level_m=5.0,
        confidence=0.4, method=ExtractionMethod.VISION,
    )
    bm = mk_building(floors=[f_bad])
    anoms = run_semantic_checks(bm, ub)
    assert any(a.code == "SEM-003" and a.severity == AnomalySeverity.BLOQUEANTE for a in anoms)


def test_sem003_floor_vector_text_always_accepted() -> None:
    ub = parse_user_brief({})
    f_ok = mk_floor(confidence=0.3, method=ExtractionMethod.VECTOR_TEXT)
    bm = mk_building(floors=[f_ok])
    anoms = run_semantic_checks(bm, ub)
    assert not any(a.code == "SEM-003" for a in anoms)


def test_sem005_notes_referencing_out_of_scope() -> None:
    ub = parse_user_brief({"notes": "Precisa também de verificação térmica REH e análise acústica."})
    bm = mk_building(floors=[mk_floor()])
    anoms = run_semantic_checks(bm, ub)
    assert any(a.code == "SEM-005" and a.severity == AnomalySeverity.AVISO for a in anoms)
