"""Construção de um ficheiro IFC 4.3 (IfcOpenShell) a partir de um `BuildingModel`.

Convenções do piso gerado (um piso por página de planta):
- cota 0 = pavimento acabado do piso; as lajes lidas na planta ficam POR BAIXO (de −e a 0);
- paredes e pilares vão de 0 ao pé-direito; as vigas ficam penduradas no topo (de H − h a H);
- as sapatas ficam sob a laje (ou sob a cota 0 se não houver laje).

Cada elemento recebe um GlobalId DETERMINÍSTICO (uuid5 de plano + página + id de origem): voltar a
gerar o modelo mantém os mesmos identificadores, para que cálculos, orçamentos e comentários BCF
continuem ligados aos mesmos elementos.
"""
from __future__ import annotations

import math
import uuid
from itertools import product
from threading import Lock

import numpy as np

from .model import BuildingModel

SCHEMA = "IFC4X3"
_NS = uuid.UUID("5b0f7c1e-6c2a-4b8e-9a51-c0a57e2f1a10")  # espaço de nomes ConstruPilot BIM
_SCHEMA_VALIDATION_LOCK = Lock()

MATERIALS = {
    "concrete": ("Betão armado C25/30", "CONCRETE"),
    "masonry": ("Alvenaria", "MASONRY"),
}
OPENING_PALETTE = {
    "frame": ("Caixilharia antracite", (.15, .18, .20), 0.),
    "glass": ("Vidro", (.58, .76, .82), .62),
    "door": ("Folha de madeira", (.52, .34, .22), 0.),
    "hardware": ("Ferragens acetinadas", (.70, .72, .73), 0.),
}


def stable_guid(*parts) -> str:
    import ifcopenshell.guid  # noqa: PLC0415
    return ifcopenshell.guid.compress(uuid.uuid5(_NS, ":".join(str(p) for p in parts)).hex)


def _matrix(x: float, y: float, z: float, angle: float = 0.0) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    m = np.eye(4)
    m[0][0], m[0][1], m[1][0], m[1][1] = c, -s, s, c
    m[0][3], m[1][3], m[2][3] = x, y, z
    return m


def _floor_preview(points, tiled, color):
    from shapely import constrained_delaunay_triangles
    from shapely.geometry import Polygon, box

    polygon = Polygon(points)
    xmin, ymin, xmax, ymax = polygon.bounds
    module, half_joint = .60, .002
    cols = range(math.floor(xmin/module), math.ceil(xmax/module))
    rows = range(math.floor(ymin/module), math.ceil(ymax/module))
    # Tile joints are a presentation detail. The base surface keeps the full
    # slab outline and the preview never declares a tile size or thickness.
    tiled = tiled and len(cols) * len(rows) <= 3200
    base = ((.57, .51, .46) if tiled else color)
    parts = [(base, 0., [polygon])]
    if tiled:
        tiles = [[] for _ in range(3)]
        for i, j in product(cols, rows):
            cell = box(i*module+half_joint, j*module+half_joint, (i+1)*module-half_joint, (j+1)*module-half_joint)
            if polygon.intersects(cell):
                tiles[(i + 2*j) % 3].append(polygon.intersection(cell))
        for tone, regions in zip((.92, 1.0, 1.06), tiles):
            if regions:
                parts.append((tuple(min(c*tone, 1.) for c in color), .0004, regions))

    mesh_vertices, mesh_faces, colors = [], [], []
    for shade, z, regions in parts:
        vertices, faces = [], []
        for region in regions:
            for triangle in constrained_delaunay_triangles(region).geoms:
                coords = list(triangle.exterior.coords)[:-1]
                if not triangle.exterior.is_ccw:
                    coords.reverse()
                faces.append(list(range(len(vertices), len(vertices) + len(coords))))
                vertices.extend((x, y, z) for x, y in coords)
        if faces:
            mesh_vertices.append(vertices)
            mesh_faces.append(faces)
            colors.append(shade)
    return mesh_vertices, mesh_faces, colors


