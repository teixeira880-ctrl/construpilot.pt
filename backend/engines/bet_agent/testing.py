"""Helpers para construir BuildingModels sintéticos em testes.

Nenhum destes helpers depende do reader LLM — são usados para validar
os checks determinísticos e o Summary.

Vive no pacote `engines.bet_agent` (não em `tests/`) para evitar colisão de
namespace do pytest (`tests/engines/__init__.py` sobrepõe-se ao `engines/`
quando pytest insere `tests/` no sys.path).
"""
from __future__ import annotations

from engines.bet_agent.models.building import (
    BBox,
    BuildingModel,
    ElementSource,
    ExtractionMethod,
    Floor,
    FloorKind,
    Opening,
    OpeningKind,
    Roof,
    RoofKind,
    Room,
    SlabOpening,
    Stair,
    StructuralElement,
    StructuralKind,
    Wall,
    WallKind,
)


def mk_bbox(x1: float = 0, y1: float = 0, x2: float = 100, y2: float = 100) -> BBox:
    return BBox(x1=x1, y1=y1, x2=x2, y2=y2)


def mk_source(page: int = 1, bbox: BBox | None = None,
              method: ExtractionMethod = ExtractionMethod.VECTOR_TEXT) -> ElementSource:
    return ElementSource(page=page, bbox=bbox or mk_bbox(), extraction_method=method)


def mk_floor(fid: str = "F-R0", kind: FloorKind = FloorKind.RC,
             level_m: float = 0.0, height_clear_m: float | None = 2.7,
             confidence: float = 0.95, method: ExtractionMethod = ExtractionMethod.VECTOR_TEXT,
             habitable: bool | None = None) -> Floor:
    return Floor(
        id=fid, kind=kind, level_m=level_m, height_clear_m=height_clear_m,
        habitable=habitable,
        source=mk_source(method=method), confidence=confidence,
    )


def mk_wall(wid: str = "W-01", floor_id: str = "F-R0", length_m: float = 5.0,
            thickness_m: float = 0.15, kind: WallKind = WallKind.INTERIOR,
            bbox: BBox | None = None) -> Wall:
    return Wall(
        id=wid, floor_id=floor_id, kind=kind, length_m=length_m,
        thickness_m=thickness_m,
        source=mk_source(bbox=bbox or mk_bbox()), confidence=0.9,
    )


def mk_opening(oid: str = "O-01", wall_id: str = "W-01",
               kind: OpeningKind = OpeningKind.PORTA,
               width_m: float = 0.9, height_m: float = 2.1,
               bbox: BBox | None = None) -> Opening:
    return Opening(
        id=oid, wall_id=wall_id, kind=kind, width_m=width_m, height_m=height_m,
        source=mk_source(bbox=bbox or mk_bbox(10, 10, 50, 50)), confidence=0.9,
    )


def mk_stair(sid: str = "S-01", floor_from_id: str = "F-R0", floor_to_id: str = "F-R1",
             opening_length_m: float = 3.6, opening_width_m: float = 1.2,
             riser_count: int | None = None, riser_height_m: float | None = None,
             tread_depth_m: float | None = None) -> Stair:
    return Stair(
        id=sid, floor_from_id=floor_from_id, floor_to_id=floor_to_id,
        opening_length_m=opening_length_m, opening_width_m=opening_width_m,
        riser_count=riser_count, riser_height_m=riser_height_m,
        tread_depth_m=tread_depth_m,
        source=mk_source(), confidence=0.9,
    )


def mk_slab_opening(soid: str = "SO-01", floor_id: str = "F-R0",
                    length_m: float = 3.6, width_m: float = 1.2,
                    purpose: str = "escada",
                    bbox: BBox | None = None) -> SlabOpening:
    return SlabOpening(
        id=soid, floor_id=floor_id, length_m=length_m, width_m=width_m, purpose=purpose,
        source=mk_source(bbox=bbox or mk_bbox(0, 0, 200, 200)), confidence=0.9,
    )


def mk_structural(eid: str = "LAJE-01", floor_id: str = "F-R0",
                  kind: StructuralKind = StructuralKind.LAJE,
                  thickness_mm: int | None = 250, span_m: float | None = None) -> StructuralElement:
    return StructuralElement(
        id=eid, floor_id=floor_id, kind=kind,
        thickness_mm=thickness_mm, span_m=span_m,
        source=mk_source(), confidence=0.9,
    )


def mk_building(project_id: str = "test-proj", **sections) -> BuildingModel:
    return BuildingModel(project_id=project_id, **sections)
