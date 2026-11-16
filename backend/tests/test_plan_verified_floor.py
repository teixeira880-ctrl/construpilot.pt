from __future__ import annotations

from copy import deepcopy
import math

import pytest
from shapely.geometry import Point, Polygon

from engines import plan_verified_floor
from engines.bim_core import edicao, ifc_builder
from engines.bim_core.model import from_takeoff


VERTICES = [(0, 10), (12, 10), (12, 5), (6, 5), (6, 0), (0, 0)]
PPM = 66.6496


def plan():
    scale_pt = 72 / (0.0254 * 100)
    path = [(137+x*scale_pt, 638.8897705-y*scale_pt) for x, y in VERTICES]
    page = {"dpi": 169.29, "width_px": 2800, "height_px": 1979, "detected_scale_denominator": 100,
            "text_blocks": [{"text": "Área bruta total 180 m² · 90 m² por piso"}],
            "pdf_dimensions": [{"orientation": direction, "value_m": length, "measured_m": length}
                               for direction, length in [("h", 12), ("h", 6), ("h", 6), ("v", 10), ("v", 5)]],
            "vectors": [{"p1": p, "p2": q, "paint_type": "fs", "type": "line", "path_id": 12}
                        for p, q in zip(path, path[1:]+path[:1])]}
    result = {"kind": "pdf", "pages": [deepcopy(page), deepcopy(page)],
              "calibrations": {str(i): {"pixels_per_meter": PPM} for i in range(2)}, "structure": {}}
    for i, coords in enumerate(([(316,833), (1123,833), (1123,1170), (720,1170), (720,1506), (316,1506)],
                                [(316,833), (1120,833), (1120,1168), (720,1168), (720,1500), (316,1500)])):
        walls = [{"wall_id": str(n), "type": "porteur", "x1": a[0], "y1": a[1], "x2": b[0], "y2": b[1]}
                 for n, (a,b) in enumerate(zip(coords, coords[1:]+coords[:1]))]
        result["structure"][str(i)] = {"walls": walls, "floors": [{"floor_id": "L", "name": "Piso", "points": coords}],
                                         "image_width": 2800, "image_height": 1979,
                                         "openings": [{"opening_id": "J", "kind": "fenetre", "x1": 980,
                                                       "y1": 833, "x2": 1106, "y2": 833}]}
    return result


@pytest.mark.parametrize("level", [0, 1])
def test_editor_and_ifc_share_the_six_dimensioned_segments(level):
    import ifcopenshell
    import ifcopenshell.geom
    from ifcopenshell.util.element import get_psets
    from shapely.affinity import translate
    from shapely.ops import unary_union

    data = plan()
    raw = data["structure"][str(level)]
    assert Polygon(raw["floors"][0]["points"]).area / PPM**2 > 90
    structure = plan_verified_floor.verified_structure(data, level)
    outline = structure["verified_outline"]
    assert outline == {"source": "pdf_vector_dimensions", "area_m2": 90, "width_m": 12, "depth_m": 10,
                       "recess_m": [6, 5], "sides_m": [12, 5, 6, 5, 6, 10], "perimeter_m": 44}
    pts = structure["floors"][0]["points"]
    # Independent check using the Editor's pixels-per-metre ruler.
    assert Polygon(pts).area / PPM**2 == pytest.approx(90, abs=1e-9)
    assert [math.dist(a,b)/PPM for a,b in zip(pts, pts[1:]+pts[:1])] == pytest.approx(outline["sides_m"])
    model = from_takeoff(structure, PPM, origin_structure=raw)
    file = ifcopenshell.file.from_string(ifc_builder.build_ifc(model).to_string())
    assert not ifc_builder.validate(file)
    slab, = file.by_type("IfcSlab")
    props = get_psets(slab)["Qto_SlabBaseQuantities"]
    assert props["GrossArea"] == 90 and props["GrossVolume"] == 18
    assert [get_psets(w)["Qto_WallBaseQuantities"]["Length"] for w in file.by_type("IfcWall")] == outline["sides_m"]
    shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), slab)
    vertices = list(zip(*[iter(shape.geometry.verts)]*3))
    faces = list(zip(*[iter(shape.geometry.faces)]*3))
    floor = unary_union([Polygon([vertices[i][:2] for i in face]) for face in faces
                         if len({vertices[i][2] for i in face}) == 1])
    left, bottom, _, _ = floor.bounds
    exact = translate(floor, -left, -bottom)
    assert exact.symmetric_difference(Polygon(VERTICES)).area < 1e-8
    assert not exact.covers(Point(9, 2.5))


