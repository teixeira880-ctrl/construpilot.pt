"""Leitura de um IFC externo (Revit, Archicad, Tekla, Allplan… ou o nosso) para um `BuildingModel` por piso.

O cálculo (`analysis.py`) trabalha sobre o `BuildingModel`; este módulo permite-lhe ler modelos de parceiros.
Tudo é deduzido da geometria tridimensional (IfcOpenShell, coordenadas do mundo em metros), não das
propriedades de cada programa, que variam de exportador para exportador:

- paredes, pilares e vigas: caixa orientada em planta (eixo maior = eixo do elemento, menor = espessura/largura);
- lajes: contorno em planta = união das faces projetadas (Shapely), espessura = extensão vertical;
- piso: paredes e pilares cujo centro está entre a cota do piso e a do piso seguinte; vigas e lajes cujo topo
  está à cota do piso seguinte (teto do piso). Se não houver laje no teto, usa-se a laje do pavimento do piso
  como laje tipo e regista-se um aviso.

Os elementos guardam o GlobalId original (`source_id`), para os resultados voltarem ao mesmo elemento no
visualizador e nos programas dos parceiros. Paredes resistentes: `Pset_WallCommon.LoadBearing`; sem essa
propriedade, espessura ≥ 15 cm.
"""
from __future__ import annotations

import math
import os
import tempfile

import numpy as np

from .model import DEFAULTS, Beam, BuildingModel, Column, ModelError, Slab, Wall

WALLS = ("IfcWall", "IfcWallStandardCase")
TOP_TOL = 0.35          # topo de viga/laje a ± desta distância da cota do piso seguinte (m)
MIN_STOREY_H = 2.0      # pisos mais próximos do que isto (ex.: níveis de referência) são agrupados
LOAD_BEARING_MIN_T = 0.15
MAX_ELEMENTS = 20000


def open_ifc(data: bytes):
    """Abre um IFC a partir dos bytes enviados; lança ModelError se não for um ficheiro IFC legível."""
    import ifcopenshell

    if not data or b"ISO-10303-21" not in data[:200]:
        raise ModelError("O ficheiro não é um IFC (STEP ISO-10303-21).")
    fd, path = tempfile.mkstemp(suffix=".ifc")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        try:
            return ifcopenshell.open(path)
        except Exception as e:
            raise ModelError(f"IFC ilegível: {str(e)[:200]}") from e
    finally:
        os.unlink(path)


def _shapes(f, classes) -> dict:
    """GlobalId → (elemento, vértices N×3, triângulos M×3) em coordenadas do mundo (m)."""
    import ifcopenshell.geom

    elements = [e for c in classes for e in f.by_type(c, include_subtypes=False)]
    if len(elements) > MAX_ELEMENTS:
        raise ModelError(f"Modelo demasiado grande para o cálculo em linha ({len(elements)} elementos).")
    out = {}
    if not elements:
        return out
    s = ifcopenshell.geom.settings()
    s.set("use-world-coords", True)
    it = ifcopenshell.geom.iterator(s, f, 1, include=elements)
    if it.initialize():
        while True:
            sh = it.get()
            el = f.by_id(sh.id)
            v = np.array(sh.geometry.verts, dtype=float).reshape(-1, 3)
            t = np.array(sh.geometry.faces, dtype=int).reshape(-1, 3)
            if len(v):
                out[el.GlobalId] = (el, v, t)
            if not it.next():
                break
    return out


def _obb(v):
    """Caixa orientada de área mínima em planta: (centro xy, direção do eixo maior, comprimento, largura, zmin, zmax)."""
    from shapely import MultiPoint

    xy = np.unique(np.round(v[:, :2], 5), axis=0)
    rect = MultiPoint([tuple(p) for p in xy]).minimum_rotated_rectangle
    if rect.geom_type != "Polygon":                        # elemento degenerado (linha ou ponto em planta)
        c = xy.mean(axis=0)
        d = xy - c
        u = d[int(np.argmax((d ** 2).sum(axis=1)))] if len(xy) > 1 else np.array([1.0, 0.0])
        u = u / (np.linalg.norm(u) or 1.0)
        L = float((d @ u).max() - (d @ u).min()) if len(xy) > 1 else 0.0
        return c, u, L, 0.0, float(v[:, 2].min()), float(v[:, 2].max())
    pts = np.array(rect.exterior.coords)[:4]
    e1, e2 = pts[1] - pts[0], pts[2] - pts[1]
    L, W = float(np.linalg.norm(e1)), float(np.linalg.norm(e2))
    u = e1 / L if L >= W else e2 / W
    L, W = max(L, W), min(L, W)
    # Eixos alinhados com x/y quando a diferença é numérica: plantas ortogonais ficam exatas.
    for ax in (np.array([1.0, 0.0]), np.array([0.0, 1.0])):
        if abs(abs(float(u @ ax)) - 1.0) < 1e-6:
            u = ax
    if u[0] < -1e-9 or (abs(u[0]) <= 1e-9 and u[1] < 0):
        u = -u
    return pts.mean(axis=0), u, L, W, float(v[:, 2].min()), float(v[:, 2].max())