def build_ifc(model: BuildingModel, *, project_name: str = "Projeto ConstruPilot",
              author: str = "ConstruPilot"):
    """Devolve um `ifcopenshell.file` IFC4X3 com o piso descrito por `model`."""
    import ifcopenshell  # noqa: PLC0415
    import ifcopenshell.api  # noqa: PLC0415
    from .edicao import PAVIMENTOS, REVESTIMENTOS

    api = ifcopenshell.api.run
    f = api("project.create_file", version=SCHEMA)
    key = (model.plan_id or "plan", model.page_index)

    def entity(ifc_class, name, source_id, predefined_type=None):
        el = api("root.create_entity", f, ifc_class=ifc_class, name=name,
                 predefined_type=predefined_type)
        el.GlobalId = stable_guid(*key, ifc_class, source_id)
        return el

    project = entity("IfcProject", project_name, "project")
    # Unidades SI em METROS (não em mm): os perfis e as quantidades são escritos tal como calculados.
    api("unit.assign_unit", f, units=[
        api("unit.add_si_unit", f, unit_type="LENGTHUNIT"),
        api("unit.add_si_unit", f, unit_type="AREAUNIT"),
        api("unit.add_si_unit", f, unit_type="VOLUMEUNIT"),
        api("unit.add_si_unit", f, unit_type="PLANEANGLEUNIT"),
    ])
    model3d = api("context.add_context", f, context_type="Model")
    body = api("context.add_context", f, context_type="Model", context_identifier="Body",
               target_view="MODEL_VIEW", parent=model3d)
    plan2d = api("context.add_context", f, context_type="Plan")
    api("context.add_context", f, context_type="Plan", context_identifier="Annotation",
        target_view="PLAN_VIEW", parent=plan2d)

    site = entity("IfcSite", "Terreno", "site")
    building = entity("IfcBuilding", "Edifício", "building")
    storey = entity("IfcBuildingStorey", model.storey_name, f"storey-{model.page_index}")
    storey.Elevation = 0.0
    api("aggregate.assign_object", f, products=[site], relating_object=project)
    api("aggregate.assign_object", f, products=[building], relating_object=site)
    api("aggregate.assign_object", f, products=[storey], relating_object=building)
    for el in (site, building, storey):
        api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4))

    mats = {}
    for k, (name, category) in MATERIALS.items():
        mat = api("material.add_material", f, name=name, category=category)
        mats[k] = mat

    def finish(el, matrix, rep, material, psets: dict, qto_name: str | None, qtos: dict,
               source_id: str):
        api("geometry.edit_object_placement", f, product=el, matrix=matrix)
        if rep is not None:
            api("geometry.assign_representation", f, product=el, representation=rep)
        if material is not None:
            api("material.assign_material", f, products=[el], material=mats[material])
        for pname, props in psets.items():
            ps = api("pset.add_pset", f, product=el, name=pname)
            api("pset.edit_pset", f, pset=ps, properties=props)
        origin = api("pset.add_pset", f, product=el, name="CP_Origem")
        api("pset.edit_pset", f, pset=origin, properties={
            "Fonte": "ConstruPilot — leitura de planta", "IdOrigem": source_id,
            "PlanoId": model.plan_id, "Pagina": int(model.page_index)})
        if qto_name and qtos:
            q = api("pset.add_qto", f, product=el, name=qto_name)
            api("pset.edit_qto", f, qto=q, properties={k: round(float(v), 4) for k, v in qtos.items()})

    contained = []
    slab_depth = max((s.thickness for s in model.slabs), default=0.0)

    # ---------- Paredes + vãos ----------
    walls_by_id = {}
    styles = {}

    def surface(label, color, transparency=0.):
        if label not in styles:
            red, green, blue = color
            style = api("style.add_style", f, name=label)
            attributes = {"SurfaceColour": {"Name": label, "Red": red, "Green": green, "Blue": blue}}
            if transparency:
                # WebIFC reads alpha from SurfaceStyleRendering; exporters
                # reading the IFC also receive the glazing reflectance type.
                api("style.add_surface_style", f, style=style, ifc_class="IfcSurfaceStyleRendering",
                    attributes={**attributes, "Transparency": transparency, "DiffuseColour": 1.0,
                                "ReflectanceMethod": "GLASS"})
            else:
                api("style.add_surface_style", f, style=style, ifc_class="IfcSurfaceStyleShading", attributes=attributes)
            styles[label] = style
        return styles[label]

    revestimentos = model.params.get("revestimentos") or {}
    openings_by_wall: dict[str, list] = {}
    for o in model.openings:
        openings_by_wall.setdefault(o.wall_id, []).append(o)
    for w in model.walls:
        name = ("Parede resistente" if w.load_bearing else "Divisória") + f" {len(walls_by_id) + 1}"
        el = entity("IfcWall", name, w.source_id, predefined_type="SOLIDWALL" if w.load_bearing else "PARTITIONING")
        rep = api("geometry.add_wall_representation", f, context=body, length=w.length,
                  height=w.height, thickness=w.thickness, offset=-w.thickness / 2)
        void = sum(o.width * o.height for o in openings_by_wall.get(w.source_id, [])) * w.thickness
        gross = w.length * w.height * w.thickness
        finish(el, _matrix(w.x1, w.y1, 0.0, w.angle), rep, "concrete" if w.load_bearing else "masonry",
               {"Pset_WallCommon": {"LoadBearing": w.load_bearing,
                                    "Reference": "Parede resistente" if w.load_bearing else "Divisória"}},
               "Qto_WallBaseQuantities",
               {"Length": w.length, "Width": w.thickness, "Height": w.height,
                "GrossVolume": gross, "NetVolume": max(gross - void, 0.0)},
               w.source_id)
        revestimento = revestimentos.get(w.source_id)
        cor = (model.params.get("cores_parede") or {}).get(w.source_id)
        props = {}
        if revestimento in REVESTIMENTOS:
            label, color = REVESTIMENTOS[revestimento]
            props["Revestimento"] = label
        elif w.load_bearing:
            label, color = "Betão", (.61, .62, .60)
        else:
            label, color = "Alvenaria", (.86, .83, .76)
        if cor:
            label = f"Pintura {cor.upper()}"
            color = tuple(int(cor[i:i+2], 16) / 255 for i in (1, 3, 5))
            props["Cor"] = cor.upper()
        api("style.assign_representation_styles", f, shape_representation=rep, styles=[surface(label, color)])
        if props:
            acabamento = api("pset.add_pset", f, product=el, name="CP_Acabamento")
            api("pset.edit_pset", f, pset=acabamento, properties=props)
        walls_by_id[w.source_id] = (w, el)
        contained.append(el)

    for o in model.openings:
        w, wall_el = walls_by_id[o.wall_id]
        ux, uy = math.cos(w.angle), math.sin(w.angle)
        ox, oy = w.x1 + ux * o.offset, w.y1 + uy * o.offset
        depth = w.thickness + 0.10
        op = entity("IfcOpeningElement", f"Vão {o.source_id}", o.source_id, predefined_type="OPENING")
        rep = api("geometry.add_wall_representation", f, context=body, length=o.width,
                  height=o.height, thickness=depth, offset=-depth / 2)
        api("geometry.edit_object_placement", f, product=op, matrix=_matrix(ox, oy, o.sill, w.angle))
        api("geometry.assign_representation", f, product=op, representation=rep)
        api("feature.add_feature", f, feature=op, element=wall_el)

        door = o.kind == "porte"
        shape = f.create_entity("IfcProductDefinitionShape", Representations=[])
        if door:
            fill = entity("IfcDoor", f"Porta {o.source_id}", f"fill-{o.source_id}", predefined_type="DOOR")
            frep = api("geometry.add_door_representation", f, context=body,
                       overall_height=o.height, overall_width=o.width, part_of_product=shape)
            fill.OverallHeight, fill.OverallWidth = o.height, o.width
            pset = {"Pset_DoorCommon": {"Reference": "Porta"}}
            qto = ("Qto_DoorBaseQuantities", {"Width": o.width, "Height": o.height, "Area": o.width * o.height})
        else:
            label = "Janela" if o.kind == "fenetre" else "Vão envidraçado"
            fill = entity("IfcWindow", f"{label} {o.source_id}", f"fill-{o.source_id}", predefined_type="WINDOW")
            frep = api("geometry.add_window_representation", f, context=body,
                       overall_height=o.height, overall_width=o.width, part_of_product=shape)
            fill.OverallHeight, fill.OverallWidth = o.height, o.width
            pset = {"Pset_WindowCommon": {"Reference": label}}
            qto = ("Qto_WindowBaseQuantities", {"Width": o.width, "Height": o.height, "Area": o.width * o.height})
        for aspect in shape.HasShapeAspects:
            for representation in aspect.ShapeRepresentations:
                for i, item in enumerate(representation.Items):
                    finish_kind = "frame"
                    if aspect.Name == "Glazing":
                        finish_kind = "glass"
                    elif door and aspect.Name == "Framing":
                        finish_kind = "door" if i == 0 else "hardware"
                    api("style.assign_item_style", f, item=item, style=surface(*OPENING_PALETTE[finish_kind]))
        shape.Representations = [frep]
        fill.Representation = shape
        finish(fill, _matrix(ox, oy, o.sill, w.angle), None, None, pset,
               qto[0], qto[1], o.source_id)
        api("feature.add_filling", f, opening=op, element=fill)
        contained.append(fill)

    # ---------- Lajes ----------
    for s in model.slabs:
        el = entity("IfcSlab", s.name, s.source_id, predefined_type="FLOOR")
        rep = api("geometry.add_slab_representation", f, context=body, depth=s.thickness,
                  polyline=[tuple(p) for p in s.points])
        props = {"LoadBearing": True}
        finish(el, _matrix(0.0, 0.0, -s.thickness), rep, "concrete", {"Pset_SlabCommon": props},
               "Qto_SlabBaseQuantities",
               {"Depth": s.thickness, "GrossArea": s.area, "GrossVolume": s.area * s.thickness},
               s.source_id)
        if s.elevation_ngf is not None:
            ps = api("pset.add_pset", f, product=el, name="CP_Altimetria")
            api("pset.edit_pset", f, pset=ps, properties={"CotaNGF": float(s.elevation_ngf)})
        contained.append(el)
        pavement = (model.params.get("pavimentos") or {}).get(s.source_id) or {}
        flooring = pavement.get("material")
        if flooring in PAVIMENTOS:
            label, color = PAVIMENTOS[flooring]
            covering = entity("IfcCovering", f"{label} · {s.name}", s.source_id, predefined_type="FLOORING")
            depth = pavement.get("espessura")
            if depth is None:
                vertices, faces, shades = _floor_preview(s.points, flooring in ("ceramica", "porcelanato"), color)
                items = [f.create_entity("IfcPolygonalFaceSet", Closed=False,
                         Coordinates=f.create_entity("IfcCartesianPointList3D", CoordList=points),
                         Faces=[f.create_entity("IfcIndexedPolygonalFace", CoordIndex=[v+1 for v in face])
                                for face in polygons]) for points, polygons in zip(vertices, faces)]
                flooring_rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=body,
                    RepresentationIdentifier="Body", RepresentationType="Tessellation", Items=items)
            else:
                flooring_rep = api("geometry.add_slab_representation", f, context=body, depth=depth,
                                   polyline=[tuple(p) for p in s.points])
                shades = [color]
            for i, (item, shade) in enumerate(zip(flooring_rep.Items, shades), 1):
                style_name = label if len(shades) == 1 else f"{label} · {i}"
                api("style.assign_item_style", f, item=item, style=surface(style_name, shade))
            if flooring not in mats:
                mats[flooring] = api("material.add_material", f, name=label, category="REVESTIMENTO")
            qs = {"GrossArea": s.area, "NetArea": s.area}
            if depth is not None:
                qs["Width"] = depth
            finish(covering, _matrix(0., 0., .001 if depth is None else 0.), flooring_rep, flooring,
                   {"CP_Acabamento": {"Revestimento": label, "EspessuraDefinida": depth is not None}},
                   "Qto_CoveringBaseQuantities", qs, s.source_id)
            f.create_entity("IfcRelCoversBldgElements", GlobalId=stable_guid(*key, "flooring-rel", s.source_id),
                            RelatingBuildingElement=el, RelatedCoverings=[covering])
            contained.append(covering)

    # ---------- Pilares ----------
    for i, c in enumerate(model.columns, 1):
        el = entity("IfcColumn", c.ref or f"Pilar P{i}", c.source_id, predefined_type="COLUMN")
        prof = api("profile.add_parameterized_profile", f, ifc_class="IfcRectangleProfileDef")
        prof.ProfileName = f"{c.dx * 100:.0f}x{c.dy * 100:.0f}"
        prof.XDim, prof.YDim = c.dx, c.dy
        rep = api("geometry.add_profile_representation", f, context=body, profile=prof, depth=c.height)
        finish(el, _matrix(c.cx, c.cy, 0.0), rep, "concrete", {"Pset_ColumnCommon": {"LoadBearing": True}},
               "Qto_ColumnBaseQuantities",
               {"Length": c.height, "CrossSectionArea": c.dx * c.dy, "GrossVolume": c.dx * c.dy * c.height},
               c.source_id)
        contained.append(el)

    # ---------- Vigas ----------
    top = max((w.height for w in model.walls), default=model.params["wall_height"])
    for i, b in enumerate(model.beams, 1):
        el = entity("IfcBeam", f"Viga V{i}", b.source_id, predefined_type="BEAM")
        rep = api("geometry.add_wall_representation", f, context=body, length=b.length,
                  height=b.depth, thickness=b.width, offset=-b.width / 2)
        ang = math.atan2(b.y2 - b.y1, b.x2 - b.x1)
        finish(el, _matrix(b.x1, b.y1, top - b.depth, ang), rep, "concrete",
               {"Pset_BeamCommon": {"LoadBearing": True, "Span": round(b.length, 3)}},
               "Qto_BeamBaseQuantities",
               {"Length": b.length, "CrossSectionArea": b.width * b.depth,
                "GrossVolume": b.length * b.width * b.depth},
               b.source_id)
        contained.append(el)

    # ---------- Sapatas ----------
    for i, ft in enumerate(model.footings, 1):
        label = f"Sapata linear SL{i}" if ft.wall_id else f"Sapata S{i}"
        el = entity("IfcFooting", label, ft.source_id, predefined_type="STRIP_FOOTING" if ft.wall_id else "PAD_FOOTING")
        prof = api("profile.add_parameterized_profile", f, ifc_class="IfcRectangleProfileDef")
        prof.XDim, prof.YDim = ft.dx, ft.dy
        rep = api("geometry.add_profile_representation", f, context=body, profile=prof, depth=ft.depth)
        finish(el, _matrix(ft.cx, ft.cy, -slab_depth - ft.depth, ft.angle), rep, "concrete",
               {"Pset_FootingCommon": {"LoadBearing": True}}, "Qto_FootingBaseQuantities",
               {"Length": ft.dx, "Width": ft.dy, "Height": ft.depth,
                "GrossVolume": ft.dx * ft.dy * ft.depth},
               ft.source_id)
        contained.append(el)

    if contained:
        api("spatial.assign_container", f, products=contained, relating_structure=storey)

    # ---------- Espaços (divisões) ----------
    spaces = []
    for sp in model.spaces:
        el = entity("IfcSpace", sp.name, sp.source_id, predefined_type="INTERNAL")
        el.LongName = sp.name
        rep = api("geometry.add_slab_representation", f, context=body, depth=sp.height,
                  polyline=[tuple(p) for p in sp.points])
        finish(el, _matrix(0.0, 0.0, 0.0), rep, None, {}, "Qto_SpaceBaseQuantities",
               {"NetFloorArea": sp.area, "GrossFloorArea": sp.area, "Height": sp.height}, sp.source_id)
        spaces.append(el)
    if spaces:
        api("aggregate.assign_object", f, products=spaces, relating_object=storey)

    _header(f, project_name, author)
    return f


