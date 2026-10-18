"""Testes para checks GEO-005 (áreas vs quadro) e GEO-007 (cadeia de cotas)."""
from __future__ import annotations

from engines.bet_agent.checks.geometric import (
    check_dimension_chain,
    check_room_areas_vs_table,
)
from engines.bet_agent.models.building import Room
from engines.bet_agent.models.summary import AnomalySeverity
from engines.bet_agent.testing import mk_bbox, mk_building, mk_source


def _mk_room(name: str, area: float, floor_id: str = "F-R0") -> Room:
    return Room(
        id=f"R-{name}", floor_id=floor_id, name=name, area_m2=area,
        source=mk_source(bbox=mk_bbox()), confidence=0.9,
    )


# ---------------------------------------------------------------------------
# GEO-005
# ---------------------------------------------------------------------------

def test_geo005_areas_match_table_within_tolerance() -> None:
    bm = mk_building(rooms=[_mk_room("sala", 25.5), _mk_room("cozinha", 15.0)])
    tabela = {"Sala": 25.0, "Cozinha": 15.0}
    anoms = check_room_areas_vs_table(bm, tabela)
    # delta sala = 0.5 / 25 = 2% < 5% ⇒ OK
    assert anoms == []


def test_geo005_catches_area_delta_above_tolerance() -> None:
    bm = mk_building(rooms=[_mk_room("sala", 30.0)])  # 20% delta
    tabela = {"sala": 25.0}
    anoms = check_room_areas_vs_table(bm, tabela)
    assert any(a.code == "GEO-005" and a.severity == AnomalySeverity.GRAVE for a in anoms)


def test_geo005_warns_when_room_not_in_table() -> None:
    bm = mk_building(rooms=[_mk_room("despensa_oculta", 3.0)])
    anoms = check_room_areas_vs_table(bm, {"sala": 25.0})
    # 1 AVISO (room sem tabela) + 1 AVISO (sala não lida)
    codes = [(a.code, a.severity) for a in anoms]
    assert codes.count(("GEO-005", AnomalySeverity.AVISO)) == 2


def test_geo005_warns_when_table_row_not_in_model() -> None:
    bm = mk_building(rooms=[_mk_room("sala", 25.0)])
    tabela = {"sala": 25.0, "cozinha": 15.0}
    anoms = check_room_areas_vs_table(bm, tabela)
    assert any(a.code == "GEO-005" and "cozinha" in a.message_pt.lower() for a in anoms)


def test_geo005_empty_table_no_anomalies() -> None:
    bm = mk_building(rooms=[_mk_room("sala", 25.0)])
    assert check_room_areas_vs_table(bm, {}) == []


def test_geo005_custom_tolerance() -> None:
    bm = mk_building(rooms=[_mk_room("sala", 27.0)])  # 8% delta
    tabela = {"sala": 25.0}
    # Tolerância 10% ⇒ passa.
    assert check_room_areas_vs_table(bm, tabela, tolerance_pct=10) == []
    # Tolerância 5% ⇒ falha.
    assert any(a.code == "GEO-005" for a in check_room_areas_vs_table(bm, tabela, tolerance_pct=5))


# ---------------------------------------------------------------------------
# GEO-007
# ---------------------------------------------------------------------------

def test_geo007_chain_matches_total() -> None:
    anoms = check_dimension_chain("fachada_norte", partial_m=[3.0, 4.0], total_m=7.0)
    assert anoms == []


def test_geo007_chain_within_2cm_tolerance() -> None:
    anoms = check_dimension_chain("fachada_norte", partial_m=[3.00, 4.01], total_m=7.02)
    assert anoms == []


def test_geo007_catches_delta_above_tolerance() -> None:
    anoms = check_dimension_chain(
        "fachada_norte", partial_m=[3.0, 4.0], total_m=7.5, page=1,
    )
    assert any(a.code == "GEO-007" and a.severity == AnomalySeverity.GRAVE for a in anoms)
    assert anoms[0].source.page == 1


def test_geo007_empty_partials_no_anomaly() -> None:
    assert check_dimension_chain("x", [], 0.0) == []


def test_geo007_custom_tolerance() -> None:
    # delta = 10 cm, tolerância 15 cm ⇒ OK.
    assert check_dimension_chain("x", [3.0, 4.0], 7.1, tolerance_m=0.15) == []
    # Tolerância 2 cm (default) ⇒ falha.
    assert any(check_dimension_chain("x", [3.0, 4.0], 7.1))
