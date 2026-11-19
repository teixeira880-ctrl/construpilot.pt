"""Leitura da geometria REAL em ficheiros CAD/BIM.

* IFC  — exato: paredes, lajes, espaços e pilares projetados em planta a partir do modelo BIM
         (ifcopenshell, metros). Exterior/interior pela propriedade IsExternal quando existe.
* DXF  — o desenho é renderizado à escala EXATA das unidades do ficheiro ($INSUNITS) e lido pelo
         leitor raster (todas as convenções de layers e tracejados), com a forma do contorno pela IA.
* DWG  — convertido em DXF pelo conversor já configurado na plataforma (engines.dwg_convert).
"""
from __future__ import annotations

import io
import logging
import tempfile

import numpy as np
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .model import Building, Wall

log = logging.getLogger(__name__)
MAX_PX = 7000


# ----------------------------------------------------------------------------- IFC
def _footprint_of(shape) -> Polygon | None:
    v = np.array(shape.geometry.verts, float).reshape(-1, 3)
    f = np.array(shape.geometry.faces, int).reshape(-1, 3)
    tris = []
    for a, b, c in f:
        p = Polygon([v[a, :2], v[b, :2], v[c, :2]])
        if p.area > 1e-6:
            tris.append(p)
    if not tris:
        return None
    u = unary_union(tris).buffer(0.002, join_style=2).buffer(-0.002, join_style=2)
    return u if not u.is_empty else None


def _z(shape) -> tuple[float, float]:
    v = np.array(shape.geometry.verts, float).reshape(-1, 3)
    return float(v[:, 2].min()), float(v[:, 2].max())


def _is_external(el) -> bool | None:
    try:
        import ifcopenshell.util.element as ue
        ps = ue.get_psets(el)
        for name, props in ps.items():
            if "IsExternal" in props:
                return bool(props["IsExternal"])
    except Exception:  # noqa: BLE001
        return None
    return None


def _material(el) -> str:
    try:
        import ifcopenshell.util.element as ue
        m = ue.get_material(el)
        name = (getattr(m, "Name", None) or "") if m else ""
        if not name and m is not None:
            for attr in ("ForLayerSet", "MaterialLayers", "Materials"):
                x = getattr(m, attr, None)
                if x:
                    name = str(x)
                    break
        return "betao" if any(k in name.lower() for k in ("betão", "betao", "concrete", "béton", "beton")) else "alvenaria"
    except Exception:  # noqa: BLE001
        return "alvenaria"


