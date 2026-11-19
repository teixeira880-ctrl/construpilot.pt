"""Vistas 3D EXATAS da geometria real (motor bet_geo) — base do fotorrealismo e do seu controlo.

Para cada vista (main, side, rear, aerial), com a MESMA câmara:
  * computed_view  → imagem calculada sombreada (instantânea, geometria exata por construção);
  * mask           → máscara para engines.geometry_lock (fundo 0, um tom por face, vãos = 40);
  * render_pbr     → renderização física Mitsuba (sol, céu, materiais) se o motor estiver instalado.

Volumes: fachadas extrudidas do contorno real (e dos pátios); vãos = troços de fachada sem parede ENTRE
paredes lidas (até 9 m); fachada sem nenhuma parede lida fica cega (não se inventam janelas); laje de
cobertura com palas; platibanda na cobertura. Nenhuma forma é simplificada para retângulo.
"""
from __future__ import annotations

import io
import math

import numpy as np
from shapely.geometry import LineString, Point, Polygon
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

from .model import Building

VIEWS = ("main", "side", "rear", "aerial")
FOV = 40.0
GLASS_TONE = 40


# ----------------------------------------------------------------------------- geometria 3D
def faces(b: Building, slab_h: float = 0.25, parapet: float | None = None) -> list[tuple[list, str, tuple]]:
    """[(vértices 3D, tipo, normal exterior)] — tipos: wall, glass, lintel, slab_edge, parapet, roof."""
    H = max(2.4, b.storey_height)
    par = parapet if parapet is not None else float(b.hypotheses.get("parapet_m", 0.5))
    out: list = []
    fp = orient(b.footprint, 1.0)                       # exterior CCW, furos CW → normal exterior = direita do sentido
    ext_walls = [w for w in b.walls if w.exterior]
    zone = unary_union([w.line.buffer(max(w.t / 2, 0.08) + 0.25, cap_style=2) for w in ext_walls]) if ext_walls else None
    glass_top = H - slab_h - 0.10
    for ring in [fp.exterior, *fp.interiors]:
        cs = list(ring.simplify(0.05).coords)
        for (x0, y0), (x1, y1) in zip(cs, cs[1:]):
            L = math.hypot(x1 - x0, y1 - y0)
            if L < 0.05:
                continue
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            nrm = (uy, -ux, 0.0)                         # à direita do sentido do anel orientado = exterior
            edge = LineString([(x0, y0), (x1, y1)])
            cov = []
            if zone is not None:
                inter = edge.intersection(zone)
                for g in getattr(inter, "geoms", [inter]):
                    if g.geom_type == "LineString" and g.length > 0.05:
                        t0, t1 = sorted((edge.project(Point(g.coords[0])), edge.project(Point(g.coords[-1]))))
                        cov.append((t0, t1))
            cov.sort()
            merged = []
            for a, c in cov:
                if merged and a <= merged[-1][1] + 0.05:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], c))
                else:
                    merged.append((a, c))
            if not merged:                               # nenhuma parede lida nesta fachada: cega (não inventar vãos)
                merged = [(0.0, L)]
            pts = [0.0] + [v for ab in merged for v in ab] + [L]
            segs = []
            for i in range(0, len(pts) - 1):
                a, c = pts[i], pts[i + 1]
                if c - a < 0.02:
                    continue
                is_wall = (i % 2 == 1)                   # pts alterna: livre, parede, livre, parede…
                segs.append((a, c, is_wall))

            def P(t, z):
                return (x0 + ux * t, y0 + uy * t, z)
            for a, c, is_wall in segs:
                if is_wall or (c - a) > 9.0 or (c - a) < 0.5:
                    out.append(([P(a, 0), P(c, 0), P(c, H), P(a, H)], "wall", nrm))
                else:
                    out.append(([P(a, 0), P(c, 0), P(c, glass_top), P(a, glass_top)], "glass", nrm))
                    out.append(([P(a, glass_top), P(c, glass_top), P(c, H), P(a, H)], "lintel", nrm))
    # laje de cobertura (com palas): bordo + face superior; platibanda sobre o contorno do edifício
    slab = b.roof_slab
    for poly in getattr(slab, "geoms", [slab]):
        poly = orient(poly, 1.0)
        for ring in [poly.exterior, *poly.interiors]:
            cs = list(ring.simplify(0.05).coords)
            for (x0, y0), (x1, y1) in zip(cs, cs[1:]):
                L = math.hypot(x1 - x0, y1 - y0)
                if L < 0.05:
                    continue
                n = ((y1 - y0) / L, -(x1 - x0) / L, 0.0)
                on_fp = LineString([(x0, y0), (x1, y1)]).within(b.footprint.boundary.buffer(0.05))
                top = H + (par if on_fp and par > 0 else 0.0)
                out.append(([(x0, y0, H - slab_h), (x1, y1, H - slab_h), (x1, y1, top), (x0, y0, top)],
                            "parapet" if top > H else "slab_edge", n))
        out.append(([(x, y, H) for x, y in list(poly.exterior.coords)[:-1]], "roof", (0.0, 0.0, 1.0)))
    return out