def _header(f, project_name: str, author: str) -> None:
    try:
        h = f.wrapped_data.header
        h.file_name.name = project_name
        h.file_name.author = (author,)
        h.file_name.organization = ("ConstruPilot",)
        h.file_name.originating_system = "ConstruPilot BIM (IfcOpenShell)"
        h.file_description.description = ("ViewDefinition [ReferenceView]",)
    except Exception:  # noqa: BLE001 — o cabeçalho é informativo; nunca bloqueia a exportação
        pass


def summarize(f) -> dict:
    """Lista dos elementos e totais de quantidades lidos DO PRÓPRIO IFC (não do modelo de origem)."""
    import ifcopenshell.util.element as E  # noqa: PLC0415

    classes = ("IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcFooting", "IfcDoor", "IfcWindow", "IfcSpace", "IfcCovering")
    elements, totals = [], {}
    for cls in classes:
        for el in f.by_type(cls):
            psets = E.get_psets(el)
            qto = next((v for k, v in psets.items() if k.startswith("Qto_")), {})
            origin = psets.get("CP_Origem", {})
            elements.append({"guid": el.GlobalId, "ifc_class": cls, "name": el.Name,
                             "source_id": origin.get("IdOrigem"),
                             **({"finish": psets["CP_Acabamento"]["Revestimento"]} if "Revestimento" in psets.get("CP_Acabamento", {}) else {}),
                             "quantities": {k: v for k, v in qto.items() if k != "id"}})
            t = totals.setdefault(cls, {"count": 0, "volume_m3": 0.0, "area_m2": 0.0, "length_m": 0.0})
            t["count"] += 1
            t["volume_m3"] += float(qto.get("NetVolume") or qto.get("GrossVolume") or 0.0)
            t["area_m2"] += float(qto.get("GrossArea") or qto.get("NetFloorArea") or qto.get("Area") or 0.0)
            if cls in ("IfcWall", "IfcBeam"):
                t["length_m"] += float(qto.get("Length") or 0.0)
    for t in totals.values():
        for k in ("volume_m3", "area_m2", "length_m"):
            t[k] = round(t[k], 3)
    concrete = sum(t["volume_m3"] for c, t in totals.items() if c in ("IfcSlab", "IfcColumn", "IfcBeam", "IfcFooting"))
    concrete += sum(e["quantities"].get("NetVolume", 0.0) for e in elements
                    if e["ifc_class"] == "IfcWall" and _is_load_bearing(f, e["guid"]))
    return {"schema": f.schema_identifier if hasattr(f, "schema_identifier") else f.schema,
            "elements": elements, "totals": totals, "concrete_volume_m3": round(concrete, 3)}