def _footprint(v, t):
    """Contorno(s) em planta da união dos triângulos projetados."""
    from shapely.geometry import Polygon
    from shapely.ops import unary_union

    tris = []
    for a, b, c in t:
        p = Polygon([tuple(v[a, :2]), tuple(v[b, :2]), tuple(v[c, :2])])
        if p.area > 1e-6:
            tris.append(p)
    if not tris:
        return []
    u = unary_union(tris).buffer(0.005).buffer(-0.005).simplify(0.01)
    polys = [u] if u.geom_type == "Polygon" else list(getattr(u, "geoms", []))
    return [[(round(x, 4), round(y, 4)) for x, y in list(p.exterior.coords)[:-1]] for p in polys if p.area > 0.5]


def _load_bearing(el, thickness: float) -> bool:
    import ifcopenshell.util.element as ue

    for pset in ("Pset_WallCommon", "Pset_ColumnCommon"):
        val = (ue.get_psets(el).get(pset) or {}).get("LoadBearing")
        if isinstance(val, bool):
            return val
    return thickness >= LOAD_BEARING_MIN_T


def storeys(f) -> list[dict]:
    """Pisos do edifício por cota crescente (m), agrupando níveis com menos de MIN_STOREY_H de diferença."""
    import ifcopenshell.util.placement as up
    import ifcopenshell.util.unit as uu

    scale = uu.calculate_unit_scale(f)
    levels = []
    for st in f.by_type("IfcBuildingStorey"):
        z = None
        if st.ObjectPlacement is not None:
            z = float(up.get_local_placement(st.ObjectPlacement)[2, 3]) * scale
        if z is None and st.Elevation is not None:
            z = float(st.Elevation) * scale
        levels.append({"guid": st.GlobalId, "name": st.Name or st.LongName or "Piso", "elevation": round(z or 0.0, 3)})
    levels.sort(key=lambda s: s["elevation"])
    merged = []
    for lv in levels:
        if merged and lv["elevation"] - merged[-1]["elevation"] < MIN_STOREY_H:
            continue
        merged.append(lv)
    for i, lv in enumerate(merged):
        lv["index"] = i
    return merged


