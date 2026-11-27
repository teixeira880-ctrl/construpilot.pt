"""Exportação IFC4 do modelo único (IfcOpenShell): a mesma geometria do 3D, dos alçados e das medições.

Conteúdo: terreno → edifício → um IfcBuildingStorey por piso (cota = pavimento acabado); paredes com o seu conjunto
de camadas (IfcMaterialLayerSet), vãos abertos nas paredes e preenchidos com porta ou janela; lajes com os vazios das
escadas; águas e empenas da cobertura; escadas; um IfcSpace por divisão com área, perímetro e acabamentos.

Os GlobalId são determinísticos (processo + classe + identificador do modelo): exportar outra vez mantém-nos.
"""
from __future__ import annotations

import math
import uuid
from typing import Any, Dict, List

import numpy as np

SCHEMA = "IFC4"
_NS = uuid.UUID("7c3f0b52-1d1e-4f0a-9b77-2a9d5c4e6f31")   # espaço de nomes do Estúdio de Projeto


def _guid(*partes) -> str:
    import ifcopenshell.guid  # noqa: PLC0415
    return ifcopenshell.guid.compress(uuid.uuid5(_NS, ":".join(str(p) for p in partes)).hex)


def _matriz(x: float, y: float, z: float, ang: float = 0.0) -> np.ndarray:
    c, s = math.cos(ang), math.sin(ang)
    mt = np.eye(4)
    mt[0][0], mt[0][1], mt[1][0], mt[1][1] = c, -s, s, c
    mt[0][3], mt[1][3], mt[2][3] = x, y, z
    return mt


def _caixa(pts: List[List[float]], z0: float, z1: float):
    """Prisma de base poligonal convexa (4 pontos) entre duas cotas: vértices e triângulos."""
    n = len(pts)
    v = [(p[0], p[1], z0) for p in pts] + [(p[0], p[1], z1) for p in pts]
    f = []
    for i in range(1, n - 1):
        f += [(0, i + 1, i), (n, n + i, n + i + 1)]
    for i in range(n):
        j = (i + 1) % n
        f += [(i, j, n + j), (i, n + j, n + i)]
    return v, f