# ----------------------------------------------------------------------------- câmara
def camera(b: Building, view: str, width: int, height: int):
    x0, y0, x1, y1 = b.roof_slab.bounds
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    outline = Polygon(b.footprint.exterior)
    notch = outline.envelope.difference(outline)
    if not notch.is_empty and notch.area > 1.0:
        q = notch.representative_point()
        dx, dy = q.x - cx, q.y - cy
    else:
        dx, dy = 0.70, -0.71
    n = math.hypot(dx, dy) or 1.0
    dx, dy = dx / n, dy / n
    for _ in range({"main": 0, "side": 1, "rear": 2, "aerial": 0}.get(view, 0)):
        dx, dy = -dy, dx
    H = max(2.4, b.storey_height)
    diag = math.hypot(x1 - x0, y1 - y0)
    dist = (max(diag, H * 1.6) * 0.52) / math.tan(math.radians(FOV / 2))
    if view == "aerial":
        d = dist * 1.3
        eye = np.array([cx + dx * d * 0.78, cy + dy * d * 0.78, d * 0.62])
        tgt = np.array([cx, cy, 1.5])
    else:
        eye = np.array([cx + dx * dist, cy + dy * dist, 1.6])
        tgt = np.array([cx, cy, H * 0.42])
    return eye, tgt


def _project(eye, tgt, width, height):
    f = tgt - eye
    f = f / np.linalg.norm(f)
    r = np.cross(f, [0.0, 0.0, 1.0])
    r = r / np.linalg.norm(r)
    u = np.cross(r, f)
    fx = (width / 2) / math.tan(math.radians(FOV / 2))      # fov horizontal (como o Mitsuba, fov_axis="x")

    def proj(p):
        v = np.asarray(p, float) - eye
        z = float(v @ f)
        return (width / 2 + fx * float(v @ r) / z, height / 2 - fx * float(v @ u) / z, z)
    return proj


COLORS = {"wall": (236, 233, 226), "lintel": (236, 233, 226), "glass": (58, 70, 80), "slab_edge": (222, 220, 214),
          "parapet": (228, 226, 220), "roof": (150, 148, 142)}


def computed_and_mask(b: Building, view: str, width: int = 1600, height: int = 900) -> tuple[bytes, bytes]:
    """(PNG calculado sombreado, PNG máscara) com a mesma câmara."""
    import cv2

    eye, tgt = camera(b, view, width, height)
    proj = _project(eye, tgt, width, height)
    sun = np.array([-0.45, -0.6, 0.66])
    sun /= np.linalg.norm(sun)
    img = np.zeros((height, width, 3), np.uint8)
    for yy in range(height):                              # céu em gradiente + chão
        t = yy / height
        img[yy, :] = (int(235 - 40 * t), int(222 - 30 * t), int(200 - 20 * t)) if yy < height * 0.55 else (178, 186, 180)
    mask = np.zeros((height, width), np.uint8)
    items = []
    for verts, kind, nrm in faces(b):
        pts = [proj(p) for p in verts]
        if any(p[2] <= 0.1 for p in pts):
            continue
        view_dir = np.mean(np.asarray(verts, float), axis=0) - eye
        if kind != "roof" and float(np.dot(view_dir, nrm)) > 0:   # face de costas para a câmara
            continue
        items.append((max(p[2] for p in pts), pts, kind, nrm))
    items.sort(key=lambda it: -it[0])                     # pintor: do mais longe para o mais perto
    tone = 60
    for _, pts, kind, nrm in items:
        poly = np.array([[p[0], p[1]] for p in pts], np.int32)
        shade = 0.55 + 0.45 * max(0.0, float(np.dot(np.asarray(nrm, float), sun)))
        col = tuple(int(c * shade) for c in COLORS[kind])
        cv2.fillPoly(img, [poly], col[::-1], lineType=cv2.LINE_AA)
        cv2.polylines(img, [poly], True, (60, 60, 60), 1, cv2.LINE_AA)
        if kind == "glass":
            cv2.fillPoly(mask, [poly], GLASS_TONE)
        else:
            tone = 60 + ((tone - 60 + 23) % 190)
            if tone == GLASS_TONE:
                tone += 1
            cv2.fillPoly(mask, [poly], tone)
    ok1, a = cv2.imencode(".png", img)
    ok2, m = cv2.imencode(".png", mask)
    return a.tobytes(), m.tobytes()