def read(f, storey_index: int | None = None, *, params: dict | None = None) -> tuple[BuildingModel, list[dict]]:
    """→ (modelo do piso escolhido, lista de pisos com contagens). Sem `storey_index`, escolhe o piso com mais
    vigas e pilares (o pórtico mais completo)."""
    lv = storeys(f)
    sh = _shapes(f, (*WALLS, "IfcColumn", "IfcBeam", "IfcSlab"))
    if not sh:
        raise ModelError("O IFC não tem paredes, pilares, vigas nem lajes com geometria.")
    boxes = {g: (el, v, t, _obb(v)) for g, (el, v, t) in sh.items()}
    if not lv:
        lv = [{"guid": None, "name": "Piso 0", "elevation": round(min(b[3][4] for b in boxes.values()), 3), "index": 0}]

    def bounds(i):
        e = lv[i]["elevation"]
        if i + 1 < len(lv):
            return e, lv[i + 1]["elevation"]
        walls_h = [b[3][5] for b in boxes.values() if b[0].is_a() in WALLS + ("IfcColumn",) and b[3][4] >= e - 0.3]
        return e, max(walls_h) if walls_h else e          # último nível sem paredes nem pilares (cobertura): vazio

    def members(i):
        e, e2 = bounds(i)
        sel = {"vert": [], "beam": [], "slab_top": [], "slab_base": []}
        if e2 - e < 1.0:
            return e, e2, sel
        for g, (el, _v, _t, (_c, _u, _L, _W, z0, z1)) in boxes.items():
            cls = el.is_a()
            if cls in WALLS or cls == "IfcColumn":
                if e < (z0 + z1) / 2 < e2:
                    sel["vert"].append(g)
            elif cls == "IfcBeam":
                if abs(z1 - e2) <= TOP_TOL:
                    sel["beam"].append(g)
            elif abs(z1 - e2) <= TOP_TOL:
                sel["slab_top"].append(g)
            elif abs(z1 - e) <= TOP_TOL:
                sel["slab_base"].append(g)
        return e, e2, sel

    summary = []
    for i in range(len(lv)):
        _, _, s = members(i)
        cols = sum(1 for g in s["vert"] if boxes[g][0].is_a() == "IfcColumn")
        summary.append({**lv[i], "columns": cols, "beams": len(s["beam"]),
                        "walls": len(s["vert"]) - cols, "slabs": len(s["slab_top"]) or len(s["slab_base"])})
    if storey_index is None:
        storey_index = max(range(len(lv)), key=lambda k: (summary[k]["columns"] + summary[k]["beams"], -k))
    if not 0 <= storey_index < len(lv):
        raise ModelError(f"Piso {storey_index} inexistente (o IFC tem {len(lv)}).")

    e, e2, s = members(storey_index)
    H = round(e2 - e, 3)
    if H < 1.5:
        raise ModelError("Não foi possível determinar o pé-direito do piso escolhido.")
    p = {**DEFAULTS, **{k: v for k, v in (params or {}).items() if v is not None}, "wall_height": H}
    model = BuildingModel(plan_id="ifc", page_index=storey_index, storey_name=lv[storey_index]["name"], params=p)
    model.ifc_guids = True

    for g in s["vert"]:
        el, _v, _t, (c, u, L, W, _z0, _z1) = boxes[g]
        if el.is_a() == "IfcColumn":
            dx, dy = (L, W) if abs(u[0]) >= abs(u[1]) else (W, L)
            model.columns.append(Column(source_id=g, cx=round(float(c[0]), 4), cy=round(float(c[1]), 4),
                                        dx=round(dx, 4), dy=round(dy, 4), height=H, ref=el.Name or ""))
            continue
        if W <= 0.01 or L <= 0.05:
            continue
        a, b = c - u * L / 2, c + u * L / 2
        model.walls.append(Wall(source_id=g, x1=round(float(a[0]), 4), y1=round(float(a[1]), 4),
                                x2=round(float(b[0]), 4), y2=round(float(b[1]), 4), thickness=round(W, 4),
                                height=H, load_bearing=_load_bearing(el, W)))
    for g in s["beam"]:
        _el, _v, _t, (c, u, L, W, z0, z1) = boxes[g]
        a, b = c - u * L / 2, c + u * L / 2
        model.beams.append(Beam(source_id=g, x1=round(float(a[0]), 4), y1=round(float(a[1]), 4),
                                x2=round(float(b[0]), 4), y2=round(float(b[1]), 4),
                                width=round(W, 4), depth=round(z1 - z0, 4)))
    slabs = s["slab_top"]
    if not slabs and s["slab_base"]:
        slabs = s["slab_base"]
        model.warnings.append({"code": "slab_from_floor", "detail": "Sem laje no teto do piso: a laje do pavimento "
                               "foi usada como laje tipo para as cargas."})
    for g in slabs:
        el, v, t, (*_, z0, z1) = boxes[g]
        for k, pts in enumerate(_footprint(v, t)):
            model.slabs.append(Slab(source_id=g if k == 0 else f"{g}#{k}", name=el.Name or "Laje", points=pts,
                                    thickness=round(z1 - z0, 4), elevation_ngf=None))
    _to_local(model)
    if not model.slabs:
        model.warnings.append({"code": "no_slab", "detail": "Sem lajes no piso: só o peso próprio das vigas é considerado."})
    if not (model.beams or model.columns):
        model.warnings.append({"code": "no_frame", "detail": "O piso escolhido não tem vigas nem pilares."})
    return model, summary



