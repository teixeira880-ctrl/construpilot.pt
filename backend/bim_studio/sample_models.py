"""Gerador de modelos IFC sintéticos para testes e demonstração do BIM Studio.

Origem e licença: modelos 100 % gerados por este código (ConstruPilot Portugal),
sem qualquer ficheiro de terceiros. Podem ser usados livremente em testes.

Os valores esperados (áreas, volumes, contagens) são conhecidos por construção,
o que permite verificar o motor de medições contra números exatos.
"""
from __future__ import annotations

import numpy as np
import ifcopenshell
import ifcopenshell.api
import ifcopenshell.api.root
import ifcopenshell.api.unit
import ifcopenshell.api.context
import ifcopenshell.api.project
import ifcopenshell.api.aggregate
import ifcopenshell.api.spatial
import ifcopenshell.api.geometry
import ifcopenshell.api.pset
import ifcopenshell.api.material
import ifcopenshell.api.feature


def _matrix(x=0.0, y=0.0, z=0.0, rot_z_deg=0.0) -> np.ndarray:
    m = np.eye(4)
    a = np.radians(rot_z_deg)
    m[0, 0], m[0, 1], m[1, 0], m[1, 1] = np.cos(a), -np.sin(a), np.sin(a), np.cos(a)
    m[0, 3], m[1, 3], m[2, 3] = x, y, z
    return m