def render_pbr(b: Building, view: str, width: int = 1600, height: int = 900, spp: int = 16) -> bytes | None:
    """Renderização física (Mitsuba) com a mesma câmara; None se o motor não estiver instalado."""
    from engines import house_pbr
    if not house_pbr.available():
        return None
    import os
    import tempfile

    from engines.calc_lots import render3d as R3
    mi = house_pbr._mi()
    eye, tgt = camera(b, view, width, height)
    groups: dict[str, list] = {}
    for verts, kind, _n in faces(b):
        groups.setdefault(kind, []).append(verts)
        if kind in ("parapet", "slab_edge"):                       # visível dos dois lados (face interior da platibanda)
            groups[kind].append(list(reversed(verts)))
    mat_of = {"wall": "reboco", "lintel": "reboco", "glass": "vidro", "slab_edge": "reboco", "parapet": "reboco", "roof": "seixo"}
    with tempfile.TemporaryDirectory() as tmp:
        mats = R3._materiais(tmp)
        sc = {"type": "scene", "integrator": {"type": "path", "max_depth": 6},
              "sensor": {"type": "perspective", "fov": FOV,
                         "to_world": mi.ScalarTransform4f().look_at(origin=eye.tolist(), target=tgt.tolist(), up=[0, 0, 1]),
                         "film": {"type": "hdrfilm", "width": width, "height": height, "rfilter": {"type": "gaussian"}},
                         "sampler": {"type": "independent", "sample_count": int(spp)}},
              "ceu": {"type": "sunsky", "sun_direction": [-0.45, -0.6, 0.66], "turbidity": 3.0, "albedo": 0.2}}
        sc.update(mats)
        for kind, polys in groups.items():
            sc["m_" + kind] = {"type": "obj", "face_normals": True,
                               "filename": house_pbr._obj(os.path.join(tmp, kind + ".obj"), polys, (2.0, 2.0)),
                               "bsdf": {"type": "ref", "id": mat_of[kind]}}
        XY = (np.array([1.0, 0, 0]), np.array([0, 1.0, 0]))
        g = 80.0
        sc["m_relva"] = {"type": "obj", "face_normals": True, "bsdf": {"type": "ref", "id": "relva"},
                         "filename": house_pbr._obj(os.path.join(tmp, "relva.obj"),
                                                    [[(-g, -g, -0.02), (g, -g, -0.02), (g, g, -0.02), (-g, g, -0.02)]],
                                                    (2 * g, 2 * g), XY)}
        G = 4000.0                                                     # campo até ao horizonte (sem faixa preta)
        sc["m_campo"] = {"type": "obj", "face_normals": True,
                         "bsdf": {"type": "principled", "base_color": {"type": "rgb", "value": [0.11, 0.15, 0.06]}, "roughness": 1.0},
                         "filename": house_pbr._obj(os.path.join(tmp, "campo.obj"),
                                                    [[(-G, -G, -0.05), (G, -G, -0.05), (G, G, -0.05), (-G, G, -0.05)]], (1.0, 1.0), XY)}
        from shapely import constrained_delaunay_triangles
        paving = [[(x, y, 0.0) for x, y in orient(face).exterior.coords[:-1]]
                  for face in constrained_delaunay_triangles(Polygon(b.footprint.exterior).buffer(1.25, join_style="mitre")).geoms]
        sc["m_passeio"] = {"type": "obj", "face_normals": True, "bsdf": {"type": "ref", "id": "lajeado"},
                           "filename": house_pbr._obj(os.path.join(tmp, "passeio.obj"), paving, (8.0, 8.0), XY)}
        img = mi.render(mi.load_dict(sc), spp=int(spp))
        img = house_pbr._oidn(img, spp)
        rgb = R3._tonemap(img)
    from PIL import Image
    out = io.BytesIO()
    Image.fromarray((np.clip(rgb, 0, 1) * 255).astype(np.uint8)).save(out, "PNG", optimize=True)
    return out.getvalue()