def _to_local(model: BuildingModel) -> None:
    """Desloca o piso para perto de (0, 0): projetos georreferenciados têm coordenadas de centenas de km."""
    xs = [w.x1 for w in model.walls] + [w.x2 for w in model.walls] + [b.x1 for b in model.beams] + \
        [b.x2 for b in model.beams] + [c.cx for c in model.columns] + [p[0] for s in model.slabs for p in s.points]
    ys = [w.y1 for w in model.walls] + [w.y2 for w in model.walls] + [b.y1 for b in model.beams] + \
        [b.y2 for b in model.beams] + [c.cy for c in model.columns] + [p[1] for s in model.slabs for p in s.points]
    if not xs:
        return
    ox, oy = math.floor(min(xs)), math.floor(min(ys))
    model.origin = (ox, oy)
    for e in model.walls + model.beams:
        e.x1, e.x2, e.y1, e.y2 = round(e.x1 - ox, 4), round(e.x2 - ox, 4), round(e.y1 - oy, 4), round(e.y2 - oy, 4)
    for c in model.columns:
        c.cx, c.cy = round(c.cx - ox, 4), round(c.cy - oy, 4)
    for s in model.slabs:
        s.points = [(round(x - ox, 4), round(y - oy, 4)) for x, y in s.points]


STACK_TOL = 0.30        # pilar de um piso superior considerado sobre o pilar de baixo a menos disto (m)


def analyze_storey(f, storey_index: int | None = None, loads: dict | None = None) -> tuple[BuildingModel, list[dict], dict]:
    """Calcula o piso pedido e soma aos seus pilares o esforço normal (ELU) dos pilares empilhados dos pisos de cima.

    Cada piso é um pórtico próprio (vigas do teto + pilares). O esforço normal desce pelos pilares: para cada piso
    acima com pórtico, o N_Ed de cada pilar é transmitido ao pilar do piso de baixo na mesma posição (± 30 cm).
    Um pilar que apoia numa viga (transição) é assinalado: essa carga não é transmitida ao pórtico de baixo.
    """
    from . import analysis as A

    model, summary = read(f, storey_index)
    result = A.analyze(model, loads)
    i = model.page_index
    world = {c.source_id: (c.cx + model.origin[0], c.cy + model.origin[1]) for c in model.columns}
    # Pilares de cada piso acima, de cima para baixo, com o N acumulado.
    carried: list[tuple[float, float, float, str]] = []      # (x, y, N_total, nome do piso de origem)
    above = [k for k in range(i + 1, len(summary)) if summary[k]["columns"]]
    for k in sorted(above, reverse=True):
        try:
            mk, _ = read(f, k)
            rk = A.analyze(mk, loads)
        except (ModelError, A.AnalysisError) as e:
            result["warnings"].append({"code": "upper_storey_failed", "detail": f"Piso {summary[k]['name']}: {e}"})
            continue
        pos = {c.source_id: (c.cx + mk.origin[0], c.cy + mk.origin[1]) for c in mk.columns}
        nxt = []
        for c in rk["columns"]:
            x, y = pos[c["source_id"]]
            n = c["n_ed_kn"] + sum(nc for (cx, cy, nc, _) in carried if math.hypot(cx - x, cy - y) <= STACK_TOL)
            nxt.append((x, y, n, summary[k]["name"]))
        lost = [t for t in carried if not any(math.hypot(t[0] - x, t[1] - y) <= STACK_TOL for x, y, _, _ in nxt)]
        for x, y, n, name in lost:
            result["warnings"].append({"code": "column_transfer", "detail": f"Pilar do piso {name} em ({x:.2f}; {y:.2f}) "
                                       f"sem pilar por baixo: {n:.0f} kN não transmitidos (viga de transição?)."})
        carried = nxt
    for col in result["columns"]:
        x, y = world[col["source_id"]]
        n_above = sum(n for (cx, cy, n, _) in carried if math.hypot(cx - x, cy - y) <= STACK_TOL)
        if n_above > 0:
            own = col["n_ed_kn"]
            col.update(A.check_column(own + n_above, col["b_m"], col["h_m"], col["height_m"], result["params"]))
            col["n_ed_own_kn"], col["n_ed_above_kn"] = round(own, 2), round(n_above, 2)
    if result["columns"]:
        worst = max([b["utilization"] for b in result["beams"]] + [c["utilization"] for c in result["columns"]])
        result["columns"].sort(key=lambda c: -c["utilization"])
        result["max_utilization"], result["status"] = round(worst, 3), A._status(worst)
    result["storeys_above_carried"] = [summary[k]["name"] for k in above]
    return model, summary, result
