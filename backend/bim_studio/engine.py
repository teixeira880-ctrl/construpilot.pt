"""Motor BIM do ConstruPilot BIM Studio (IfcOpenShell).

Função pura: ficheiro IFC → elementos classificados, propriedades, quantidades
com origem rastreável e malhas 3D para o visualizador. Não acede à base de dados
nem à rede; é executado num processo isolado (ver ``worker_main.py``).

Regras de medição (secção 4.D da missão):
  1. Quantidades IFC declaradas (IfcElementQuantity / Qto_*) têm prioridade.
  2. Na falta delas, quantidades calculadas a partir da geometria (malha fechada).
  3. Aproximações (caixa envolvente, área/altura…) são marcadas como "estimadas".
  4. Nada disto é "verificado": só um humano valida (estado gerido na API).
  5. Unidades normalizadas para SI (m, m², m³, kg) com o valor original preservado.
  6. Elementos agregadores (ex.: IfcRoof com lajes filhas) não são contados duas vezes.
"""
from __future__ import annotations

import gzip
import json
import logging
import math
import os
import re
from typing import Callable

import numpy as np
import ifcopenshell
import ifcopenshell.geom
import ifcopenshell.util.element as uel
import ifcopenshell.util.unit as uunit

log = logging.getLogger(__name__)

ENGINE_VERSION = "1.0.0"

from bim_studio.constants import CATEGORIES, PRIMARY, QTY_LABELS, UNIT_OF  # noqa: E402,F401

EXCLUDED = ("IfcOpeningElement", "IfcVirtualElement", "IfcFeatureElement", "IfcSpatialZone",
            "IfcAnnotation", "IfcGrid")


def classify(el) -> str:
    c = el.is_a()
    pt = (getattr(el, "PredefinedType", None) or "")
    if el.is_a("IfcWall") or c == "IfcWallStandardCase":
        return "paredes"
    if el.is_a("IfcDoor"):
        return "portas"
    if el.is_a("IfcWindow"):
        return "janelas"
    if el.is_a("IfcSlab"):
        if pt == "ROOF" or _parent_is(el, "IfcRoof"):
            return "coberturas"
        return "lajes"
    if el.is_a("IfcRoof"):
        return "coberturas"
    if el.is_a("IfcColumn"):
        return "pilares"
    if el.is_a("IfcBeam"):
        return "vigas"
    if el.is_a("IfcStair") or el.is_a("IfcStairFlight") or el.is_a("IfcRamp") or el.is_a("IfcRampFlight"):
        return "escadas"
    if el.is_a("IfcCovering"):
        if pt in ("FLOORING",):
            return "pavimentos"
        if pt in ("ROOFING",):
            return "coberturas"
        return "revestimentos"
    if el.is_a("IfcSpace"):
        return "espacos"
    if any(el.is_a(k) for k in ("IfcFooting", "IfcPile", "IfcMember", "IfcPlate",
                                 "IfcReinforcingElement", "IfcBuildingElementProxy")):
        return "estrutura" if not el.is_a("IfcBuildingElementProxy") else "outros"
    if el.is_a("IfcCurtainWall"):
        return "fachadas"
    if el.is_a("IfcRailing"):
        return "guardas"
    if el.is_a("IfcDistributionElement"):
        return "instalacoes"
    if el.is_a("IfcFurnishingElement") or el.is_a("IfcFurniture"):
        return "mobiliario"
    return "outros"


def _parent_is(el, cls: str) -> bool:
    try:
        p = uel.get_aggregate(el)
        return bool(p and p.is_a(cls))
    except Exception:
        return False


def _is_candidate(el) -> bool:
    if el.is_a("IfcSpace"):
        return True
    if not el.is_a("IfcElement"):
        return False
    return not any(el.is_a(x) for x in EXCLUDED)


# ── Unidades ─────────────────────────────────────────────────────────────────
_SI_PREFIX = {"EXA": 1e18, "PETA": 1e15, "TERA": 1e12, "GIGA": 1e9, "MEGA": 1e6, "KILO": 1e3,
              "HECTO": 1e2, "DECA": 1e1, "DECI": 1e-1, "CENTI": 1e-2, "MILLI": 1e-3, "MICRO": 1e-6}
_DIM = {"LENGTHUNIT": 1, "AREAUNIT": 2, "VOLUMEUNIT": 3}