def geometry_key(bd: dict) -> str:
    import hashlib
    import json
    return "geo_" + hashlib.sha1(json.dumps({k: bd.get(k) for k in ("footprint", "covered", "walls", "floor_level",
                                                                       "roof_level")},
                                            sort_keys=True, default=str).encode()).hexdigest()


def quote_flowables(geo: dict, views: dict, meta: dict | None = None, accent: str = "#15803D", lang: str = "pt") -> list:
    """Página « Imagens do projeto — geometria real » para o PDF do orçamento: vista principal grande + 3 vistas,
    com a origem de cada imagem e o resultado do controlo geométrico."""
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Image as RLImage
    from reportlab.platypus import KeepTogether, PageBreak, Paragraph, Spacer, Table, TableStyle

    from engines.pdf_fonts import F

    fr = str(lang or "").lower().startswith("fr")
    acc = colors.HexColor(accent if str(accent).startswith("#") and len(str(accent)) == 7 else "#15803D")
    H1 = ParagraphStyle("g1", fontName=F("Helvetica-Bold"), fontSize=15, leading=19, textColor=acc, spaceAfter=4)
    P = ParagraphStyle("gp", fontName=F("Helvetica"), fontSize=8.5, leading=11.5, textColor=colors.HexColor("#374151"))
    CAP = ParagraphStyle("gc", fontName=F("Helvetica"), fontSize=7.5, leading=9.5, textColor=colors.HexColor("#6b7280"),
                         alignment=1)

    def img(data, w_mm):
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        return RLImage(io.BytesIO(data), width=w_mm * mm, height=w_mm * mm * im.height / im.width)

    meta = meta or {}
    eng = str(meta.get("engine") or "")
    if meta.get("quality") in ("fast", "openai") or eng in ("kling", "nano_banana_3.1", "openai_gpt_image"):
        origin = (f"Photo générée par IA ({'Kling AI' if eng == 'kling' else eng}) à partir de la géométrie réelle, "
                  "contrôlée : volumes, toiture et baies au même endroit que le modèle calculé." if fr else
                  f"Imagem gerada por IA ({'Kling AI' if eng == 'kling' else eng}) a partir da geometria real e verificada: "
                  "volumes, cobertura e vãos no mesmo sítio que o modelo calculado.")
    elif meta.get("quality") == "pbr":
        origin = ("Rendu physique (sans IA) de la géométrie réelle lue sur les plans." if fr else
                  "Renderização física (sem IA) da geometria real lida nas plantas.")
    else:
        origin = ("Vue calculée de la géométrie réelle lue sur les plans." if fr else
                  "Vista calculada da geometria real lida nas plantas.")
    try:
        area = Building.from_dict(geo).footprint.area
        dims = f"{area:,.1f}".replace(",", " ").replace(".", ",")
    except Exception:  # noqa: BLE001
        dims = "-"
    out = [PageBreak(), Paragraph("Images du projet — géométrie réelle" if fr else "Imagens do projeto — geometria real", H1),
           Paragraph((f"Emprise réelle lue sur les plans : {dims} m² (forme exacte, patios déduits). " if fr else
                      f"Implantação real lida nas plantas: {dims} m² (forma exata, pátios descontados). ") + origin, P),
           Spacer(1, 4 * mm)]
    if views.get("main"):
        out.append(KeepTogether([img(views["main"], 180), Paragraph("Perspective principale" if fr else "Perspetiva principal", CAP)]))
    small = [(k, lab) for k, lab in (("side", "Perspetiva lateral"), ("rear", "Perspetiva posterior"), ("aerial", "Vista aérea"))
             if views.get(k)]
    if small:
        row = [[img(views[k], 58) for k, _ in small], [Paragraph(lab, CAP) for _, lab in small]]
        t = Table(row, colWidths=[60 * mm] * len(small))
        t.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER"), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
        out += [Spacer(1, 3 * mm), t]
    return out
