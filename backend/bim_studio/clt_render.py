"""3D views of the ASSEMBLED CLT only: the wall pieces with their openings cut out, the lintels, the floor slab and the
roof strips, exactly as measured for the quantities (same pieces, same numbers). No cladding, no windows, no finishes.

The boxes come from clt_only (walls joined over the lintels, strips of the plates); the image is path-traced by the
render engine of the platform (engines.calc_lots.render3d) with a bare timber material.
"""
from __future__ import annotations

import math

from shapely.geometry import Polygon, box

from bim_studio import clt_only
from bim_studio.clt_economics import EstimateInput, standard_heights

GAP = 0.006            # visual joint between two panels, so each piece reads on the image


def boxes(entrada: dict, parametros: dict, geometria: dict | None = None) -> list[tuple]:
    """[(x0, y0, z0, x1, y1, z1, kind)] in one frame for the whole house. Floors are stacked: each floor starts on the
    slab of the floor below. geometria[floor]["origem_m"] = (dx, dy) aligns sheets that have different origins."""
    body = EstimateInput.model_validate(clt_only.clt_only(entrada))
    body, _notes = standard_heights(body, parametros)
    geometria = geometria or {}
    press = (float(parametros["press_length_m"]["value"]), float(parametros["press_width_m"]["value"]))
    out, z = [], 0.0
    for i, fl in enumerate(body.floors):
        geo = geometria.get(fl.name) or {}
        dx, dy = geo.get("origem_m") or (0.0, 0.0)
        h = float(fl.height_m)
        above = body.floors[i + 1] if i + 1 < len(body.floors) else None
        analysis, bridged, _n, walls = clt_only._wall_pieces(fl)
        for w in walls or []:
            horizontal = abs(w.y2 - w.y1) < abs(w.x2 - w.x1)
            t = w.thickness_m / 2
            a0 = min(w.x1, w.x2) if horizontal else min(w.y1, w.y2)
            length = math.hypot(w.x2 - w.x1, w.y2 - w.y1)
            cuts = sorted(((o.offset_m, o.offset_m + o.width_m, o.sill_m, o.sill_m + o.height_m) for o in w.openings), key=lambda c: c[0])
            if (w.x2 < w.x1) if horizontal else (w.y2 < w.y1):                       # offsets run from (x1, y1)
                cuts = sorted(((length - b, length - a, s, e) for a, b, s, e in cuts), key=lambda c: c[0])

            def seg(u0, u1, z0, z1):
                if u1 - u0 < 1e-4 or z1 - z0 < 1e-4:
                    return
                if horizontal:
                    out.append((a0 + u0 - dx, w.y1 - t - dy, z + z0, a0 + u1 - dx, w.y1 + t - dy, z + z1, "parede"))
                else:
                    out.append((w.x1 - t - dx, a0 + u0 - dy, z + z0, w.x1 + t - dx, a0 + u1 - dy, z + z1, "parede"))
            u = 0.0
            for a, b, s, e in cuts:
                seg(u, a, 0, h)
                seg(a, b, 0, s)                               # under the opening (sill)
                seg(a, b, min(e, h), h)                       # over the opening (lintel part of the same piece)
                u = b
            seg(u, length, 0, h)
        for li in fl.lintels:                                 # lintels that stay separate panels
            if li.ref in bridged or not li.rect_m:
                continue
            x0, y0, x1, y1 = li.rect_m
            out.append((x0 - dx, y0 - dy, z + li.head_m, x1 - dx, y1 - dy, z + h, "lintel"))
        top = z + h
        slab_t = 0.0
        for owner, kinds in ((fl, ("cobertura",)), (above, ("laje",))):
            if owner is None:
                continue
            ogeo = geometria.get(owner.name) or {}
            odx, ody = ogeo.get("origem_placas_m") or ogeo.get("origem_m") or (0.0, 0.0)
            for g in ogeo.get("placas") or []:
                if g["kind"] not in kinds:
                    continue
                t = float(g["thickness_mm"]) / 1000
                poly = Polygon(g["contorno_m"], [v for v in g.get("vazios_m") or []])
                strips, along = clt_only._strips(poly, press[1], press[0])
                for _l, _w, _net, rect in strips:
                    part = poly.intersection(box(*rect))
                    for piece in getattr(part, "geoms", [part]):
                        if not isinstance(piece, Polygon) or piece.area < 1e-4:
                            continue
                        solid = Polygon(piece.exterior) if not piece.interiors else piece
                        rects = clt_only._rectangles(Polygon(solid.exterior), along) if not piece.interiors else _around_holes(piece, along)
                        for rx0, ry0, rx1, ry1 in rects:
                            out.append((rx0 + GAP - odx, ry0 + GAP - ody, top, rx1 - GAP - odx, ry1 - GAP - ody, top + t,
                                        "laje" if g["kind"] == "laje" else "cobertura"))
                if g["kind"] == "laje":
                    slab_t = max(slab_t, t)
        z = top + slab_t
    return out


def _around_holes(piece: Polygon, along: str):
    """Rectangles of a strip that has an opening in it (stair): the strip minus the hole, cut into rectangles."""
    x0, y0, x1, y1 = piece.bounds
    xs = sorted({round(c[0], 4) for ring in [piece.exterior, *piece.interiors] for c in ring.coords})
    ys = sorted({round(c[1], 4) for ring in [piece.exterior, *piece.interiors] for c in ring.coords})
    rects = []
    for a, b in zip(xs, xs[1:]):
        for c, d in zip(ys, ys[1:]):
            cell = box(a, c, b, d)
            if piece.contains(cell.centroid):
                rects.append((a, c, b, d))
    return rects


def views(entrada: dict, parametros: dict, geometria: dict | None = None, largura=1500, altura=900, spp=48) -> list[tuple[str, bytes]]:
    """[(view name, PNG)] of the assembled CLT: two eye-level views and one from above. [] when the render engine is not available."""
    from engines.calc_lots import render3d
    bs = boxes(entrada, parametros, geometria)
    if not bs:
        return []
    x0, x1 = min(b[0] for b in bs), max(b[3] for b in bs)
    y0, y1 = min(b[1] for b in bs), max(b[4] for b in bs)     # the take-off stores y growing to the top of the sheet
    z1 = max(b[5] for b in bs)
    cena = render3d._Cena()
    D = 14.0
    cena.caixa(x0 - D, y0 - D, -0.6, x1 + D, y1 + D, -0.25, "seixo")
    cena.caixa(x0 - 0.25, y0 - 0.25, -0.25, x1 + 0.25, y1 + 0.25, 0.0, "betao")        # the concrete slab the CLT stands on
    for bx0, by0, bz0, bx1, by1, bz1, kind in bs:
        cena.caixa(bx0, by0, bz0, bx1, by1, bz1, "clt" if kind in ("parede", "lintel") else "madeira_deck")
    try:
        return render3d.render({}, {"vistas": [("frente", (0.55, -0.84), 1.6, 1.0), ("tras", (-0.62, 0.78), 1.6, 1.0), ("cima", (0.70, -0.70), None, 1.15)]},
                               largura=largura, altura=altura, spp=spp, cena_pronta=(cena, (x0, x1, y0, y1, 0.0, z1)))
    except Exception:                                          # render engine missing on this server: the dossier goes out without images
        return []
