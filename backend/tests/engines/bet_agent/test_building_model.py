"""Testes dos modelos Pydantic de BuildingModel: source + confidence + validações."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from engines.bet_agent.models.building import (
    BBox,
    BuildingModel,
    ElementSource,
    ExtractionMethod,
    Floor,
    FloorKind,
    Wall,
    WallKind,
)
from engines.bet_agent.testing import mk_floor, mk_wall


def test_element_source_requires_bbox_and_page() -> None:
    with pytest.raises(ValidationError):
        ElementSource(page=0, bbox=BBox(x1=0, y1=0, x2=1, y2=1), extraction_method=ExtractionMethod.VISION)
    # page >= 1 obrigatório
    ok = ElementSource(page=1, bbox=BBox(x1=0, y1=0, x2=1, y2=1), extraction_method=ExtractionMethod.VISION)
    assert ok.page == 1


def test_floor_confidence_bounded_0_1() -> None:
    with pytest.raises(ValidationError):
        Floor(
            id="F-1", kind=FloorKind.RC, level_m=0,
            source=ElementSource(page=1, bbox=BBox(x1=0, y1=0, x2=1, y2=1),
                                 extraction_method=ExtractionMethod.VISION),
            confidence=1.5,
        )


def test_wall_positive_dimensions_required() -> None:
    with pytest.raises(ValidationError):
        Wall(
            id="W-1", floor_id="F-1", kind=WallKind.INTERIOR,
            length_m=0, thickness_m=0.15,
            source=ElementSource(page=1, bbox=BBox(x1=0, y1=0, x2=1, y2=1),
                                 extraction_method=ExtractionMethod.VISION),
            confidence=0.9,
        )


def test_building_model_serializes_roundtrip() -> None:
    bm = BuildingModel(
        project_id="test",
        floors=[mk_floor()],
        walls=[mk_wall()],
    )
    dumped = bm.model_dump()
    restored = BuildingModel.model_validate(dumped)
    assert restored.project_id == "test"
    assert len(restored.floors) == 1
    assert len(restored.walls) == 1


def test_user_imposed_flag_defaults_false() -> None:
    f = mk_floor()
    assert f.user_imposed is False


def test_building_model_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        BuildingModel.model_validate({"project_id": "t", "nonsense": 42})
