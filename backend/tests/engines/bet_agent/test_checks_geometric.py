"""Testes dos checks determinísticos geométricos."""
from __future__ import annotations

from engines.bet_agent.checks.geometric import run_geometric_checks
from engines.bet_agent.models.building import BuildingModel, FloorKind, OpeningKind
from engines.bet_agent.models.summary import AnomalySeverity
from engines.bet_agent.testing import (
    mk_bbox,
    mk_building,
    mk_floor,
    mk_opening,
    mk_slab_opening,
    mk_stair,
    mk_wall,
)


def test_clean_model_has_zero_anomalies() -> None:
    bm = mk_building(
        floors=[mk_floor()],
        walls=[mk_wall()],
    )
    assert run_geometric_checks(bm) == []


def test_geo001_catches_wall_zero_length() -> None:
    # Pydantic rejeita length=0 na criação directa (gt=0). Para teste do check,
    # construímos via model_construct para contornar validações e simular um
    # bug a jusante do reader.
    bm = BuildingModel(project_id="t", floors=[mk_floor()])
    bad_wall = mk_wall(length_m=0.5)
    bad_wall.length_m = 0  # ignora validator após construção
    bm.walls.append(bad_wall)
    anoms = run_geometric_checks(bm)
    assert any(a.code == "GEO-001" and a.severity == AnomalySeverity.GRAVE for a in anoms)


def test_geo002_catches_duplicate_opening_in_same_wall() -> None:
    wall = mk_wall(wid="W-garagem", length_m=4.0, bbox=mk_bbox(0, 0, 400, 100))
    o1 = mk_opening(oid="O-portao-A", wall_id="W-garagem", kind=OpeningKind.PORTAO_GARAGEM,
                    width_m=2.5, height_m=2.2, bbox=mk_bbox(50, 10, 150, 90))
    o2 = mk_opening(oid="O-portao-B", wall_id="W-garagem", kind=OpeningKind.PORTAO_GARAGEM,
                    width_m=2.5, height_m=2.2, bbox=mk_bbox(55, 10, 155, 90))
    bm = mk_building(floors=[mk_floor()], walls=[wall], openings=[o1, o2])
    anoms = run_geometric_checks(bm)
    assert any(a.code == "GEO-002" for a in anoms)


def test_geo003_catches_implausible_floor_height() -> None:
    bm = mk_building(floors=[
        mk_floor(fid="F-cave", kind=FloorKind.CAVE, height_clear_m=1.80),  # fora 2.20-3.00
    ])
    anoms = run_geometric_checks(bm)
    assert any(a.code == "GEO-003" and a.severity == AnomalySeverity.GRAVE for a in anoms)


def test_geo003_accepts_normal_floor_height() -> None:
    bm = mk_building(floors=[mk_floor(height_clear_m=2.7)])
    anoms = run_geometric_checks(bm)
    assert not any(a.code == "GEO-003" for a in anoms)


def test_geo004_catches_stair_too_long_for_opening() -> None:
    # delta_h = 3.00 m, abertura só tem 1.20 m. Impossível.
    bm = mk_building(
        floors=[
            mk_floor(fid="F-R0", level_m=0.0, height_clear_m=2.7),
            mk_floor(fid="F-R1", level_m=3.0, height_clear_m=2.7),
        ],
        stairs=[mk_stair(sid="S-bad", floor_from_id="F-R0", floor_to_id="F-R1",
                         opening_length_m=1.2, opening_width_m=1.0)],
    )
    anoms = run_geometric_checks(bm)
    assert any(a.code == "GEO-004" and a.severity == AnomalySeverity.BLOQUEANTE for a in anoms)


def test_geo004_accepts_well_dimensioned_stair() -> None:
    bm = mk_building(
        floors=[
            mk_floor(fid="F-R0", level_m=0.0),
            mk_floor(fid="F-R1", level_m=2.9),
        ],
        stairs=[mk_stair(opening_length_m=4.5, opening_width_m=1.2)],
    )
    anoms = run_geometric_checks(bm)
    # 16 espelhos de 2.9/16=0.18, tread=0.63-0.36=0.27, length=15*0.27=4.05 ≤ 4.5
    assert not any(a.code == "GEO-004" for a in anoms)


def test_geo006_catches_wall_fully_inside_slab_opening() -> None:
    wall_bbox = mk_bbox(50, 50, 100, 100)
    opening_bbox = mk_bbox(0, 0, 200, 200)
    bm = mk_building(
        floors=[mk_floor()],
        walls=[mk_wall(wid="W-ghost", bbox=wall_bbox)],
        slab_openings=[mk_slab_opening(bbox=opening_bbox)],
    )
    anoms = run_geometric_checks(bm)
    assert any(a.code == "GEO-006" for a in anoms)