def read_ifc(data: bytes, country: str = "PT", name: str = "") -> Building | None:
    import ifcopenshell
    import ifcopenshell.geom

    try:
        f = ifcopenshell.file.from_string(data.decode("utf-8", "ignore"))
    except Exception:  # noqa: BLE001
        with tempfile.NamedTemporaryFile(suffix=".ifc") as tmp:
            tmp.write(data)
            tmp.flush()
            f = ifcopenshell.open(tmp.name)
    st = ifcopenshell.geom.settings()
    st.set(st.USE_WORLD_COORDS, True)

    def shapes(types):
        out = []
        for t in types:
            try:
                els = f.by_type(t)
            except RuntimeError:
                continue
            for el in els:
                try:
                    out.append((el, ifcopenshell.geom.create_shape(st, el)))
                except Exception:  # noqa: BLE001 — elemento sem geometria
                    continue
        return out

    walls = shapes(["IfcWall", "IfcWallStandardCase", "IfcCurtainWall"])
    if not walls:
        return None
    slabs = shapes(["IfcSlab", "IfcRoof"])
    spaces = shapes(["IfcSpace"])
    # piso de referência = o mais baixo com paredes (por cota da base)
    zmins = sorted(_z(s)[0] for _, s in walls)
    z0 = zmins[0]
    ground = [(el, s) for el, s in walls if _z(s)[0] <= z0 + 0.5]
    wall_polys = [(el, _footprint_of(s)) for el, s in ground]
    wall_polys = [(el, p) for el, p in wall_polys if p is not None]
    zone = [p for _, p in wall_polys]
    zone += [p for p in (_footprint_of(s) for _, s in spaces if _z(s)[0] <= z0 + 0.5) if p is not None]
    floor_slabs = [(el, s) for el, s in slabs if abs(_z(s)[1] - z0) < 0.6]
    zone += [p for p in (_footprint_of(s) for _, s in floor_slabs) if p is not None]
    fp = unary_union(zone).buffer(0.05, join_style=2).buffer(-0.05, join_style=2)
    fp = max(getattr(fp, "geoms", [fp]), key=lambda g: g.area)
    # furos: compartimentos (cobertos por laje) ou pátios (sem laje por cima, > 1 m²)
    all_slabs = unary_union([p for p in (_footprint_of(s) for _, s in slabs) if p is not None]) if slabs else None
    holes = []
    for h in fp.interiors:
        hp = Polygon(h)
        if hp.area > 1.0 and all_slabs is not None and hp.intersection(all_slabs).area < 0.5 * hp.area:
            holes.append(h)
    fp = Polygon(fp.exterior, holes)
    # cobertura = laje mais alta acima do piso
    roofs = [(el, s) for el, s in slabs if _z(s)[1] > z0 + 2.0]
    covered = []
    roof_top = None
    if roofs:
        roof_top = max(_z(s)[1] for _, s in roofs)
        rp = unary_union([p for p in (_footprint_of(s) for _, s in roofs) if p is not None])
        extra = rp.difference(fp).buffer(-0.01, join_style=2).buffer(0.01, join_style=2)
        covered = [g for g in getattr(extra, "geoms", [extra]) if g.area > 0.5]
    # eixos das paredes: máscara a 1 cm/px + leitor raster (qualquer forma de parede)
    from . import raster
    x0, y0, x1, y1 = unary_union([p for _, p in wall_polys]).bounds
    mpp = max(0.01, max(x1 - x0, y1 - y0) / MAX_PX)
    W, H = int((x1 - x0) / mpp) + 4, int((y1 - y0) / mpp) + 4
    import cv2
    mask = np.zeros((H, W), np.uint8)
    for _, p in wall_polys:
        for g in getattr(p, "geoms", [p]):
            pts = np.array([[(x - x0) / mpp + 2, (y1 - y) / mpp + 2] for x, y in g.exterior.coords], np.int32)
            cv2.fillPoly(mask, [pts], 255)
    ws = []
    ext_by_el = [(p, _is_external(el), _material(el)) for el, p in wall_polys]
    ox, oy = fp.bounds[0], fp.bounds[1]
    for a, b, t in raster.segments(mask, mpp):
        ax_, ay_ = a[0] * mpp + x0 - 2 * mpp, y1 - (a[1] - 2) * mpp
        bx_, by_ = b[0] * mpp + x0 - 2 * mpp, y1 - (b[1] - 2) * mpp
        from shapely.geometry import LineString
        ln = LineString([(ax_, ay_), (bx_, by_)])
        if ln.length < 0.45:
            continue
        host = max(ext_by_el, key=lambda e: e[0].intersection(ln.buffer(0.02)).area)
        ext = host[1] if host[1] is not None else (ln.distance(fp.exterior) < 0.35)
        ws.append(Wall((round(ax_ - ox, 3), round(ay_ - oy, 3)), (round(bx_ - ox, 3), round(by_ - oy, 3)),
                       round(min(max(t, 0.08), 0.60), 3), host[2], bool(ext), source="IFC"))
    from shapely.affinity import translate
    fp_m = translate(fp, -ox, -oy)
    b = Building(footprint=fp_m, covered=[translate(c, -ox, -oy) for c in covered], walls=ws, country=country,
                 sources=[f"modelo IFC {name}".strip()])
    b.floor_level = round(z0, 3)
    if roof_top is not None and 2.4 <= roof_top - z0 <= 6.5:
        b.roof_level = round(roof_top, 3)
    storeys = sorted({round(_z(s)[0], 1) for _, s in walls})
    b.storeys = max(1, len([z for i, z in enumerate(storeys) if i == 0 or z - storeys[i - 1] > 2.0]))
    b.checks = [{"item": "área de construção (contorno lido)", "valor": round(fp_m.area, 2), "unidade": "m²",
                 "metodo": "modelo IFC: paredes + espaços + laje do piso, projetados em planta (exato)"},
                {"item": "comprimento total de paredes lidas", "valor": round(sum(w.length for w in ws), 2), "unidade": "m",
                 "metodo": f"{len(wall_polys)} IfcWall do piso de referência"}]
    if spaces:
        sp = sum(p.area for p in (_footprint_of(s) for _, s in spaces if _z(s)[0] <= z0 + 0.5) if p is not None)
        if sp > 0:
            ratio = sp / fp_m.area
            b.checks.append({"item": "área útil dos espaços IFC (2.ª fonte)", "valor": round(sp, 2), "unidade": "m²",
                             "metodo": f"{ratio * 100:.0f} % da área de construção (esperado 70–95 %)".replace(".", ","),
                             "ok": 0.70 <= ratio <= 0.97})
    b.hypotheses["_reader"] = "ifc"
    return b