def _is_load_bearing(f, guid: str) -> bool:
    import ifcopenshell.util.element as E  # noqa: PLC0415
    return bool(E.get_psets(f.by_guid(guid)).get("Pset_WallCommon", {}).get("LoadBearing"))


def validate(f) -> list[str]:
    """Erros de conformidade ao esquema IFC (lista vazia = ficheiro válido)."""
    import logging  # noqa: PLC0415

    import ifcopenshell.validate  # noqa: PLC0415

    class _Collect(logging.Handler):
        def __init__(self):
            super().__init__()
            self.msgs: list[str] = []

        def emit(self, record):
            self.msgs.append(record.getMessage())

    log = logging.Logger("construpilot.bim.validate")
    log.propagate = False
    h = _Collect()
    log.addHandler(h)
    # IfcOpenShell enables derived attribute values through a process-wide
    # feature switch during validation. Concurrent summary/download requests
    # must not restore the switch while another model is still being checked.
    with _SCHEMA_VALIDATION_LOCK:
        wrapper = ifcopenshell.ifcopenshell_wrapper
        flag = "use_attribute_value_derived"
        previous = wrapper.get_feature(flag)
        try:
            ifcopenshell.validate.validate(f, log, express_rules=False)
        finally:
            wrapper.set_feature(flag, previous)
            log.removeHandler(h)
    return h.msgs
