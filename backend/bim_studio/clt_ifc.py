"""IFC4 model of the CLT production pieces (IfcOpenShell, LGPL-3.0, used as a library).

Each production piece from clt_walls becomes an IfcWall with an extruded body,
its openings as IfcOpeningElement voids, a CLT layer set, the IFC base
quantities and a ConstruPilot property set with the source of every value.

The model is then re-read and tessellated by OpenCascade (ifcopenshell.geom),
and the solid volume of every wall is compared with the analytic volume. This
is a third independent engine on the same quantities; a wall that differs by
more than 2 % fails the check.
"""
from __future__ import annotations

import math
import tempfile
from pathlib import Path

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.geom
import ifcopenshell.util.shape
import numpy as np

from bim_studio.clt_geometry import reconciliation


def _placement(x, y, z, ux, uy):
    m = np.eye(4)
    m[0][0], m[1][0] = ux, uy
    m[0][1], m[1][1] = -uy, ux
    m[0][3], m[1][3], m[2][3] = x, y, z
    return m


def build(floors, *, project_name="ConstruPilot CLT", slabs=()):
    """floors: list of (name, elevation_m, walls, pieces) with clt_walls models and pieces.

    slabs: list of dicts {name, storey, polygon [(x,y),...], thickness_mm, elevation_m, source}.
    Returns (ifc bytes, verification rows).
    """
    run = ifcopenshell.api.run
    f = ifcopenshell.api.run("project.create_file", version="IFC4")
    project = run("root.create_entity", f, ifc_class="IfcProject", name=project_name)
    run("unit.assign_unit", f, length={"is_metric": True, "raw": "METERS"})
    model = run("context.add_context", f, context_type="Model")
    body = run("context.add_context", f, context_type="Model", context_identifier="Body",
               target_view="MODEL_VIEW", parent=model)
    site = run("root.create_entity", f, ifc_class="IfcSite", name="Obra")
    building = run("root.create_entity", f, ifc_class="IfcBuilding", name=project_name)
    run("aggregate.assign_object", f, relating_object=project, products=[site])
    run("aggregate.assign_object", f, relating_object=site, products=[building])
    materials, storeys, checks = {}, {}, []

    def material_set(thickness_mm, layers):
        key = (thickness_mm, layers)
        if key not in materials:
            mset = run("material.add_material_set", f, name=f"CLT {thickness_mm:g} mm {layers}c",
                       set_type="IfcMaterialLayerSet")
            wood = run("material.add_material", f, name="CLT C24", category="wood")
            lamella = thickness_mm / layers / 1000
            for _ in range(layers):
                layer = run("material.add_layer", f, layer_set=mset, material=wood)
                run("material.edit_layer", f, layer=layer, attributes={"LayerThickness": lamella})
            materials[key] = mset
        return materials[key]

    for name, elevation, walls, pieces in floors:
        storey = run("root.create_entity", f, ifc_class="IfcBuildingStorey", name=name)
        storey.Elevation = elevation
        run("aggregate.assign_object", f, relating_object=building, products=[storey])
        storeys[name] = (storey, elevation)
        by_id = {w.id: w for w in walls}
        for p in pieces:
            w = by_id[p["parede"]]
            ux, uy = w.direction()
            t = w.thickness_m
            x = w.x1 + ux * p["inicio_m"] + uy * t / 2
            y = w.y1 + uy * p["inicio_m"] - ux * t / 2
            wall = run("root.create_entity", f, ifc_class="IfcWall", name=p["id"])
            wall.PredefinedType = "SOLIDWALL"
            rep = run("geometry.add_wall_representation", f, context=body, length=p["comprimento_m"],
                      height=p["altura_m"], thickness=t)
            run("geometry.assign_representation", f, product=wall, representation=rep)
            run("geometry.edit_object_placement", f, product=wall,
                matrix=_placement(x, y, elevation + w.base_z_m, ux, uy), is_si=True)
            run("spatial.assign_container", f, relating_structure=storey, products=[wall])
            run("material.assign_material", f, products=[wall], type="IfcMaterialLayerSet",
                material=material_set(p["espessura_mm"], p["camadas"]))
            for k, o in enumerate(p["vaos"], 1):
                hole = run("root.create_entity", f, ifc_class="IfcOpeningElement", name=f"{p['id']}-V{k}")
                orep = run("geometry.add_wall_representation", f, context=body, length=o["width_m"],
                           height=o["height_m"], thickness=t + 0.02)
                run("geometry.assign_representation", f, product=hole, representation=orep)
                # 10 mm beyond each face, along the wall's local −Y (world (uy, −ux)).
                ox = x + ux * o["offset_m"] + uy * 0.01
                oy = y + uy * o["offset_m"] - ux * 0.01
                run("geometry.edit_object_placement", f, product=hole,
                    matrix=_placement(ox, oy, elevation + w.base_z_m + o["sill_m"], ux, uy), is_si=True)
                run("feature.add_feature", f, feature=hole, element=wall)
            qto = run("pset.add_qto", f, product=wall, name="Qto_WallBaseQuantities")
            run("pset.edit_qto", f, qto=qto, properties={
                "Length": p["comprimento_m"], "Height": p["altura_m"], "Width": t,
                "GrossSideArea": p["area_bruta_m2"], "NetSideArea": p["area_liquida_m2"],
                "GrossVolume": p["volume_bruto_m3"], "NetVolume": p["volume_liquido_m3"]})
            pset = run("pset.add_pset", f, product=wall, name="ConstruPilot_CLT")
            run("pset.edit_pset", f, pset=pset, properties={
                "Peca": p["id"], "Parede": p["parede"], "Camadas": p["camadas"], "EspessuraMM": p["espessura_mm"],
                "Origem": p["origem"][:250], "Estado": "medido no desenho" if w.source else "eixo fornecido"})
    for s in slabs:
        storey, elevation = storeys[s["storey"]]
        slab = run("root.create_entity", f, ifc_class="IfcSlab", name=s["name"])
        slab.PredefinedType = "FLOOR"
        rep = run("geometry.add_slab_representation", f, context=body, depth=s["thickness_mm"] / 1000,
                  polyline=[tuple(map(float, pt)) for pt in s["polygon"]])
        run("geometry.assign_representation", f, product=slab, representation=rep)
        run("geometry.edit_object_placement", f, product=slab,
            matrix=_placement(0, 0, s["elevation_m"], 1, 0), is_si=True)
        run("spatial.assign_container", f, relating_structure=storey, products=[slab])
        pset = run("pset.add_pset", f, product=slab, name="ConstruPilot_CLT")
        run("pset.edit_pset", f, pset=pset, properties={"Origem": s.get("source", "")[:250]})

    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "clt.ifc"
        f.write(str(path))
        data = path.read_bytes()
    checks = verify(data, {p["id"]: p["volume_liquido_m3"] for _, _, _, pieces in floors for p in pieces})
    return data, checks