def test_old_model_edits_follow_identifiers_and_undo_can_load_legacy_geometry():
    data = plan()
    raw = data["structure"]["0"]
    corrected = plan_verified_floor.verified_structure(data, 0)
    read = from_takeoff(raw, PPM)
    verified = from_takeoff(corrected, PPM, origin_structure=raw)
    edited = deepcopy(read)
    edited.walls[0].thickness = .25
    edited.walls[2].y1 += .15  # explicit change to this wall axis
    edited.params["pavimentos"] = {"L": {"material": "ceramica", "espessura": None}}
    migrated = edicao.reconcile_pdf_outline(edited, read, verified)
    assert migrated.slabs[0].area == pytest.approx(90)
    assert migrated.walls[0].length == pytest.approx(12)
    assert migrated.walls[0].thickness == .25
    assert migrated.walls[2].y1 == read.walls[2].y1 + .15
    assert migrated.params["pavimentos"]["L"]["material"] == "ceramica"
    assert edicao.para_dict(migrated) == edicao.para_dict(edicao.reconcile_pdf_outline(migrated, read, verified))


def test_validation_keeps_ifc_feature_state_while_two_requests_overlap(monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from time import sleep

    import ifcopenshell.validate

    p = plan()
    files = [ifc_builder.build_ifc(from_takeoff(plan_verified_floor.verified_structure(p, i), PPM)) for i in (0, 1)]
    original = ifcopenshell.validate.validate
    wrapper = ifcopenshell.ifcopenshell_wrapper
    flag = "use_attribute_value_derived"
    before = wrapper.get_feature(flag)
    barrier = Barrier(2)

    def check(file, logger, **kwargs):
        assert wrapper.get_feature(flag) == before
        wrapper.set_feature(flag, not before)
        sleep(.03)  # keep the process-wide setting live while the other request starts
        try:
            assert wrapper.get_feature(flag) != before
        finally:
            wrapper.set_feature(flag, before)
        original(file, logger, **kwargs)

    def request(file):
        barrier.wait(timeout=3)
        return ifc_builder.validate(file)

    monkeypatch.setattr(ifcopenshell.validate, "validate", check)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert list(pool.map(request, files)) == [[], []]
    assert wrapper.get_feature(flag) == before


@pytest.mark.parametrize("mode", ["wrong_scale", "wrong_area", "two_paths", "manual", "wrong_frame", "no_dimension"])
def test_uncertain_or_manually_changed_geometry_is_not_replaced(mode):
    data = plan()
    page = data["pages"][0]
    existing = data["structure"]["0"]
    if mode == "wrong_scale":
        data["calibrations"]["0"]["pixels_per_meter"] = PPM * 1.05
    elif mode == "wrong_area":
        page["text_blocks"][0]["text"] = "91,8 m² por piso"
    elif mode == "two_paths":
        page["vectors"] += [{**v, "path_id": 13} for v in page["vectors"]]
    elif mode == "manual":
        existing["edited_at"] = "today"
    elif mode == "wrong_frame":
        existing["image_width"] = 1800
    else:
        page["pdf_dimensions"][0]["unverified"] = True
    assert plan_verified_floor.verified_structure(data, 0) is existing