def construir(m: Dict[str, Any], d: Dict[str, Any], *, chave: str = "estudio", nome_projeto: str = "Projeto ConstruPilot"):
    """Devolve um `ifcopenshell.file` IFC4 com o edifício descrito pelo modelo `m` e pelo seu derivado `d`."""
    import ifcopenshell  # noqa: PLC0415
    import ifcopenshell.api  # noqa: PLC0415

    from engines.estudio_projeto.i18n import parte, tr, tr_chave  # noqa: PLC0415

    api = ifcopenshell.api.run
    f = api("project.create_file", version=SCHEMA)

    def ent(classe, nome, ident, tipo=None):
        el = api("root.create_entity", f, ifc_class=classe, name=tr(nome), predefined_type=tipo)
        el.GlobalId = _guid(chave, classe, ident)
        return el

    projeto = ent("IfcProject", nome_projeto, "projeto")
    api("unit.assign_unit", f, units=[api("unit.add_si_unit", f, unit_type=u) for u in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT", "PLANEANGLEUNIT")])
    modelo3d = api("context.add_context", f, context_type="Model")
    corpo = api("context.add_context", f, context_type="Model", context_identifier="Body", target_view="MODEL_VIEW", parent=modelo3d)
    terreno = ent("IfcSite", "Terreno", "terreno")
    edificio = ent("IfcBuilding", "Edifício", "edificio")
    api("aggregate.assign_object", f, products=[terreno], relating_object=projeto)
    api("aggregate.assign_object", f, products=[edificio], relating_object=terreno)
    for el in (terreno, edificio):
        api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4))

    pisos: Dict[str, Any] = {}
    contidos: Dict[str, List[Any]] = {}
    for k, p in enumerate(d["pisos"]):
        st = ent("IfcBuildingStorey", p["nome"], f"piso-{p['id']}")
        st.Elevation = float(p["z0"])
        api("aggregate.assign_object", f, products=[st], relating_object=edificio)
        api("geometry.edit_object_placement", f, product=st, matrix=_matriz(0.0, 0.0, float(p["z0"])))
        pisos[p["id"]] = st
        contidos[p["id"]] = []
    ultimo = d["pisos"][-1]["id"]

    def props(el, nome, valores):
        valores = {k: v for k, v in valores.items() if v is not None}
        if nome.startswith("CP_"):                 # conjuntos próprios: nomes e textos na língua de saída
            nome, valores = tr_chave(nome), {tr_chave(k): (parte(v) if isinstance(v, str) else v) for k, v in valores.items()}
        else:                                      # conjuntos normalizados (Pset_…): só os textos
            valores = {k: (parte(v) if isinstance(v, str) else v) for k, v in valores.items()}
        if valores:
            ps = api("pset.add_pset", f, product=el, name=nome)
            api("pset.edit_pset", f, pset=ps, properties=valores)

    def qtos(el, nome, valores):
        q = api("pset.add_qto", f, product=el, name=nome)
        api("pset.edit_qto", f, qto=q, properties={k: round(float(v), 4) for k, v in valores.items()})

    # materiais e conjuntos de camadas por tipo de parede
    materiais: Dict[str, Any] = {}

    def material(nome):
        if nome not in materiais:
            materiais[nome] = api("material.add_material", f, name=tr(nome))
        return materiais[nome]

    camadas: Dict[str, Any] = {}
    for tid, t in m["tipos_parede"].items():
        if not any(w["tipo"] == tid for w in m["paredes"]):
            continue
        cj = api("material.add_material_set", f, name=tr(t["nome"]), set_type="IfcMaterialLayerSet")
        for c in t["camadas"]:
            cam = api("material.add_layer", f, layer_set=cj, material=material(c["material"]))
            cam.LayerThickness = float(c["esp_m"])
        camadas[tid] = cj
    betao = material("Betão armado")

    med_par = {w["id"]: w for w in d["medicoes"]["paredes"]}
    # ---------- paredes, vãos, portas e janelas ----------
    for w in d["paredes"]:
        L, t = w["comprimento_m"], w["esp_m"]
        ux, uy = (w["b"][0] - w["a"][0]) / L, (w["b"][1] - w["a"][1]) / L
        ang = math.atan2(uy, ux)
        ea, eb = w.get("ext3d_a", 0.0), w.get("ext3d_b", 0.0)
        tipo = m["tipos_parede"][w["tipo"]]
        el = ent("IfcWall", f"Parede {w['id']}", f"parede-{w['id']}", "SOLIDWALL" if w["exterior"] else "PARTITIONING")
        rep = api("geometry.add_wall_representation", f, context=corpo, length=L + ea + eb, height=w["altura_m"], thickness=t, offset=-t / 2)
        api("geometry.edit_object_placement", f, product=el, matrix=_matriz(w["a"][0] - ux * ea, w["a"][1] - uy * ea, w["z0"], ang))
        api("geometry.assign_representation", f, product=el, representation=rep)
        api("material.assign_material", f, products=[el], type="IfcMaterialLayerSet", material=camadas[w["tipo"]])
        mp = med_par[w["id"]]
        props(el, "Pset_WallCommon", {"IsExternal": bool(w["exterior"]), "Reference": tipo["nome"]})
        props(el, "CP_Estudio", {"IdModelo": w["id"], "TipoParede": tipo["nome"],
                                 "Fachada": (w.get("fachada") or {}).get("nome"), "ComprimentoNoEixo": float(L)})
        qtos(el, "Qto_WallBaseQuantities", {"Length": mp["comprimento_liquido_m"], "Width": t, "Height": w["altura_m"],
                                            "GrossSideArea": mp["area_bruta_m2"], "NetSideArea": mp["area_liquida_m2"], "NetVolume": mp["volume_m3"]})
        contidos[w["piso"]].append(el)
        for v in w["vaos"]:
            if not v["valido"]:
                continue
            larg, alt = v["u1"] - v["u0"], v["z1"] - v["z0"]
            ox, oy, oz = w["a"][0] + ux * v["u0"], w["a"][1] + uy * v["u0"], w["z0"] + v["z0"]
            prof = t + 0.10
            ab = ent("IfcOpeningElement", f"Vão {v['id']}", f"vao-{v['id']}", "OPENING")
            api("geometry.edit_object_placement", f, product=ab, matrix=_matriz(ox, oy, oz, ang))
            api("geometry.assign_representation", f, product=ab, representation=api(
                "geometry.add_wall_representation", f, context=corpo, length=larg, height=alt, thickness=prof, offset=-prof / 2))
            api("feature.add_feature", f, feature=ab, element=el)
            if v["tipo"] in ("porta", "portao"):
                nome = "Portão de garagem" if v["tipo"] == "portao" else "Porta"
                pr = ent("IfcDoor", f"{nome} {v['id']}", f"folha-{v['id']}", "GATE" if v["tipo"] == "portao" else "DOOR")
                rp = api("geometry.add_door_representation", f, context=corpo, overall_height=alt, overall_width=larg)
                props(pr, "Pset_DoorCommon", {"IsExternal": bool(w["exterior"]), "Reference": nome})
                qtos(pr, "Qto_DoorBaseQuantities", {"Width": larg, "Height": alt, "Area": larg * alt})
            else:
                nome = "Janela" if v["tipo"] == "janela" else "Portada envidraçada"
                pr = ent("IfcWindow", f"{nome} {v['id']}", f"folha-{v['id']}", "WINDOW")
                rp = api("geometry.add_window_representation", f, context=corpo, overall_height=alt, overall_width=larg)
                props(pr, "Pset_WindowCommon", {"IsExternal": bool(w["exterior"]), "Reference": nome})
                qtos(pr, "Qto_WindowBaseQuantities", {"Width": larg, "Height": alt, "Area": larg * alt})
            pr.OverallHeight, pr.OverallWidth = float(alt), float(larg)
            api("geometry.edit_object_placement", f, product=pr, matrix=_matriz(ox, oy, oz, ang))
            if rp is not None:
                api("geometry.assign_representation", f, product=pr, representation=rp)
            api("feature.add_filling", f, opening=ab, element=pr)
            contidos[w["piso"]].append(pr)

    # ---------- lajes (com os vazios das escadas) ----------
    med_laje = {x["nome"]: x for x in d["medicoes"]["lajes"]}
    for i, lj in enumerate(d["lajes"]):
        e = lj["z1"] - lj["z0"]
        ultima = lj["nome"] == "Laje de cobertura"
        piso_id = next((p["id"] for p in d["pisos"] if abs(p["z0"] - lj["z1"]) < 1e-6), ultimo)     # laje sob o pavimento desse piso
        for j, anel in enumerate(lj["polys"]):
            el = ent("IfcSlab", lj["nome"], f"laje-{i}-{j}", "ROOF" if ultima else ("BASESLAB" if i == 0 else "FLOOR"))
            api("geometry.edit_object_placement", f, product=el, matrix=_matriz(0.0, 0.0, lj["z0"]))
            api("geometry.assign_representation", f, product=el, representation=api(
                "geometry.add_slab_representation", f, context=corpo, depth=e, polyline=[tuple(p) for p in anel]))
            api("material.assign_material", f, products=[el], material=betao)
            ml = med_laje.get(lj["nome"], {})
            props(el, "Pset_SlabCommon", {"IsExternal": bool(ultima or i == 0), "LoadBearing": True})
            if ml:
                qtos(el, "Qto_SlabBaseQuantities", {"Depth": e, "NetArea": ml["area_m2"], "NetVolume": ml["volume_m3"]})
            for h, furo in enumerate((lj.get("furos") or [[]] * len(lj["polys"]))[j]):
                ab = ent("IfcOpeningElement", "Vazio da escada", f"vazio-{i}-{j}-{h}", "OPENING")
                api("geometry.edit_object_placement", f, product=ab, matrix=_matriz(0.0, 0.0, lj["z0"] - 0.05))
                api("geometry.assign_representation", f, product=ab, representation=api(
                    "geometry.add_slab_representation", f, context=corpo, depth=e + 0.10, polyline=[tuple(p) for p in furo]))
                api("feature.add_feature", f, feature=ab, element=el)
            contidos[piso_id].append(el)

    # ---------- cobertura: águas e empenas ----------
    cob = d["cobertura"]
    if cob["faces"]:
        telhado = ent("IfcRoof", "Cobertura", "cobertura", {"duas_aguas": "GABLE_ROOF", "quatro_aguas": "HIP_ROOF", "uma_agua": "SHED_ROOF"}.get(cob["tipo"], "FREEFORM"))
        api("geometry.edit_object_placement", f, product=telhado, matrix=np.eye(4))
        aguas = []
        for i, face in enumerate(cob["faces"]):
            tris = face.get("tris") or [[face["pts"][0], face["pts"][k], face["pts"][k + 1]] for k in range(1, len(face["pts"]) - 1)]
            verts, idx = [], []
            for t3 in tris:
                idx.append((len(verts), len(verts) + 1, len(verts) + 2))
                verts += [tuple(float(c) for c in p) for p in t3]
            el = ent("IfcSlab", f"Água {i + 1}", f"agua-{i}", "ROOF")
            api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4))
            api("geometry.assign_representation", f, product=el, representation=api(
                "geometry.add_mesh_representation", f, context=corpo, vertices=[verts], faces=[idx]))
            qtos(el, "Qto_SlabBaseQuantities", {"GrossArea": face["area_m2"]})
            props(el, "CP_Estudio", {"InclinacaoGraus": float(m["cobertura"]["inclinacao_graus"]), "AreaEmPlanta": float(face["area_planta_m2"]),
                                     "Acabamento": next((a["material"] for a in d["medicoes"]["acabamentos"] if a["elemento"] == "Cobertura"), None)})
            aguas.append(el)
        api("aggregate.assign_object", f, products=aguas, relating_object=telhado)
        contidos[ultimo].append(telhado)
    for i, emp in enumerate(cob["empenas"]):
        pts = emp["pts"]
        verts = [tuple(float(c) for c in p) for p in pts]
        el = ent("IfcWall", f"Empena {i + 1}", f"empena-{i}", "SOLIDWALL")
        api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4))
        api("geometry.assign_representation", f, product=el, representation=api(
            "geometry.add_mesh_representation", f, context=corpo, vertices=[verts], faces=[[(0, k, k + 1) for k in range(1, len(pts) - 1)]]))
        props(el, "Pset_WallCommon", {"IsExternal": True, "Reference": "Empena"})
        qtos(el, "Qto_WallBaseQuantities", {"NetSideArea": emp["area_m2"]})
        contidos[ultimo].append(el)

    # ---------- escadas ----------
    for e in d.get("escadas") or []:
        verts, idx = [], []
        for peca in e["degraus"] + e["patamares"]:
            v, fc = _caixa(peca["pts"], peca["z"] - e["espelho_m"], peca["z"])
            idx += [tuple(i + len(verts) for i in t3) for t3 in fc]
            verts += v
        el = ent("IfcStair", f"Escada {e['id']}", f"escada-{e['id']}",
                 {"reta": "STRAIGHT_RUN_STAIR", "l": "QUARTER_TURN_STAIR", "u": "HALF_TURN_STAIR"}[e["tipo"]])
        api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4))
        api("geometry.assign_representation", f, product=el, representation=api(
            "geometry.add_mesh_representation", f, context=corpo, vertices=[verts], faces=[idx]))
        props(el, "Pset_StairCommon", {"NumberOfRiser": int(e["n_espelhos"]), "NumberOfTreads": int(e["n_cobertores"]),
                                       "RiserHeight": float(e["espelho_m"]), "TreadLength": float(e["cobertor_m"])})
        props(el, "CP_Estudio", {"Largura": float(e["largura_m"]), "AlturaVencida": float(e["altura_m"]), "Blondel": float(e["blondel_m"])})
        contidos[e["piso"]].append(el)

    # ---------- objetos (mobiliário, sanitários, equipamentos): volume de ocupação ----------
    for o in d.get("objetos") or []:
        classe = o["ifc"] if o["ifc"] in ("IfcFurniture", "IfcSanitaryTerminal", "IfcElectricAppliance", "IfcBuildingElementProxy", "IfcRailing", "IfcColumn") else "IfcBuildingElementProxy"
        el = ent(classe, o["nome"], f"objeto-{o['id']}")
        el.ObjectType = o["tipo"]
        v, fc = _caixa(o["pts"], o["z0"], o["z1"])
        api("geometry.edit_object_placement", f, product=el, matrix=np.eye(4))
        api("geometry.assign_representation", f, product=el, representation=api(
            "geometry.add_mesh_representation", f, context=corpo, vertices=[v], faces=[fc]))
        props(el, "CP_Estudio", {"Categoria": o["categoria"], "Largura": float(o["largura_m"]), "Profundidade": float(o["prof_m"]),
                                 "Altura": float(o["z1"] - o["z0"])})
        contidos[o["piso"]].append(el)

    for pid, lista in contidos.items():
        if lista:
            api("spatial.assign_container", f, products=lista, relating_structure=pisos[pid])

    # ---------- espaços (divisões) ----------
    por_piso: Dict[str, List[Any]] = {}
    for dv in d["divisoes"]:
        el = ent("IfcSpace", dv["nome"], f"espaco-{dv['id']}", "INTERNAL")
        el.LongName = tr(dv["nome"])
        api("geometry.edit_object_placement", f, product=el, matrix=_matriz(0.0, 0.0, dv["z0"]))
        api("geometry.assign_representation", f, product=el, representation=api(
            "geometry.add_slab_representation", f, context=corpo, depth=dv["z1"] - dv["z0"], polyline=[tuple(p) for p in dv["pts"]]))
        qtos(el, "Qto_SpaceBaseQuantities", {"NetFloorArea": dv["area_m2"], "NetPerimeter": dv["perimetro_m"], "Height": dv["z1"] - dv["z0"],
                                             "NetWallArea": dv["area_paredes_m2"]})
        ac = dv["acabamentos"]
        props(el, "CP_Acabamentos", {"Pavimento": ac["pavimento"]["nome"], "Paredes": ac["parede_interior"]["nome"], "Teto": ac["teto"]["nome"]})
        por_piso.setdefault(dv["piso"], []).append(el)
    for pid, lista in por_piso.items():
        api("aggregate.assign_object", f, products=lista, relating_object=pisos[pid])

    try:
        cab = f.wrapped_data.header
        cab.file_name.name = nome_projeto
        cab.file_name.organization = ("ConstruPilot",)
        cab.file_name.originating_system = tr("ConstruPilot — Estúdio de Projeto (IfcOpenShell)")
        cab.file_description.description = ("ViewDefinition [ReferenceView]",)
    except Exception:  # noqa: BLE001 — o cabeçalho é informativo; nunca bloqueia a exportação
        pass
    return f