def _unit_scale(unit, unit_type: str) -> float:
    """Fator para converter um valor na unidade dada para SI."""
    if unit is None:
        return 1.0
    try:
        if unit.is_a("IfcSIUnit"):
            base = _SI_PREFIX.get(unit.Prefix or "", 1.0)
            if unit.Name == "GRAM":
                base *= 1e-3
            return base ** _DIM.get(unit_type, 1)
        if unit.is_a("IfcConversionBasedUnit"):
            vc = unit.ConversionFactor.ValueComponent
            v = getattr(vc, "wrappedValue", vc)
            return float(v) * _unit_scale(unit.ConversionFactor.UnitComponent, unit_type)
    except Exception:
        pass
    return 1.0


def project_units(f) -> dict:
    out = {}
    for ut in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT", "MASSUNIT"):
        try:
            out[ut] = float(uunit.calculate_unit_scale(f, unit_type=ut))
        except Exception:
            out[ut] = 1.0
    names = {}
    for ut in ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT"):
        try:
            u = uunit.get_project_unit(f, ut)
            names[ut] = (f"{u.Prefix or ''}{u.Name}" if u is not None and u.is_a("IfcSIUnit")
                         else (getattr(u, "Name", None) or "?"))
        except Exception:
            names[ut] = "?"
    return {"scale": out, "names": names}


# ── Quantidades declaradas (Qto) ─────────────────────────────────────────────
_QTO_MAP_GENERIC = {
    "Length": "length", "Height": "height", "Perimeter": "perimeter", "Depth": "thickness",
    "NetSideArea": "area", "GrossSideArea": "area_gross", "NetArea": "area", "GrossArea": "area_gross",
    "NetFloorArea": "area", "GrossFloorArea": "area_gross", "Area": "area",
    "NetVolume": "volume", "GrossVolume": "volume_gross", "CrossSectionArea": "section_area",
    "OuterSurfaceArea": "surface_area", "NetWeight": "weight", "GrossWeight": "weight",
    "Count": "count", "NetSurfaceArea": "surface_area",
}
_QTYPE = {"IfcQuantityLength": "LENGTHUNIT", "IfcQuantityArea": "AREAUNIT", "IfcQuantityVolume": "VOLUMEUNIT",
          "IfcQuantityWeight": "MASSUNIT", "IfcQuantityCount": None, "IfcQuantityTime": None}


def _declared_quantities(el, cat: str, units: dict) -> list[dict]:
    found: dict[str, dict] = {}
    for rel in getattr(el, "IsDefinedBy", None) or []:
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        qset = rel.RelatingPropertyDefinition
        if not qset.is_a("IfcElementQuantity"):
            continue
        for q in qset.Quantities or []:
            qtype = q.is_a()
            if qtype not in _QTYPE or q.is_a("IfcPhysicalComplexQuantity"):
                continue
            name = q.Name or ""
            key = _QTO_MAP_GENERIC.get(name)
            if name == "Width":
                key = "thickness" if cat in ("paredes", "lajes", "coberturas") else "width"
            if not key:
                continue
            raw = q[3]
            if raw is None or not isinstance(raw, (int, float)) or not math.isfinite(float(raw)):
                continue
            ut = _QTYPE[qtype]
            if ut is None:
                scale = 1.0
            elif getattr(q, "Unit", None) is not None:
                scale = _unit_scale(q.Unit, ut)
            else:
                scale = units["scale"].get(ut, 1.0)
            value = float(raw) * scale
            # NetX prevalece sobre X genérico / Gross
            prio = 2 if name.startswith("Net") else 1
            prev = found.get(key)
            if prev and prev["_prio"] >= prio:
                continue
            found[key] = {
                "key": key, "value": value, "unit": UNIT_OF.get(key, ""), "origin": "declared",
                "source": f"{qset.Name}.{name}", "original": {"value": float(raw), "type": qtype}, "_prio": prio,
            }
    for v in found.values():
        v.pop("_prio", None)
    return list(found.values())


# ── Geometria ────────────────────────────────────────────────────────────────
def _tri_areas_normals(v: np.ndarray, faces: np.ndarray):
    a, b, c = v[faces[:, 0]], v[faces[:, 1]], v[faces[:, 2]]
    cr = np.cross(b - a, c - a)
    n2 = np.linalg.norm(cr, axis=1)
    areas = 0.5 * n2
    with np.errstate(invalid="ignore", divide="ignore"):
        normals = cr / n2[:, None]
    normals = np.nan_to_num(normals)
    return areas, normals


