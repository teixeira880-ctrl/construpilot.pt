"""3D model (IFC4) of the CLT house, built only from what the take-off measured on the drawings.

Per floor: CLT walls (each measured plan polygon extruded over the structural height), lintels (red dashed
bands, from the 2.30 m door head to the slab), the 240 mm slab of the +1 without the stair opening, the
140 mm roofs, steel beams (blue dashed bands; profile not on the drawing, drawn 200 mm deep under the slab),
exterior openings as IfcWindow and the reviewed rooms as IfcSpace. Every element carries the sheet and the
reference it comes from (Pset ConstruPilot_Origem). The foundation level is the datum (z = 0, top of the
ground slab); concrete is outside the CLT supply and is not modelled.
"""
from __future__ import annotations

import ifcopenshell
import ifcopenshell.api.aggregate
import ifcopenshell.api.geometry
import ifcopenshell.api.material
import ifcopenshell.api.pset
import ifcopenshell.api.root
import ifcopenshell.api.spatial
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from bim_studio.home_a_takeoff import (LINTEL, OPENING_HEAD_M, STEEL_BEAM, WALL_LAYERS, _bands, _wall_geometry,
                                       exterior_openings, rooms, upper_plate)
from bim_studio.sample_models import _Builder, _matrix

BEAM_DEPTH_M = .20  # hipótese: perfil não indicado


def _polygons(geometry):
    if geometry.is_empty:
        return []
    return [g for g in getattr(geometry, "geoms", [geometry]) if g.area > 1e-6]