# ----------------------------------------------------------------------------- DXF
def _dxf_units_to_m(doc) -> float:
    import ezdxf.units as U

    u = int(doc.header.get("$INSUNITS", 0) or 0)
    if u:
        try:
            return U.conversion_factor(u, U.M)
        except Exception:  # noqa: BLE001
            pass
    return 0.0


def render_dxf(data: bytes):
    """DXF → (imagem cinzenta, metros por píxel exato)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf import bbox
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    with tempfile.NamedTemporaryFile(suffix=".dxf") as tmp:
        tmp.write(data)
        tmp.flush()
        from ezdxf import recover
        doc, _aud = recover.readfile(tmp.name)
    msp = doc.modelspace()
    ext = bbox.extents(msp, fast=True)
    if not ext.has_data:
        return None, None
    (x0, y0, _), (x1, y1, _) = ext.extmin, ext.extmax
    k = _dxf_units_to_m(doc)
    if not k:                                           # sem unidades: mm se o desenho for "grande", senão metros
        k = 0.001 if max(x1 - x0, y1 - y0) > 500 else 1.0
    span_m = max(x1 - x0, y1 - y0) * k
    mpp = max(0.01, span_m / MAX_PX)
    Wpx, Hpx = int((x1 - x0) * k / mpp) + 1, int((y1 - y0) * k / mpp) + 1
    dpi = 100
    fig = plt.figure(figsize=(Wpx / dpi, Hpx / dpi), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_axis_off()
    cfg = Configuration(color_policy=ColorPolicy.BLACK, background_policy=BackgroundPolicy.WHITE)
    Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(msp, finalize=False)
    ax.set_xlim(x0, x1)
    ax.set_ylim(y0, y1)
    ax.set_aspect("auto")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, facecolor="white")
    plt.close(fig)
    import cv2
    img = cv2.imdecode(np.frombuffer(buf.getvalue(), np.uint8), cv2.IMREAD_GRAYSCALE)
    real_mpp = (x1 - x0) * k / img.shape[1]
    return img, real_mpp


async def read_dxf(data: bytes, *, llm=None, country: str = "PT", name: str = "") -> Building | None:
    from . import raster

    img, mpp = render_dxf(data)
    if img is None:
        return None
    b = await raster.read(None, image=img, m_per_px=mpp, llm=llm, country=country, name=name)
    if b is not None:
        b.sources = [f"desenho DXF {name} (escala exata das unidades do ficheiro)".replace("  ", " ")]
        b.hypotheses["_reader"] = "dxf"
    return b


async def read_dwg(data: bytes, *, llm=None, country: str = "PT", name: str = "", user_id=None) -> Building | None:
    from engines.dwg_convert import dwg_to_dxf

    from .sources import cached_dxf, remember_dxf

    dxf = cached_dxf(data)
    if dxf is None:
        dxf = await dwg_to_dxf(data, name or "plan.dwg", user_id=user_id)
        remember_dxf(data, dxf)
    b = await read_dxf(dxf, llm=llm, country=country, name=name)
    if b is not None:
        b.sources = [f"desenho DWG {name} (convertido em DXF, escala exata)".replace("  ", " ")]
    return b