class _Builder:
    def __init__(self, units: str = "mm", schema: str = "IFC4"):
        self.f = ifcopenshell.api.project.create_file(version=schema)
        f = self.f
        if schema == "IFC2X3":  # IFC2X3 exige OwnerHistory em todas as entidades
            from ifcopenshell.api import owner as api_owner
            from ifcopenshell.api.owner import settings as owner_settings
            person = api_owner.add_person(f, identification="CP", family_name="ConstruPilot")
            org = api_owner.add_organisation(f, identification="CP", name="ConstruPilot Portugal")
            user = api_owner.add_person_and_organisation(f, person=person, organisation=org)
            app = api_owner.add_application(f)
            owner_settings.get_user = lambda _f: user
            owner_settings.get_application = lambda _f: app
        self.project = ifcopenshell.api.root.create_entity(f, ifc_class="IfcProject", name="Moradia de teste")
        if units == "mm":
            length = ifcopenshell.api.unit.add_si_unit(f, unit_type="LENGTHUNIT", prefix="MILLI")
            self.s = 1000.0  # valores em mm
        else:
            length = ifcopenshell.api.unit.add_si_unit(f, unit_type="LENGTHUNIT")
            self.s = 1.0
        area = ifcopenshell.api.unit.add_si_unit(f, unit_type="AREAUNIT")
        volume = ifcopenshell.api.unit.add_si_unit(f, unit_type="VOLUMEUNIT")
        ifcopenshell.api.unit.assign_unit(f, units=[length, area, volume])
        model = ifcopenshell.api.context.add_context(f, context_type="Model")
        self.body = ifcopenshell.api.context.add_context(
            f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=model)
        self.site = ifcopenshell.api.root.create_entity(f, ifc_class="IfcSite", name="Terreno")
        self.building = ifcopenshell.api.root.create_entity(f, ifc_class="IfcBuilding", name="Moradia")
        ifcopenshell.api.aggregate.assign_object(f, relating_object=self.project, products=[self.site])
        ifcopenshell.api.aggregate.assign_object(f, relating_object=self.site, products=[self.building])
        self.storeys: list = []
        self.materials: dict = {}

    def storey(self, name: str, elevation_m: float):
        st = ifcopenshell.api.root.create_entity(self.f, ifc_class="IfcBuildingStorey", name=name)
        st.Elevation = elevation_m * self.s
        ifcopenshell.api.aggregate.assign_object(self.f, relating_object=self.building, products=[st])
        ifcopenshell.api.geometry.edit_object_placement(self.f, product=st, matrix=_matrix(z=elevation_m))
        self.storeys.append(st)
        return st

    def material(self, name: str, category: str = ""):
        if name not in self.materials:
            kw = {"category": category} if self.f.schema != "IFC2X3" else {}
            self.materials[name] = ifcopenshell.api.material.add_material(self.f, name=name, **kw)
        return self.materials[name]

    def _place(self, el, storey, x, y, z, rot=0.0):
        s = self.s
        ifcopenshell.api.geometry.edit_object_placement(self.f, product=el, matrix=_matrix(x, y, z, rot))
        ifcopenshell.api.spatial.assign_container(self.f, relating_structure=storey, products=[el])

    def wall(self, storey, name, x, y, z, length, height, thickness, rot=0.0, qto=True, material="Bloco de betão"):
        s = self.s
        el = ifcopenshell.api.root.create_entity(self.f, ifc_class="IfcWall", name=name, predefined_type="SOLIDWALL")
        rep = ifcopenshell.api.geometry.add_wall_representation(
            self.f, context=self.body, length=length, height=height, thickness=thickness)
        ifcopenshell.api.geometry.assign_representation(self.f, product=el, representation=rep)
        self._place(el, storey, x, y, z, rot)
        ifcopenshell.api.material.assign_material(self.f, products=[el], material=self.material(material, "concrete"))
        ps = ifcopenshell.api.pset.add_pset(self.f, product=el, name="Pset_WallCommon")
        ifcopenshell.api.pset.edit_pset(self.f, pset=ps, properties={
            "IsExternal": thickness >= 0.2, "LoadBearing": thickness >= 0.2, "FireRating": "EI60"})
        if qto:
            q = ifcopenshell.api.pset.add_qto(self.f, product=el, name="Qto_WallBaseQuantities")
            ifcopenshell.api.pset.edit_qto(self.f, qto=q, properties={
                "Length": length * s, "Width": thickness * s, "Height": height * s,
                "NetSideArea": length * height, "NetVolume": length * height * thickness,
            })
        return el

    def slab(self, storey, name, x, y, z, w, d, depth, predefined="FLOOR", qto=True, material="Betão C25/30"):
        s = self.s
        el = ifcopenshell.api.root.create_entity(self.f, ifc_class="IfcSlab", name=name, predefined_type=predefined)
        rep = ifcopenshell.api.geometry.add_slab_representation(
            self.f, context=self.body, depth=depth,
            polyline=[(0, 0), (w, 0), (w, d), (0, d), (0, 0)])
        ifcopenshell.api.geometry.assign_representation(self.f, product=el, representation=rep)
        self._place(el, storey, x, y, z)
        ifcopenshell.api.material.assign_material(self.f, products=[el], material=self.material(material, "concrete"))
        if qto:
            q = ifcopenshell.api.pset.add_qto(self.f, product=el, name="Qto_SlabBaseQuantities")
            ifcopenshell.api.pset.edit_qto(self.f, qto=q, properties={
                "Depth": depth * s, "NetArea": w * d, "NetVolume": w * d * depth})
        return el

    def linear(self, storey, ifc_class, name, x, y, z, b, h, length, vertical: bool, material="Betão C25/30"):
        s = self.s
        el = ifcopenshell.api.root.create_entity(self.f, ifc_class=ifc_class, name=name)
        f = self.f
        profile = f.create_entity("IfcRectangleProfileDef", ProfileType="AREA", XDim=b * s, YDim=h * s)
        origin = f.create_entity("IfcCartesianPoint", Coordinates=(0.0, 0.0, 0.0))
        if vertical:
            pos = f.create_entity("IfcAxis2Placement3D", Location=origin)
        else:  # extrusão ao longo do eixo X
            pos = f.create_entity("IfcAxis2Placement3D", Location=origin,
                                  Axis=f.create_entity("IfcDirection", DirectionRatios=(1.0, 0.0, 0.0)),
                                  RefDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 1.0, 0.0)))
        solid = f.create_entity("IfcExtrudedAreaSolid", SweptArea=profile, Position=pos,
                                ExtrudedDirection=f.create_entity("IfcDirection", DirectionRatios=(0.0, 0.0, 1.0)),
                                Depth=length * s)
        rep = f.create_entity("IfcShapeRepresentation", ContextOfItems=self.body,
                              RepresentationIdentifier="Body", RepresentationType="SweptSolid", Items=[solid])
        ifcopenshell.api.geometry.assign_representation(self.f, product=el, representation=rep)
        self._place(el, storey, x, y, z)
        ifcopenshell.api.material.assign_material(self.f, products=[el], material=self.material(material, "concrete"))
        return el

    def opening_element(self, storey, ifc_class, name, x, y, z, width, height, qto=True):
        s = self.s
        el = ifcopenshell.api.root.create_entity(self.f, ifc_class=ifc_class, name=name)
        el.OverallWidth = width * s
        el.OverallHeight = height * s
        # Geometria simplificada (caixa) — suficiente para visualização e testes.
        rep = ifcopenshell.api.geometry.add_wall_representation(
            self.f, context=self.body, length=width, height=height, thickness=0.06)
        ifcopenshell.api.geometry.assign_representation(self.f, product=el, representation=rep)
        self._place(el, storey, x, y, z)
        if qto:
            qn = "Qto_DoorBaseQuantities" if ifc_class == "IfcDoor" else "Qto_WindowBaseQuantities"
            q = ifcopenshell.api.pset.add_qto(self.f, product=el, name=qn)
            ifcopenshell.api.pset.edit_qto(self.f, qto=q, properties={
                "Width": width * s, "Height": height * s, "Area": width * height})
        return el

    def space(self, storey, name, x, y, z, w, d, h):
        s = self.s
        el = ifcopenshell.api.root.create_entity(self.f, ifc_class="IfcSpace", name=name)
        el.LongName = name
        rep = ifcopenshell.api.geometry.add_slab_representation(
            self.f, context=self.body, depth=h,
            polyline=[(0, 0), (w, 0), (w, d), (0, d), (0, 0)])
        ifcopenshell.api.geometry.assign_representation(self.f, product=el, representation=rep)
        ifcopenshell.api.geometry.edit_object_placement(self.f, product=el, matrix=_matrix(x, y, z))
        ifcopenshell.api.aggregate.assign_object(self.f, relating_object=storey, products=[el])
        q = ifcopenshell.api.pset.add_qto(self.f, product=el, name="Qto_SpaceBaseQuantities")
        ifcopenshell.api.pset.edit_qto(self.f, qto=q, properties={"NetFloorArea": w * d})
        return el