def verify(data: bytes, expected: dict):
    """Volumes of the IFC solids, computed by OpenCascade, against the analytic volumes."""
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "check.ifc"
        path.write_bytes(data)
        model = ifcopenshell.open(str(path))
    settings = ifcopenshell.geom.settings()
    rows = []
    for wall in model.by_type("IfcWall"):
        shape = ifcopenshell.geom.create_shape(settings, wall)
        volume = float(ifcopenshell.util.shape.get_volume(shape.geometry))
        reference = expected.get(wall.Name)
        if reference is None:
            continue
        check = reconciliation(volume, reference, zero_tolerance=1e-6)
        rows.append({"peca": wall.Name, "volume_ifc_m3": round(volume, 5), "volume_analitico_m3": reference,
                     "erro_percent": None if check["error_percent"] is None else round(check["error_percent"], 4),
                     "passed": check["passed"]})
    if not rows or not math.isclose(len(rows), len(expected)):
        raise ValueError("O modelo IFC não contém todas as peças medidas.")
    return {"motor": f"IfcOpenShell {ifcopenshell.version} + OpenCascade", "pecas": rows,
            "passed": all(r["passed"] for r in rows),
            "volume_ifc_m3": round(sum(r["volume_ifc_m3"] for r in rows), 5),
            "volume_analitico_m3": round(sum(r["volume_analitico_m3"] for r in rows), 5)}