class _Model(_Builder):
    def solid(self, storey, ifc_class, name, polygon, z0, depth, material, origin, predefined=None, quantities=None):
        ring = [(round(x, 4), round(y, 4)) for x, y in polygon.exterior.coords]
        kwargs = {"predefined_type": predefined} if predefined else {}
        el = ifcopenshell.api.root.create_entity(self.f, ifc_class=ifc_class, name=name, **kwargs)
        rep = ifcopenshell.api.geometry.add_slab_representation(self.f, context=self.body, depth=depth, polyline=ring)
        ifcopenshell.api.geometry.assign_representation(self.f, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(self.f, product=el, matrix=_matrix(z=z0))
        if ifc_class == "IfcSpace":
            ifcopenshell.api.aggregate.assign_object(self.f, relating_object=storey, products=[el])
        else:
            ifcopenshell.api.spatial.assign_container(self.f, relating_structure=storey, products=[el])
            ifcopenshell.api.material.assign_material(self.f, products=[el], material=self.material(material, "wood"))
        ps = ifcopenshell.api.pset.add_pset(self.f, product=el, name="ConstruPilot_Origem")
        ifcopenshell.api.pset.edit_pset(self.f, pset=ps, properties={k: str(v) for k, v in origin.items()})
        if quantities:
            ps = ifcopenshell.api.pset.add_pset(self.f, product=el, name="ConstruPilot_Quantidades")
            ifcopenshell.api.pset.edit_pset(self.f, pset=ps, properties={k: float(v) for k, v in quantities.items()})
        return el


def build(doc, extras):
    """doc: the Home A PDF (fitz document); extras: estimate_extras from the reviewed take-off."""
    b = _Model(units="m")
    b.project.Name = "Home A · CLT"
    floors = extras["floors"]
    h_rdc, h_1 = floors["RDC"]["height_m"], floors["+1"]["height_m"]
    slab_t, roof_t = .240, .140
    levels = {"RDC": 0.0, "+1": h_rdc + slab_t}
    b.storey("Fundações (cota de apoio, betão fora do fornecimento CLT)", 0.0)
    storeys = {"RDC": b.storey("RDC", 0.0), "+1": b.storey("+1", levels["+1"]),
               "Cobertura": b.storey("Cobertura", levels["+1"] + h_1)}
    counts = {}
    page_h = doc[1].rect.height

    def to_m(geom, k):
        from shapely.affinity import affine_transform
        return affine_transform(geom, [k, 0, 0, -k, 0, page_h * k])   # y up, same origin on both sheets

    plate_m = None
    for number, key in ((2, "RDC"), (3, "+1")):
        page = doc[number - 1]
        k, markers, walls = _wall_geometry(page)
        ids = [m["id"] for m in markers if m["id"] != "scale"]
        z, height = levels[key], floors[key]["height_m"]
        for ref, wall in zip(ids, walls):
            width = round(min(wall.bounds[2] - wall.bounds[0], wall.bounds[3] - wall.bounds[1]) * k * 100) * 10
            b.solid(storeys[key], "IfcWall", f"Parede CLT {width} mm · {ref}", to_m(wall, k), z, height,
                    f"CLT {width} mm {WALL_LAYERS.get(width, 5)} camadas", {"Folha": number, "Referencia": ref, "Fonte": "medido"},
                    "SOLIDWALL")
            counts["paredes"] = counts.get("paredes", 0) + 1
        wall_union = unary_union(walls)
        for n, band in enumerate(_bands(page, LINTEL, k), 1):
            for part in _polygons(band.difference(wall_union)):
                width = round(min(band.bounds[2] - band.bounds[0], band.bounds[3] - band.bounds[1]) * k * 100) * 10
                b.solid(storeys[key], "IfcBeam", f"Lintel CLT {width} mm · lintel-{n}", to_m(part, k), z + OPENING_HEAD_M,
                        height - OPENING_HEAD_M, f"CLT {width} mm {WALL_LAYERS.get(width, 5)} camadas",
                        {"Folha": number, "Referencia": f"lintel-{n}", "Fonte": "medido; topo do vão 2,30 m (portas cotadas)"}, "LINTEL")
                counts["linteis"] = counts.get("linteis", 0) + 1
        for n, band in enumerate(_bands(page, STEEL_BEAM, k), 1):
            b.solid(storeys[key], "IfcBeam", f"Viga de aço · beam-{n}", to_m(band, k), z + height - BEAM_DEPTH_M, BEAM_DEPTH_M,
                    "Aço (perfil a definir)", {"Folha": number, "Referencia": f"beam-{n}", "Fonte": "comprimento medido; altura 200 mm hipótese"}, "BEAM")
            counts["vigas"] = counts.get("vigas", 0) + 1
        for room in rooms(page, k):
            x0, y0, x1, y1 = room["rect"]
            rect = box(x0 * page.rect.width, y0 * page.rect.height, x1 * page.rect.width, y1 * page.rect.height)
            b.solid(storeys[key], "IfcSpace", room["nome"], to_m(rect, k), z, floors[key]["ceiling_height_m"], "",
                    {"Folha": number, "Referencia": room["nome"], "Fonte": "divisão revista",
                     "LadosAConfirmar": ", ".join(room["lados_a_confirmar"]) or "—"},
                    quantities={"Area_m2": room["area_m2"]})
            counts["divisoes"] = counts.get("divisoes", 0) + 1
        if number == 2:
            x0, _, x1, y1 = wall_union.bounds
            terrace = min(m["rect"][1] for m in markers if m["id"] == "clt-2905") * page.rect.height
            envelope = box(x0, terrace, x1, y1)
        else:
            plate, void, outline = upper_plate(page, markers)
            envelope, plate_m = plate, (to_m(plate, k), to_m(void, k), to_m(outline, k))
        for n, opening in enumerate(exterior_openings(page, k, walls, envelope), 1):
            x0, y0, x1, y1 = opening["rect"]
            seg = box(x0 * page.rect.width, y0 * page.rect.height, x1 * page.rect.width, y1 * page.rect.height)
            head = floors[key]["ceiling_height_m"] if opening["sobre"] == "viga" else \
                OPENING_HEAD_M if opening["sobre"] == "lintel" else (1.2 if opening["tipo"] == "janela" else 2.1)
            sill = 0.0 if opening["tipo"] == "vao_envidracado" or opening["sobre"] else 2.3 - 1.2
            b.solid(storeys[key], "IfcWindow", f"Vão exterior {opening['largura_m']:.2f} m", to_m(seg, k), z + sill,
                    head if sill == 0 else 1.2, "Caixilharia (a definir)",
                    {"Folha": number, "Referencia": f"vao-{n}", "Fonte": "largura medida; altura hipótese salvo sob lintel ou viga"})
            counts["vaos"] = counts.get("vaos", 0) + 1
    plate, void, outline = plate_m
    for part in _polygons(plate.difference(void)):
        b.solid(storeys["+1"], "IfcSlab", "Laje CLT 240 mm 7 camadas", part, levels["+1"] - slab_t, slab_t, "CLT 240 mm 7 camadas",
                {"Folha": 3, "Referencia": "faces exteriores das paredes do +1, sem a escada", "Fonte": "medido"}, "FLOOR")
    for part in _polygons(outline.difference(plate)):
        b.solid(storeys["RDC"], "IfcSlab", "Cobertura CLT 140 mm (RDC)", part, h_rdc, roof_t, "CLT 140 mm 5 camadas",
                {"Folha": 3, "Referencia": "contorno violeta menos a laje do +1", "Fonte": "medido; composição do corte"}, "ROOF")
    b.solid(storeys["Cobertura"], "IfcSlab", "Cobertura CLT 140 mm (+1)", plate, levels["+1"] + h_1, roof_t, "CLT 140 mm 5 camadas",
            {"Folha": 3, "Referencia": "laje do +1", "Fonte": "medido"}, "ROOF")
    counts["lajes_e_coberturas"] = 3
    return b.f, counts