def _signed_volume(v: np.ndarray, faces: np.ndarray) -> float:
    a, b, c = v[faces[:, 0]], v[faces[:, 1]], v[faces[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _is_closed(v: np.ndarray, faces: np.ndarray) -> bool:
    if len(faces) < 4:
        return False
    key = np.round(v, 6)
    _, inv = np.unique(key, axis=0, return_inverse=True)
    f = inv.reshape(-1)[faces]
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    return bool(np.all(counts == 2))


def _geom_quantities(cat: str, v: np.ndarray, faces: np.ndarray) -> list[dict]:
    """Quantidades calculadas/estimadas a partir da malha (coordenadas em metros)."""
    out: list[dict] = []
    if len(faces) == 0:
        return out
    areas, normals = _tri_areas_normals(v, faces)
    mn, mx = v.min(axis=0), v.max(axis=0)
    dims = mx - mn
    closed = _is_closed(v, faces)
    vol = abs(_signed_volume(v, faces))
    if closed and vol > 0:
        out.append(_q("volume", vol, "calculated", "geometria: volume da malha fechada"))
    elif dims.prod() > 0:
        out.append(_q("volume", float(dims.prod()), "estimated",
                      "geometria aberta: volume da caixa envolvente (sobrestima)"))
    out.append(_q("height", float(dims[2]), "calculated", "geometria: extensão vertical"))

    up = areas[normals[:, 2] > 0.9].sum()
    horiz = np.abs(normals[:, 2]) < 0.1
    if cat in ("paredes", "fachadas"):
        side = _dominant_side_area(areas[horiz], normals[horiz])
        if side > 0:
            if _is_straight(areas[horiz], normals[horiz], side):
                out.append(_q("area", side, "calculated", "geometria: área da maior face lateral"))
            else:
                out.append(_q("area", side, "estimated",
                              "parede não retilínea: só a face dominante foi medida (subestima)"))
            if dims[2] > 0:
                out.append(_q("length", side / dims[2], "estimated", "área lateral ÷ altura"))
            if closed and vol > 0:
                out.append(_q("thickness", vol / side, "estimated", "volume ÷ área lateral"))
    elif cat in ("lajes", "coberturas", "pavimentos", "espacos", "revestimentos"):
        if up > 0:
            out.append(_q("area", float(up), "calculated", "geometria: área da face superior"))
        if cat != "espacos" and closed and vol > 0 and up > 0:
            out.append(_q("thickness", vol / float(up), "estimated", "volume ÷ área superior"))
    elif cat in ("pilares",):
        out.append(_q("length", float(dims[2]), "calculated", "geometria: altura do pilar"))
    elif cat in ("vigas", "guardas"):
        out.append(_q("length", float(max(dims[0], dims[1])), "estimated",
                      "geometria: maior dimensão horizontal da caixa envolvente"))
    elif cat in ("portas", "janelas"):
        side = _dominant_side_area(areas[horiz], normals[horiz])
        if side > 0:
            out.append(_q("area", side, "estimated", "geometria: maior face lateral"))
    return out


def _dominant_side_area(areas: np.ndarray, normals: np.ndarray) -> float:
    """Soma das áreas dos triângulos alinhados com a direção horizontal dominante (um só lado)."""
    if len(areas) == 0:
        return 0.0
    ang = np.round(np.degrees(np.arctan2(normals[:, 1], normals[:, 0])) / 2.0) * 2.0  # bins de 2°
    bins: dict[float, float] = {}
    for a, ar in zip(ang, areas):
        bins[float(a)] = bins.get(float(a), 0.0) + float(ar)
    best = max(bins.values())
    return best


def _is_straight(areas: np.ndarray, normals: np.ndarray, side: float) -> bool:
    """False se houver faces laterais significativas noutras direções (parede curva ou em L)."""
    if len(areas) == 0 or side <= 0:
        return True
    ang = np.degrees(np.arctan2(normals[:, 1], normals[:, 0]))
    bins: dict[float, float] = {}
    for a, ar in zip(np.round(ang / 2.0) * 2.0, areas):
        bins[float(a)] = bins.get(float(a), 0.0) + float(ar)
    b = max(bins, key=bins.get)
    other = sum(v for a, v in bins.items()
                if min(abs((a - b + 180) % 360 - 180), abs((a - b) % 360 - 180)) > 4)
    return other <= 0.25 * side


FACE_CATEGORIES = ("paredes", "fachadas", "lajes", "coberturas", "pavimentos")


def face_info(cat: str, v: np.ndarray, faces: np.ndarray) -> dict | None:
    """Faces revestíveis de um elemento (metros).

    Paredes: lados A/B segundo a normal horizontal dominante (eixo ``axis``); área de cada lado
    medida na malha (triângulos alinhados com ±eixo), cota inferior/superior para zonas em altura.
    Lajes/coberturas: face superior (pavimento/cobertura) e inferior (teto).
    """
    if len(faces) == 0 or cat not in FACE_CATEGORIES:
        return None
    areas, normals = _tri_areas_normals(v, faces)
    z0, z1 = float(v[:, 2].min()), float(v[:, 2].max())
    if cat in ("paredes", "fachadas"):
        horiz = np.abs(normals[:, 2]) < 0.1
        if not horiz.any():
            return None
        ang = np.round(np.degrees(np.arctan2(normals[horiz, 1], normals[horiz, 0])) / 2.0) * 2.0
        bins: dict[float, float] = {}
        for a, ar in zip(ang, areas[horiz]):
            bins[float(a)] = bins.get(float(a), 0.0) + float(ar)
        best = max(bins, key=bins.get)
        axis = np.array([math.cos(math.radians(best)), math.sin(math.radians(best))])
        d = normals[:, 0] * axis[0] + normals[:, 1] * axis[1]
        a_area = float(areas[horiz & (d > 0.95)].sum())
        b_area = float(areas[horiz & (d < -0.95)].sum())
        c = v.mean(axis=0)
        return {"kind": "wall", "axis": [round(float(axis[0]), 5), round(float(axis[1]), 5)],
                "center": [round(float(c[0]), 3), round(float(c[1]), 3)],
                "z0": round(z0, 4), "z1": round(z1, 4),
                "sides": {"A": {"area": round(a_area, 4), "label": "interior"},
                          "B": {"area": round(b_area, 4), "label": "interior"}}}
    up = float(areas[normals[:, 2] > 0.9].sum())
    down = float(areas[normals[:, 2] < -0.9].sum())
    top_label = "cobertura" if cat == "coberturas" else "pavimento"
    return {"kind": "slab", "z0": round(z0, 4), "z1": round(z1, 4),
            "sides": {"top": {"area": round(up, 4), "label": top_label},
                      "bottom": {"area": round(down, 4), "label": "teto"}}}


def label_exterior_sides(records: list[dict]) -> None:
    """Paredes exteriores: o lado cuja normal se afasta do centro do edifício é o exterior."""
    walls = [r for r in records if (r.get("faces") or {}).get("kind") == "wall"]
    if not walls:
        return
    cx = sum(r["faces"]["center"][0] for r in walls) / len(walls)
    cy = sum(r["faces"]["center"][1] for r in walls) / len(walls)
    for r in walls:
        ext = (r.get("properties") or {}).get("Pset_WallCommon", {}).get("IsExternal")
        f = r["faces"]
        if ext is not True:
            continue
        out = (f["center"][0] - cx) * f["axis"][0] + (f["center"][1] - cy) * f["axis"][1]
        f["sides"]["A"]["label"] = "exterior" if out >= 0 else "interior"
        f["sides"]["B"]["label"] = "interior" if out >= 0 else "exterior"
        f["exterior_guess"] = True


def _q(key, value, origin, source):
    return {"key": key, "value": float(value), "unit": UNIT_OF.get(key, ""), "origin": origin, "source": source}


def _attr_quantities(el, cat: str, units: dict) -> list[dict]:
    out = [_q("count", 1, "calculated", "1 elemento IFC")]
    if cat in ("portas", "janelas"):
        w, h = getattr(el, "OverallWidth", None), getattr(el, "OverallHeight", None)
        s = units["scale"]["LENGTHUNIT"]
        if w and h:
            out.append(_q("width", w * s, "declared", f"{el.is_a()}.OverallWidth"))
            out.append(_q("height", h * s, "declared", f"{el.is_a()}.OverallHeight"))
            out.append(_q("area", w * h * s * s, "calculated", "OverallWidth × OverallHeight"))
    return out


_ORIGIN_RANK = {"manual": 0, "declared": 1, "calculated": 2, "estimated": 3}


def merge_quantities(*groups: list[dict]) -> dict[str, dict]:
    """Escolhe, por chave, a melhor origem; guarda as alternativas para auditoria."""
    best: dict[str, dict] = {}
    alts: dict[str, list] = {}
    for g in groups:
        for q in g:
            if not (isinstance(q.get("value"), (int, float)) and math.isfinite(q["value"])) or q["value"] < 0:
                continue
            alts.setdefault(q["key"], []).append(q)
            cur = best.get(q["key"])
            if cur is None or _ORIGIN_RANK[q["origin"]] < _ORIGIN_RANK[cur["origin"]]:
                best[q["key"]] = q
    for k, q in best.items():
        q = dict(q)
        q["value"] = round(q["value"], 6)
        q["alternatives"] = [{"value": round(a["value"], 6), "origin": a["origin"], "source": a["source"]}
                             for a in alts[k] if a is not best[k]][:4]
        best[k] = q
    return best


# ── Materiais, propriedades, piso ────────────────────────────────────────────
def _materials(el, units) -> tuple[list[str], float | None]:
    names: list[str] = []
    thickness = None
    try:
        for m in uel.get_materials(el) or []:
            n = getattr(m, "Name", None)
            if n and n not in names:
                names.append(str(n)[:120])
        mat = uel.get_material(el)
        layers = None
        if mat is not None:
            if mat.is_a("IfcMaterialLayerSetUsage"):
                layers = mat.ForLayerSet.MaterialLayers
            elif mat.is_a("IfcMaterialLayerSet"):
                layers = mat.MaterialLayers
        if layers:
            t = sum(float(l.LayerThickness or 0) for l in layers)
            if t > 0:
                thickness = t * units["scale"]["LENGTHUNIT"]
    except Exception:
        pass
    return names[:8], thickness


def _clean_value(v):
    if isinstance(v, (bool, int)):
        return v
    if isinstance(v, float):
        return round(v, 6) if math.isfinite(v) else None
    if isinstance(v, str):
        return v[:200]
    if v is None:
        return None
    return str(v)[:200]


def _properties(el) -> dict:
    out: dict = {}
    try:
        psets = uel.get_psets(el, psets_only=True) or {}
    except Exception:
        return out
    for pname, props in list(psets.items())[:30]:
        clean = {}
        for k, v in list(props.items())[:60]:
            if k == "id":
                continue
            clean[str(k)[:80]] = _clean_value(v)
        if clean:
            out[str(pname)[:80]] = clean
    return out


def _storey_of(el):
    cur, guard = el, 0
    while cur is not None and guard < 10:
        guard += 1
        try:
            c = uel.get_container(cur)
        except Exception:
            c = None
        if c is not None:
            if c.is_a("IfcBuildingStorey"):
                return c
            return None
        try:
            cur = uel.get_aggregate(cur)
        except Exception:
            cur = None
        if cur is not None and cur.is_a("IfcBuildingStorey"):
            return cur
    return None


def _is_container(el) -> bool:
    """True se o elemento agrega sub-elementos com geometria (evita contagem dupla)."""
    for rel in getattr(el, "IsDecomposedBy", None) or []:
        for p in rel.RelatedObjects or []:
            if p.is_a("IfcElement") and getattr(p, "Representation", None):
                return True
    return False


# ── Pipeline principal ───────────────────────────────────────────────────────
class LimitExceeded(Exception):
    pass


class EmptyModel(Exception):
    pass


_INST = re.compile(rb"^\s*#(\d+)\s*=")


def _instancias_ilegiveis(ifc_path: str, f) -> int:
    """Linhas de dados (#id=...) que o leitor não conseguiu interpretar. Conforme a versão, o IfcOpenShell salta
    estas linhas em silêncio — um ficheiro com dados corrompidos não pode passar por modelo válido."""
    ids = set()
    with open(ifc_path, "rb") as fh:
        for line in fh:
            m = _INST.match(line)
            if m:
                ids.add(int(m.group(1)))
    perdidos = 0
    for i in ids:
        try:
            f.by_id(i)
        except Exception:  # noqa: BLE001
            perdidos += 1
    return perdidos


def process(ifc_path: str, out_dir: str, *, max_elements: int = 60000, max_triangles: int = 4_000_000,
            chunk_triangles: int = 250_000, threads: int = 1,
            progress: Callable[[float, str], None] | None = None) -> dict:
    """Processa um IFC e escreve ``result.json.gz`` + ``geom_N.json.gz`` em ``out_dir``."""
    prog = progress or (lambda p, s: None)
    prog(0.02, "a abrir o ficheiro IFC")
    f = ifcopenshell.open(ifc_path)
    schema = f.schema
    if not f.by_type("IfcProject"):
        raise EmptyModel("O ficheiro não contém um IfcProject legível (ficheiro corrompido ou incompleto).")
    perdidos = _instancias_ilegiveis(ifc_path, f)
    if perdidos:
        raise EmptyModel(f"O ficheiro está corrompido: {perdidos} linha(s) de dados ilegíveis. Exporte de novo o IFC "
                         "a partir do programa de origem.")
    units = project_units(f)
    ls = units["scale"]["LENGTHUNIT"]
    warnings: list[str] = []

    storeys = []
    for st in f.by_type("IfcBuildingStorey"):
        elev = st.Elevation
        storeys.append({"gid": st.GlobalId, "name": st.Name or st.LongName or "Piso",
                        "elevation_m": round(float(elev) * ls, 4) if elev is not None else None})
    storeys.sort(key=lambda s: (s["elevation_m"] is None, s["elevation_m"] or 0))

    candidates = [e for e in f.by_type("IfcProduct") if _is_candidate(e)]
    if not candidates:
        raise EmptyModel("O modelo não contém elementos construtivos legíveis.")
    if len(candidates) > max_elements:
        raise LimitExceeded(f"O modelo tem {len(candidates)} elementos (limite {max_elements}).")
    prog(0.08, f"{len(candidates)} elementos encontrados")

    elements: dict[int, dict] = {}
    seen_gid: set[str] = set()
    for el in candidates:
        gid = el.GlobalId
        if gid in seen_gid:
            warnings.append(f"GlobalId duplicado ignorado: {gid} ({el.is_a()})")
            continue
        seen_gid.add(gid)
        cat = classify(el)
        mats, layer_t = _materials(el, units)
        st = _storey_of(el)
        container = _is_container(el)
        type_obj = None
        try:
            type_obj = uel.get_type(el)
        except Exception:
            pass
        rec = {
            "gid": gid, "step_id": el.id(), "ifc_class": el.is_a(),
            "predefined_type": str(getattr(el, "PredefinedType", "") or "") or None,
            "category": cat, "name": (el.Name or "")[:200], "description": (el.Description or "")[:300],
            "type_name": (type_obj.Name if type_obj is not None and type_obj.Name else None),
            "storey_gid": st.GlobalId if st is not None else None,
            "storey": (st.Name if st is not None else None),
            "materials": mats, "properties": _properties(el),
            "counted": not container,
            "container_note": "Quantidades contadas nos sub-elementos (evita contagem dupla)" if container else None,
            "_declared": _declared_quantities(el, cat, units),
            "_attr": _attr_quantities(el, cat, units),
            "_layer_t": layer_t,
            "_geom": [], "has_geometry": False, "bbox": None, "chunk": None, "faces": None,
        }
        elements[el.id()] = rec

    # Geometria (malhas + quantidades calculadas)
    prog(0.15, "a gerar geometria")
    settings = ifcopenshell.geom.settings()
    settings.set("use-world-coords", True)
    settings.set("weld-vertices", True)
    try:
        settings.set("apply-default-materials", True)
    except Exception:
        pass
    geo_targets = [e for e in candidates if e.id() in elements and getattr(e, "Representation", None)]
    chunks: list[dict] = []
    current = {"elements": [], "triangles": 0}
    total_tris = 0
    mesh_skipped = 0
    geom_failed = 0
    if geo_targets:
        it = ifcopenshell.geom.iterator(settings, f, max(1, int(threads)), include=geo_targets)
        done = 0
        if it.initialize():
            while True:
                shape = it.get()
                rec = elements.get(shape.id)
                if rec is not None:
                    try:
                        g = shape.geometry
                        # O iterador de geometria devolve sempre coordenadas em metros (SI).
                        v = np.asarray(g.verts, dtype=np.float64).reshape(-1, 3)
                        faces = np.asarray(g.faces, dtype=np.int64).reshape(-1, 3)
                        rec["_geom"] = _geom_quantities(rec["category"], v, faces)
                        rec["faces"] = face_info(rec["category"], v, faces)
                        rec["has_geometry"] = len(faces) > 0
                        rec["bbox"] = ([round(float(x), 3) for x in v.min(axis=0)] + [round(float(x), 3) for x in v.max(axis=0)]) if len(v) else None
                        if len(faces) and total_tris + len(faces) <= max_triangles:
                            color = _colour(g)
                            current["elements"].append({
                                "gid": rec["gid"], "c": color,
                                "p": np.round(v, 3).reshape(-1).tolist(),
                                "i": faces.reshape(-1).tolist(),
                            })
                            current["triangles"] += len(faces)
                            total_tris += len(faces)
                            rec["chunk"] = len(chunks)
                            if current["triangles"] >= chunk_triangles:
                                chunks.append(current)
                                current = {"elements": [], "triangles": 0}
                        elif len(faces):
                            mesh_skipped += 1
                    except Exception as exc:  # malha inválida: segue sem geometria
                        geom_failed += 1
                        log.debug("geometria falhou para %s: %s", rec["gid"], exc)
                done += 1
                if done % 200 == 0:
                    prog(0.15 + 0.7 * done / max(1, len(geo_targets)), f"geometria {done}/{len(geo_targets)}")
                if not it.next():
                    break
    if current["elements"]:
        chunks.append(current)
    missing_geo = sum(1 for e in geo_targets if not elements[e.id()]["has_geometry"])
    if missing_geo:
        warnings.append(f"{missing_geo} elemento(s) sem geometria válida — quantidades só declaradas.")
    if mesh_skipped:
        warnings.append(f"Limite de visualização atingido: {mesh_skipped} elemento(s) sem malha 3D (quantidades mantidas).")

    prog(0.88, "a consolidar medições")
    out_elements = []
    for rec in elements.values():
        extra = []
        if rec["_layer_t"] and rec["category"] in ("paredes", "lajes", "coberturas", "pavimentos"):
            extra.append(_q("thickness", rec["_layer_t"], "declared", "IfcMaterialLayerSet: soma das camadas"))
        q = merge_quantities(rec.pop("_declared"), extra, rec.pop("_attr"), rec.pop("_geom"))
        rec.pop("_layer_t", None)
        rec["quantities"] = q
        prim = PRIMARY.get(rec["category"], "count")
        rec["primary_key"] = prim
        missing = []
        if prim not in q:
            missing.append(prim)
        if rec["category"] in ("paredes", "lajes", "coberturas") and "thickness" not in q:
            missing.append("thickness")
        if not rec["materials"] and rec["category"] not in ("espacos",):
            missing.append("material")
        rec["missing"] = missing if rec["counted"] else []
        out_elements.append(rec)

    # Geometria → ficheiros
    os.makedirs(out_dir, exist_ok=True)
    for i, ch in enumerate(chunks):
        with gzip.open(os.path.join(out_dir, f"geom_{i}.json.gz"), "wt", encoding="utf-8") as fh:
            json.dump({"chunk": i, "elements": ch["elements"]}, fh, separators=(",", ":"))

    label_exterior_sides(out_elements)
    counts: dict[str, int] = {}
    for e in out_elements:
        counts[e["category"]] = counts.get(e["category"], 0) + 1
    result = {
        "engine_version": ENGINE_VERSION, "ifcopenshell_version": ifcopenshell.version,
        "schema": schema,
        "project": {"name": (f.by_type("IfcProject")[0].Name if f.by_type("IfcProject") else None)},
        "units": units, "storeys": storeys, "elements": out_elements,
        "stats": {"elements": len(out_elements), "by_category": counts, "triangles": total_tris,
                  "chunks": len(chunks), "geometry_failed": geom_failed,
                  "with_missing": sum(1 for e in out_elements if e["missing"])},
        "warnings": warnings[:200],
    }
    with gzip.open(os.path.join(out_dir, "result.json.gz"), "wt", encoding="utf-8") as fh:
        json.dump(result, fh, separators=(",", ":"), default=str)
    prog(0.97, "resultados gravados")
    return result


def _colour(g) -> list[float]:
    try:
        mats = g.materials
        if mats:
            d = mats[0].diffuse
            r, gg, b = (d.r(), d.g(), d.b()) if callable(getattr(d, "r", None)) else tuple(d)[:3]
            return [round(float(r), 3), round(float(gg), 3), round(float(b), 3)]
    except Exception:
        pass
    return [0.75, 0.73, 0.70]
