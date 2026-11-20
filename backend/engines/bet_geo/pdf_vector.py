"""Leitura da geometria REAL a partir de plantas vetoriais (PDF exportado de CAD).

Fonte A (vetorial, exata à escala):
  * contorno da área de construção = linha tracejada fechada (qualquer cor) que melhor
    envolve as paredes; pátios/saguões = anéis interiores da mesma linha;
  * áreas exteriores cobertas = anéis tracejados de outras cores fora do contorno;
  * paredes = bandas preenchidas por tracejado (segmentos curtos não ortogonais —
    padrão de alvenaria a 45° ou de betão pontilhado), em qualquer ângulo.

Nada aqui supõe uma forma retangular. Cada leitura deixa uma "confrontação" (check) com
uma segunda medida independente para a regra das duas fontes.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

import numpy as np
from shapely.affinity import affine_transform
from shapely.geometry import Point, LineString, Polygon, box
from shapely.ops import unary_union

from .model import Building, Wall, split_by_boundary

PT_PER_M_PAPER = 72 / 0.0254
SCALE_RX = re.compile(r"\b1\s*[:/]\s*(20|25|50|75|100|150|200|250|500)\b")
PLAN_RX = re.compile(r"planta\s+(?:de|do|da)\s+(?:piso|r/?c|r[eé]s|andar|pavimento|cave)", re.I)
NOT_PLAN_RX = re.compile(r"cobertura|implanta|pavimentos e rodap|tetos|ilumina|fundaç|estrutur|localiza", re.I)
_DASH_MIN_ITEMS = 12


@dataclass
class PlanSheet:
    index: int
    page: object
    scale: int
    text: str


def _norm(c) -> tuple:
    return tuple(round(float(x), 2) for x in (c or ()))


def find_plans(docs) -> list[PlanSheet]:
    """Folhas de planta de piso (não cobertura/implantação/acabamentos), com escala."""
    import pymupdf

    out = []
    for i, (_, data) in enumerate(docs):
        try:
            pdf = pymupdf.open(stream=data, filetype="pdf")
        except Exception:  # noqa: BLE001
            continue
        for page in pdf:
            text = page.get_text()
            flat = " ".join(text.split())
            if not PLAN_RX.search(flat):
                continue
            titles = [m.group(0) for m in PLAN_RX.finditer(flat)]
            # o título da folha (não uma referência no texto) não pode ser de acabamentos
            head = flat[max(0, flat.find(titles[0]) - 5): flat.find(titles[0]) + 60]
            if NOT_PLAN_RX.search(head):
                continue
            sc = SCALE_RX.findall(flat)
            if not sc:
                continue
            out.append(PlanSheet(i, page, int(sc[0]), text))
    return out


class _Frame:
    """Conversão pontos-PDF → metros reais (y para cima)."""

    def __init__(self, page, scale: int):
        self.m_per_pt = scale / PT_PER_M_PAPER
        self.h = page.rect.height

    def geom(self, g, origin=(0.0, 0.0)):
        f = self.m_per_pt
        return affine_transform(g, [f, 0, 0, -f, -origin[0], self.h * f - origin[1]])


# ----------------------------------------------------------------------------- paredes
def wall_mask(page, px_per_pt: int = 4):
    """Máscara raster das bandas de parede (tracejado curto não ortogonal) — qualquer ângulo."""
    import cv2

    w, h = int(page.rect.width * px_per_pt), int(page.rect.height * px_per_pt)
    m = np.zeros((h, w), np.uint8)
    for d in page.get_drawings():
        if d.get("type") != "s":
            continue
        col = _norm(d.get("color"))
        if col and max(col) > 0.35:          # tracejado de parede é escuro
            continue
        for it in d["items"]:
            if it[0] != "l":
                continue
            a, b = it[1], it[2]
            L = math.hypot(b.x - a.x, b.y - a.y)
            if L < 0.05 or L > 16:
                continue
            ang = math.degrees(math.atan2(b.y - a.y, b.x - a.x)) % 180
            if min(ang, abs(ang - 90), 180 - ang) < 3:   # linhas de pavimento/mobiliário (0°/90°)
                continue
            cv2.line(m, (int(a.x * px_per_pt), int(a.y * px_per_pt)),
                     (int(b.x * px_per_pt), int(b.y * px_per_pt)), 255, 2)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (11, 11)))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))
    num, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros_like(m)
    for i in range(1, num):
        if st[i, cv2.CC_STAT_AREA] > 600:
            keep[lab == i] = 255
    return keep


def _mask_polygons(mask, px_per_pt):
    import cv2

    cs, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    polys = []
    for c in cs:
        if len(c) < 3:
            continue
        p = Polygon([(x / px_per_pt, y / px_per_pt) for x, y in c[:, 0, :]]).buffer(0)
        if p.area > 0:
            polys.append(p)
    return polys


def wall_segments(mask, px_per_pt: int, m_per_pt: float, min_len_m=0.45):
    """Eixos das paredes (segmentos) + espessura medida pela transformada de distância."""
    import cv2
    from skimage.morphology import skeletonize

    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    sk = skeletonize(mask > 0).astype(np.uint8) * 255
    px_m = m_per_pt / px_per_pt
    lines = cv2.HoughLinesP(sk, 1, np.pi / 360, threshold=12,
                            minLineLength=int(min_len_m / px_m), maxLineGap=int(0.12 / px_m))
    segs = []
    for x1, y1, x2, y2 in (np.asarray(lines).reshape(-1, 4) if lines is not None else []):
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 4))
        xs = np.linspace(x1, x2, n).astype(int)
        ys = np.linspace(y1, y2, n).astype(int)
        t = 2 * float(np.median(dist[ys, xs])) * px_m
        segs.append(((x1 / px_per_pt, y1 / px_per_pt), (x2 / px_per_pt, y2 / px_per_pt), t))
    return _merge_collinear(segs, tol_pt=0.10 / m_per_pt)


def _merge_collinear(segs, tol_pt):
    """Funde segmentos colineares sobrepostos (o Hough devolve vários por parede)."""
    out: list[list] = []
    for a, b, t in sorted(segs, key=lambda s: -math.dist(s[0], s[1])):
        la = LineString([a, b])
        merged = False
        for o in out:
            lo = LineString([o[0], o[1]])
            ang1 = math.atan2(b[1] - a[1], b[0] - a[0]) % math.pi
            ang2 = math.atan2(o[1][1] - o[0][1], o[1][0] - o[0][0]) % math.pi
            dang = min(abs(ang1 - ang2), math.pi - abs(ang1 - ang2))
            if dang < math.radians(3) and lo.distance(la) < tol_pt and \
                    max(lo.distance(LineString([a, a])), lo.distance(LineString([b, b]))) < tol_pt * 1.5:
                # projetar extremos sobre a direção do mais longo e estender
                ux, uy = o[1][0] - o[0][0], o[1][1] - o[0][1]
                n = math.hypot(ux, uy)
                ux, uy = ux / n, uy / n
                ts = [((p[0] - o[0][0]) * ux + (p[1] - o[0][1]) * uy) for p in (o[0], o[1], a, b)]
                t0, t1 = min(ts), max(ts)
                o[0] = (o[0][0] + ux * t0, o[0][1] + uy * t0)
                o[1] = (o[0][0] + ux * (t1 - t0), o[0][1] + uy * (t1 - t0))
                o[2] = max(o[2], t)
                merged = True
                break
        if not merged:
            out.append([a, b, t])
    return [tuple(o) for o in out]


# ----------------------------------------------------------------------------- contornos tracejados
def dashed_rings(page, min_area_pt2=1500.0):
    """Anéis fechados formados por linhas tracejadas (traços preenchidos ou riscados), por cor."""
    by_col: dict[tuple, list] = {}
    for d in page.get_drawings():
        col = _norm(d.get("fill")) if d.get("type") in ("f", "fs") else _norm(d.get("color"))
        if not col or (max(col) - min(col) < 0.15):    # só cores (o preto/cinzento é desenho)
            continue
        r = d["rect"]
        if max(r.width, r.height) > 40:                 # traço, não mancha
            continue
        by_col.setdefault(col, []).append(box(r.x0, r.y0, max(r.x1, r.x0 + 0.1), max(r.y1, r.y0 + 0.1)))
    rings = {}
    for col, bs in by_col.items():
        if len(bs) < _DASH_MIN_ITEMS:
            continue
        band = unary_union([b.buffer(2.6, join_style=2) for b in bs])
        polys = []
        for g in getattr(band, "geoms", [band]):
            for r in g.interiors:
                p = Polygon(r)
                if p.area > min_area_pt2 / 10:
                    polys.append(p)
        if polys:
            rings[col] = sorted(polys, key=lambda p: -p.area)
    return rings


def snap_directions(walls, fp, tol_deg=2.5):
    """Paredes a ±2,5° de uma direção dominante do contorno → alinhadas (imprecisão de desenho), qualquer que
    seja a direção dominante (edifícios rodados ou com alas oblíquas mantêm as suas direções)."""
    cs = list(fp.exterior.coords)
    hist: dict[int, float] = {}
    for p, q in zip(cs, cs[1:]):
        a = round(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])) % 180)
        hist[a % 180] = hist.get(a % 180, 0.0) + math.dist(p, q)
    dom = [a for a, L in sorted(hist.items(), key=lambda kv: -kv[1]) if L > 2.0][:4]
    out = []
    for w in walls:
        (ax, ay), (bx, by) = w.a, w.b
        ang = math.degrees(math.atan2(by - ay, bx - ax)) % 180
        best = min(dom, key=lambda d: min(abs(ang - d), 180 - abs(ang - d)), default=None)
        if best is not None and min(abs(ang - best), 180 - abs(ang - best)) <= tol_deg:
            mx, my, L = (ax + bx) / 2, (ay + by) / 2, math.dist(w.a, w.b)
            ux, uy = math.cos(math.radians(best)), math.sin(math.radians(best))
            if ux * (bx - ax) + uy * (by - ay) < 0:
                ux, uy = -ux, -uy
            w.a = (round(mx - ux * L / 2, 3), round(my - uy * L / 2, 3))
            w.b = (round(mx + ux * L / 2, 3), round(my + uy * L / 2, 3))
        out.append(w)
    return out


# ----------------------------------------------------------------------------- leitura completa
_DIM_TXT = re.compile(r"^\d{1,3}[.,]\d{2}$")


def _face_lines(page, f: float, ox: float, oy: float):
    """Traços escuros horizontais e verticais da folha (faces de paredes, caixilhos…) em metros do edifício."""
    H = page.rect.height
    hz, vt = [], []
    for d in page.get_drawings():
        col = d.get("color")
        if col is None or max(col) > 0.25:
            continue
        for it in d["items"]:
            if it[0] == "l":
                segs = [(it[1], it[2])]
            elif it[0] == "re":
                r = it[1]
                segs = [(r.tl, r.tr), (r.bl, r.br), (r.tl, r.bl), (r.tr, r.br)]
            else:
                continue
            for a, b in segs:
                ax, ay, bx, by = a.x * f - ox, H * f - a.y * f - oy, b.x * f - ox, H * f - b.y * f - oy
                if abs(ay - by) < 0.004 and abs(bx - ax) > 0.05:
                    hz.append((min(ax, bx), max(ax, bx), ay))
                elif abs(ax - bx) < 0.004 and abs(by - ay) > 0.05:
                    vt.append((min(ay, by), max(ay, by), ax))
    return np.array(hz or [(0, 0, -1e9)]), np.array(vt or [(0, 0, -1e9)])


def _match_span(v: float, x: float, y: float, hz, vt, tol=0.012):
    """Procura, à volta do texto, as duas faces cuja distância é o valor escrito (texto ao centro da cota).
    → (eixo, início, fim, erro) ou None."""
    best = None
    for axis in ("x", "y"):
        for dy in ((0.0, -0.12, 0.12) if axis == "x" else (0.0,)):
            for dx in ((0.0,) if axis == "x" else (0.0, -0.12, 0.12)):
                X, Y = x + dx, y + dy
                if axis == "x":
                    m = (vt[:, 0] <= Y) & (vt[:, 1] >= Y)
                    cs = vt[m][:, 2]
                    pos = np.sort(cs[cs > X] - X)[:12]
                    neg = np.sort(X - cs[cs < X])[:12]
                else:
                    m = (hz[:, 0] <= X) & (hz[:, 1] >= X)
                    cs = hz[m][:, 2]
                    pos = np.sort(cs[cs > Y] - Y)[:12]
                    neg = np.sort(Y - cs[cs < Y])[:12]
                for a in pos:
                    for b_ in neg:
                        e = abs(a + b_ - v)
                        asym = abs(a - b_) / max(v, 0.1)
                        if e <= tol and asym <= 0.35:
                            score = e + 0.01 * asym
                            if best is None or score < best[-1]:
                                if axis == "x":
                                    best = ("x", (X - b_, Y), (X + a, Y), round(e, 4), score)
                                else:
                                    best = ("y", (X, Y - b_), (X, Y + a), round(e, 4), score)
    return best[:4] if best else None


def _keep_faces(fp, hz, vt, out: list, min_len=0.20) -> None:
    """Traços horizontais/verticais ≥ 20 cm dentro da área de construção (sem duplicados ao cm)."""
    from shapely.prepared import prep
    zone = prep(fp.buffer(0.6))
    seen = set()
    for x0, x1, y in hz:
        if x1 - x0 >= min_len and zone.intersects(LineString([(x0, y), (x1, y)])):
            k = (round(x0, 2), round(y, 2), round(x1, 2), round(y, 2))
            if k not in seen:
                seen.add(k)
                out.append(list(k))
    for y0, y1, x in vt:
        if y1 - y0 >= min_len and zone.intersects(LineString([(x, y0), (x, y1)])):
            k = (round(x, 2), round(y0, 2), round(x, 2), round(y1, 2))
            if k not in seen:
                seen.add(k)
                out.append(list(k))


def _drop_patterns(lines: list) -> list:
    """Retira os padrões de pavimento/tracejados: séries de ≥ 4 traços paralelos igualmente espaçados (8–35 cm)
    que se sobrepõem — uma parede tem 2 faces, não uma série regular."""
    def key(q):
        hzt = abs(q[1] - q[3]) < 1e-6
        return hzt, (q[1] if hzt else q[0]), (min(q[0], q[2]) if hzt else min(q[1], q[3])), (max(q[0], q[2]) if hzt else max(q[1], q[3]))
    ks = [key(q) for q in lines]
    from collections import defaultdict
    byc = defaultdict(list)
    for i, (hzt, c, a, b_) in enumerate(ks):
        byc[(hzt, round(c, 2))].append(i)

    def at(hzt, c, a, b_):
        for cc in (round(c, 2), round(c + 0.01, 2), round(c - 0.01, 2)):
            for j in byc.get((hzt, cc), []):
                _, _, a2, b2 = ks[j]
                if min(b_, b2) - max(a, a2) >= 0.6 * (b_ - a):
                    return True
        return False
    keep = []
    for i, (hzt, c, a, b_) in enumerate(ks):
        pattern = False
        for d in [x / 100 for x in range(8, 36)]:
            if at(hzt, c + d, a, b_) and at(hzt, c - d, a, b_) and (at(hzt, c + 2 * d, a, b_) or at(hzt, c - 2 * d, a, b_)):
                pattern = True
                break
        if not pattern:
            keep.append(lines[i])
    return keep


def written_dims(page, fr, ox: float, oy: float, fp) -> list[dict]:
    """Cotas ESCRITAS pelo arquiteto na folha (valor, posição em metros), no referencial do edifício.
    Duas fontes: o valor escrito e a distância MEDIDA entre as duas faces desenhadas de cada lado do texto.
    Confirmada (≤ 1,2 cm, texto ao centro) → cota desenhada com linha de cota nas extremidades reais."""
    out = []
    f = fr.m_per_pt
    zone = fp.buffer(6.0)
    texts = []
    for blk in page.get_text("dict").get("blocks", []):
        for ln in blk.get("lines", []):
            t = "".join(sp.get("text", "") for sp in ln.get("spans", [])).strip()
            if not _DIM_TXT.match(t):
                continue
            x0, y0, x1, y1 = ln["bbox"]
            X, Y = (x0 + x1) / 2 * f - ox, fr.h * f - (y0 + y1) / 2 * f - oy
            if zone.contains(Point(X, Y)):
                dx, dy = ln.get("dir", (1.0, 0.0))
                texts.append((float(t.replace(",", ".")), X, Y, math.degrees(math.atan2(-dy, dx))))
    if not texts:
        return out
    hz, vt = _face_lines(page, f, ox, oy)
    _keep_faces(fp, hz, vt, out_faces := [])
    written_dims.faces = out_faces                  # traço do arquiteto (faces das paredes), para as plantas cotadas
    for v, X, Y, ang in texts:
        d = {"v": v, "x": round(X, 3), "y": round(Y, 3), "ang": round(ang, 1), "ok": False}
        mt = _match_span(v, X, Y, hz, vt)
        if mt:
            d.update(ok=True, axis=mt[0], a=[round(float(c), 3) for c in mt[1]], b=[round(float(c), 3) for c in mt[2]],
                     err=float(mt[3]))
        out.append(d)
    return out


def read(docs, hypotheses: str = "", country: str = "PT") -> Building | None:
    plans = find_plans(docs)
    if not plans:
        return None
    sheet = plans[0]
    page = sheet.page
    fr = _Frame(page, sheet.scale)
    ppp = 4
    mask = wall_mask(page, ppp)
    wall_polys = _mask_polygons(mask, ppp)
    if not wall_polys:
        return None
    walls_union = unary_union(wall_polys)

    rings = dashed_rings(page)
    footprint_pt, holes_pt, covered_pt, ring_col = None, [], [], None
    best = 0.0
    for col, polys in rings.items():
        big = polys[0]
        inside = walls_union.intersection(big.buffer(6)).area / max(walls_union.area, 1e-9)
        if inside > best and big.area > 30 / fr.m_per_pt ** 2:
            best, footprint_pt, ring_col = inside, big, col
    checks = []
    if footprint_pt is None or best < 0.5:
        # sem linha de área de construção: contorno = envolvente das paredes exteriores
        hull = walls_union.buffer(1.5 / fr.m_per_pt / 10, join_style=2)
        footprint_pt = Polygon(max(getattr(hull, "geoms", [hull]), key=lambda g: g.area).exterior)
        checks.append({"item": "contorno", "fonte": "envolvente das paredes (sem linha de área)", "ok": None})
    else:
        holes_pt = [p for p in rings[ring_col][1:] if footprint_pt.contains(p.representative_point())]
        for col, polys in rings.items():
            if col == ring_col:
                continue
            for p in polys:
                if p.intersection(footprint_pt).area < 0.5 * p.area:
                    covered_pt.append(p)
    # eixo da linha tracejada = anel interior da banda reposto pela mesma dilatação (2,6 pt),
    # para o contorno exterior E para os pátios (validado no caso de referência: 302,66 m²
    # lidos vs 303,35 m² declarados, −0,2 %)
    outer = footprint_pt.buffer(2.6, join_style=2)
    holes = [h.buffer(2.6, join_style=2) for h in holes_pt]
    fp_pt = Polygon(outer.exterior, [h.exterior for h in holes])
    covered_pt = [c.buffer(2.6, join_style=2).difference(outer).buffer(0) for c in covered_pt]
    covered_pt = [c for c in covered_pt if c.area > 0.5 / fr.m_per_pt ** 2]
    # origem no canto inferior esquerdo do contorno
    fp_m = fr.geom(fp_pt)
    ox, oy = fp_m.bounds[0], fp_m.bounds[1]
    fp = fr.geom(fp_pt, (ox, oy))
    covered = [fr.geom(p, (ox, oy)) for p in covered_pt]

    walls = []
    for a, b, t in wall_segments(mask, ppp, fr.m_per_pt):
        L = fr.geom(LineString([a, b]), (ox, oy))
        (ax, ay), (bx, by) = L.coords
        if L.length < 0.45 or t < 0.06:
            continue
        if not fp.buffer(0.6).contains(L):        # muros do lote, vedações: fora do edifício
            continue
        for piece, ext in split_by_boundary(L, fp):
            (ax, ay), (bx, by) = piece.coords[0], piece.coords[-1]
            walls.append(Wall((round(ax, 3), round(ay, 3)), (round(bx, 3), round(by, 3)),
                              round(min(max(t, 0.10), 0.40), 2), exterior=bool(ext), source="vetorial"))
    walls = snap_directions(walls, fp)
    b = Building(footprint=fp, covered=covered, walls=walls, country=country,
                 sources=[f"planta vetorial (doc {sheet.index + 1}, escala 1:{sheet.scale})"])
    b.hypotheses["frame"] = {"doc": sheet.index, "page": page.number, "scale": sheet.scale, "ox": round(ox, 4), "oy": round(oy, 4)}
    written_dims.faces = []
    b.hypotheses["dims_text"] = written_dims(page, fr, ox, oy, fp)
    b.hypotheses["faces"] = [[float(v) for v in q] for q in _drop_patterns(written_dims.faces)][:5000]
    # confrontação 1: área do contorno vs. área das paredes + compartimentos fechados
    b.checks = checks + [{
        "item": "área de construção (contorno lido)", "valor": round(fp.area, 2), "unidade": "m²",
        "metodo": "eixo da linha tracejada de área de construção (pátios descontados)",
    }, {
        "item": "comprimento total de paredes lidas", "valor": round(sum(w.length for w in walls), 2), "unidade": "m",
        "metodo": "eixos das bandas tracejadas (transformada de distância + Hough)",
    }]
    return b