def small_house(units: str = "mm", schema: str = "IFC4") -> ifcopenshell.file:
    """Moradia de 2 pisos, 10 m × 8 m. Valores esperados em `SMALL_HOUSE_EXPECTED`."""
    b = _Builder(units=units, schema=schema)
    r0 = b.storey("Piso 0", 0.0)
    r1 = b.storey("Piso 1", 3.0)
    b.slab(r0, "Laje térrea", 0, 0, -0.2, 10, 8, 0.2, "BASESLAB")
    # 4 paredes exteriores com quantidades declaradas (Qto)
    b.wall(r0, "Parede Norte", 0, 8, 0, 10, 2.8, 0.2)
    b.wall(r0, "Parede Sul", 0, 0, 0, 10, 2.8, 0.2)
    b.wall(r0, "Parede Este", 10, 0, 0, 8, 2.8, 0.2, rot=90)
    b.wall(r0, "Parede Oeste", 0, 0, 0, 8, 2.8, 0.2, rot=90)
    # 1 parede interior SEM quantidades declaradas → tem de ser calculada pela geometria
    b.wall(r0, "Divisória interior", 0, 4, 0, 5, 2.8, 0.1, qto=False, material="Gesso cartonado")
    b.opening_element(r0, "IfcDoor", "Porta de entrada", 4, 0, 0, 0.9, 2.1)
    b.opening_element(r0, "IfcWindow", "Janela sala", 7, 0, 1.0, 1.2, 1.2)
    b.opening_element(r0, "IfcWindow", "Janela cozinha", 2, 8, 1.0, 1.0, 1.2, qto=False)
    b.linear(r0, "IfcColumn", "Pilar P1", 5, 4, 0, 0.3, 0.3, 2.8, vertical=True)
    b.linear(r0, "IfcBeam", "Viga V1", 0, 4, 2.8, 0.2, 0.4, 10, vertical=False)
    b.space(r0, "Sala", 0, 0, 0, 5, 4, 2.8)
    # Piso 1: laje e cobertura agregada (IfcRoof → IfcSlab ROOF)
    b.slab(r1, "Laje piso 1", 0, 0, 0, 10, 8, 0.2, "FLOOR")
    roof = ifcopenshell.api.root.create_entity(b.f, ifc_class="IfcRoof", name="Cobertura", predefined_type="FLAT_ROOF")
    b._place(roof, r1, 0, 0, 0)
    # Elemento sem geometria nem quantidades (dados em falta propositados)
    proxy = ifcopenshell.api.root.create_entity(b.f, ifc_class="IfcBuildingElementProxy", name="Elemento sem dados")
    ifcopenshell.api.spatial.assign_container(b.f, relating_structure=r1, products=[proxy])
    roof_slab = b.slab(r1, "Laje de cobertura", 0, 0, 2.8, 10, 8, 0.25, "ROOF", qto=False)
    ifcopenshell.api.spatial.unassign_container(b.f, products=[roof_slab])
    ifcopenshell.api.aggregate.assign_object(b.f, relating_object=roof, products=[roof_slab])
    return b.f


SMALL_HOUSE_EXPECTED = {
    "counts": {"paredes": 5, "portas": 1, "janelas": 2, "lajes": 2, "pilares": 1, "vigas": 1,
               "coberturas": 2, "espacos": 1, "outros": 1},
    "wall_north_area_m2": 28.0,
    "wall_north_volume_m3": 5.6,
    "interior_wall_volume_m3": 5 * 2.8 * 0.1,
    "slab_ground_area_m2": 80.0,
    "roof_slab_volume_m3": 10 * 8 * 0.25,
    "column_volume_m3": 0.3 * 0.3 * 2.8,
    "beam_volume_m3": 0.2 * 0.4 * 10,
    "space_area_m2": 20.0,
}


def large_model(n_walls: int = 1500, units: str = "m") -> ifcopenshell.file:
    """Modelo grande sintético (muitas paredes repartidas por pisos) para testes de carga."""
    b = _Builder(units=units)
    floors = max(1, n_walls // 300)
    storeys = [b.storey(f"Piso {i}", 3.0 * i) for i in range(floors)]
    for i in range(n_walls):
        st = storeys[i % floors]
        b.wall(st, f"Parede {i}", (i % 50) * 1.5, (i // 50) % 40 * 1.5, 3.0 * (i % floors),
               1.2, 2.7, 0.15, qto=(i % 3 != 0))
    return b.f


def write(model: ifcopenshell.file, path: str) -> str:
    model.write(path)
    return path


if __name__ == "__main__":  # pragma: no cover
    import sys
    write(small_house(), sys.argv[1] if len(sys.argv) > 1 else "moradia_teste.ifc")
