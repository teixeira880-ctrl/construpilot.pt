"""Leitura da geometria REAL em plantas raster: PDF digitalizado, fotografia, JPG/PNG/TIFF, DXF renderizado.

Duas fontes independentes, combinadas:
  A. Imagem (código): paredes detetadas em qualquer estilo de desenho —
       * tracejadas (aberturas morfológicas orientadas a 45°/135°, separam o tracejado das
         riscas de pavimento a 0°/90°),
       * cheias (poché: sobrevivem a qualquer abertura),
       * a traço grosso (filtro de espessura de traço);
     texto, cotas e símbolos (componentes pequenos) são retirados antes.
  B. IA de visão: forma aproximada do contorno e dos pátios (coordenadas 0–1000), escala da
     folha e cotas gerais. A IA dá a TOPOLOGIA; o código dá a PRECISÃO: cada aresta da IA é
     encaixada na face real da parede mais próxima (≤ 0,8 m).

Escala: (1) tamanho físico da folha × escala 1:N, ou (2) cota geral lida pela IA ÷ medida em
píxeis — confirmada por uma 2.ª cota (desvio ≤ 3 %). Sem escala fiável → None (nunca inventa).
"""
from __future__ import annotations

import base64
import io
import json
import logging
import math
import re

import numpy as np
from shapely.geometry import LineString, Polygon
from shapely.ops import unary_union

from .model import Building, Wall, split_by_boundary

log = logging.getLogger(__name__)
PT_PER_M_PAPER = 72 / 0.0254
PAPER_MM = [(841, 1189), (594, 841), (420, 594), (297, 420), (210, 297), (580, 297), (594, 297)]


# ----------------------------------------------------------------------------- imagem
def load_gray(data: bytes, page_index: int = 0, dpi: int = 200):
    """(imagem cinzenta, mm de papel por píxel ou None). Aceita PDF (página) ou imagem."""
    import cv2
    import pymupdf

    if data[:4] == b"%PDF":
        pdf = pymupdf.open(stream=data, filetype="pdf")
        page = pdf[page_index]
        pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
        img = np.frombuffer(pix.samples, np.uint8).reshape(pix.height, pix.width).copy()
        w_mm, h_mm = page.rect.width / 72 * 25.4, page.rect.height / 72 * 25.4
        # tamanho físico só é fiável se corresponder a um formato de papel de desenho
        paper = any(abs(sorted((w_mm, h_mm))[0] - a) / a < 0.03 and abs(sorted((w_mm, h_mm))[1] - b) / b < 0.03
                    for a, b in [sorted(p) for p in PAPER_MM])
        return img, (25.4 / dpi if paper else None)
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        from PIL import Image
        img = np.array(Image.open(io.BytesIO(data)).convert("L"))
    return img, None


def deskew(img):
    """Endireita uma fotografia/digitalização torta (ângulo dominante das linhas longas)."""
    import cv2

    edges = cv2.Canny(img, 50, 150)
    lines = cv2.HoughLinesP(edges, 1, np.pi / 720, 200, minLineLength=max(img.shape) // 8, maxLineGap=5)
    if lines is None:
        return img, 0.0
    angs = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        a = math.degrees(math.atan2(y2 - y1, x2 - x1)) % 90
        angs.append(a - 90 if a > 45 else a)
    a = float(np.median(angs))
    if abs(a) < 0.15 or abs(a) > 10:
        return img, 0.0
    h, w = img.shape
    M = cv2.getRotationMatrix2D((w / 2, h / 2), a, 1.0)
    return cv2.warpAffine(img, M, (w, h), borderValue=255), a


def _line_kernel(n_px: int, ang: float):
    import cv2

    n = max(3, n_px) | 1
    k = np.zeros((n, n), np.uint8)
    c = n // 2
    dx, dy = math.cos(math.radians(ang)), math.sin(math.radians(ang))
    cv2.line(k, (round(c - dx * c), round(c - dy * c)), (round(c + dx * c), round(c + dy * c)), 1, 1)
    return k


def _ink(img, mpp: float):
    """Traço vs papel por contraste LOCAL (black-hat): sombras, papel amarelado, JPEG, traços finos e claros."""
    import cv2

    k = max(7, int(0.25 / mpp)) | 1
    bh = cv2.morphologyEx(img, cv2.MORPH_BLACKHAT, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    loc = ((bh > 12) * 255).astype(np.uint8)
    glob = ((img < 150) * 255).astype(np.uint8)              # manchas escuras grandes (poché) que o black-hat não vê
    return cv2.bitwise_or(loc, glob)


def wall_mask(img, mpp: float):
    """Máscara de paredes (qualquer estilo) — mpp = metros reais por píxel."""
    import cv2

    ink = _ink(img, mpp)
    # 1) retirar texto/símbolos: componentes pequenos (< 0,45 m) que não tocam em nada maior
    num, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    small = np.zeros(num, bool)
    lim = 0.45 / mpp
    small[1:] = (np.maximum(st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]) < lim)
    clean = ink.copy()
    clean[small[lab]] = 0
    # 2a) tracejado a 45°/135° (separa das riscas de pavimento a 0°/90°)
    L = max(5, int(0.10 / mpp))
    hatch = cv2.bitwise_or(cv2.morphologyEx(ink, cv2.MORPH_OPEN, _line_kernel(L, 45)),
                           cv2.morphologyEx(ink, cv2.MORPH_OPEN, _line_kernel(L, 135)))
    # 2b) poché + traço grosso (≥ ~5 cm reais e ≥ 3 px): sobrevive a uma erosão
    e = max(3, int(0.05 / mpp)) | 1
    thick = cv2.morphologyEx(clean, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (e, e)))
    m = cv2.bitwise_or(hatch, thick)
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (max(3, int(0.12 / mpp)) | 1,) * 2))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(0.06 / mpp)) | 1,) * 2))
    # 3) retirar só as ZONAS grossas (> 60 cm: manchas, árvores, texto fundido), não o componente inteiro
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    core = ((dist > 0.30 / mpp) * 255).astype(np.uint8)
    if core.any():
        r = max(3, int(0.32 / mpp)) | 1
        m = cv2.bitwise_and(m, cv2.bitwise_not(cv2.dilate(core, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1,) * 2))))
    # 4) bandas com comprimento de parede (≥ 0,6 m) e espessura ≥ 7 cm
    num, lab, st, _ = cv2.connectedComponentsWithStats(m)
    dist = cv2.distanceTransform(m, cv2.DIST_L2, 5)
    keep = np.zeros_like(m)
    for i in range(1, num):
        area = st[i, cv2.CC_STAT_AREA] * mpp * mpp
        if area < 0.05:
            continue
        sel = lab == i
        t = 2 * float(np.percentile(dist[sel], 90)) * mpp
        if t >= 0.07 and area / max(t, 1e-6) >= 0.6:
            keep[sel] = 255
    return keep


def segments(mask, mpp: float, min_len=0.45):
    """Eixos (px) + espessura (m) das paredes."""
    import cv2
    from skimage.morphology import skeletonize

    from .pdf_vector import _merge_collinear

    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    sk = skeletonize(mask > 0).astype(np.uint8) * 255
    lines = cv2.HoughLinesP(sk, 1, np.pi / 360, threshold=12, minLineLength=int(min_len / mpp),
                            maxLineGap=int(0.12 / mpp))
    segs = []
    for x1, y1, x2, y2 in (np.asarray(lines).reshape(-1, 4) if lines is not None else []):
        n = max(2, int(math.hypot(x2 - x1, y2 - y1) / 4))
        xs = np.clip(np.linspace(x1, x2, n).astype(int), 0, mask.shape[1] - 1)
        ys = np.clip(np.linspace(y1, y2, n).astype(int), 0, mask.shape[0] - 1)
        t = 2 * float(np.median(dist[ys, xs])) * mpp
        segs.append(((float(x1), float(y1)), (float(x2), float(y2)), t))
    return _merge_collinear(segs, tol_pt=0.10 / mpp)


# ----------------------------------------------------------------------------- contorno: IA (forma) + imagem (precisão)
def long_lines(img, mpp: float, min_m=1.0):
    """Linhas retas longas da imagem (caixilhos, fachadas, linhas tracejadas de área) — 2.º nível de encaixe."""
    import cv2

    ink = _ink(img, mpp)
    lines = cv2.HoughLinesP(ink, 1, np.pi / 720, threshold=int(min_m / mpp * 0.6), minLineLength=int(min_m / mpp),
                            maxLineGap=int(0.15 / mpp))
    return [((float(a), float(b)), (float(c), float(d)), 0.0)
            for a, b, c, d in (np.asarray(lines).reshape(-1, 4) if lines is not None else [])]


def snap_outline(poly_px: Polygon, segs, mpp: float, reach_m=0.8, fallback=None, far_m=1.5):
    """Encaixa cada aresta do contorno aproximado na face EXTERIOR da parede paralela mais próxima."""
    cs = list(poly_px.exterior.coords)[:-1]
    n = len(cs)
    # direções dominantes das paredes reais (qualquer ângulo, não só 0°/90°)
    hist: dict[int, float] = {}
    for p, q, _t in segs:
        ang = int(round(math.degrees(math.atan2(q[1] - p[1], q[0] - p[0])))) % 180
        hist[ang] = hist.get(ang, 0.0) + math.dist(p, q)
    doms = []
    for ang, wgt in sorted(hist.items(), key=lambda kv: -kv[1]):
        if all(min(abs(ang - d), 180 - abs(ang - d)) > 8 for d in doms):
            doms.append(ang)
        if len(doms) >= 4:
            break
    centroid = poly_px.centroid
    new_lines, matched, flags = [], 0, []
    for i in range(n):
        a, b = np.array(cs[i]), np.array(cs[(i + 1) % n])
        d = b - a
        L = np.linalg.norm(d)
        if L < 1e-6:
            new_lines.append((a, d))
            flags.append(False)
            continue
        u = d / L
        ang = math.degrees(math.atan2(u[1], u[0])) % 180
        dom = min(doms, key=lambda x: min(abs(ang - x), 180 - abs(ang - x)), default=None)
        if dom is not None and min(abs(ang - dom), 180 - abs(ang - dom)) <= 8:
            v = np.array([math.cos(math.radians(dom)), math.sin(math.radians(dom))])
            u = v if np.dot(v, u) >= 0 else -v           # direção da parede real, rodada no meio da aresta
            mid = (a + b) / 2
            a, b = mid - u * L / 2, mid + u * L / 2
        nrm = np.array([-u[1], u[0]])
        if np.dot(nrm, np.array([centroid.x, centroid.y]) - (a + b) / 2) > 0:
            nrm = -nrm                                    # normal para fora
        best, best_off, best_score = None, 0.0, -9.0
        for p, q, t in segs:
            p, q = np.array(p), np.array(q)
            v = q - p
            lv = np.linalg.norm(v)
            if lv < 1e-6 or abs(np.dot(v / lv, u)) < math.cos(math.radians(6)):
                continue
            # sobreposição ao longo da aresta ≥ 30 %
            tp, tq = sorted((np.dot(p - a, u), np.dot(q - a, u)))
            ov = max(0.0, min(L, tq) - max(0.0, tp))
            if ov < 0.3 * min(L, lv):
                continue
            off = np.dot((p + q) / 2 - a, nrm) + (t / mpp) / 2            # face exterior
            if abs(off) * mpp <= reach_m:
                score = -abs(off)                                            # 1.º: a mais próxima
            elif abs(off) * mpp <= far_m and ov >= 0.5 * L:
                score = -1e6 + off                                           # 2.º: longe → a mais EXTERIOR (nunca uma interior)
            else:
                continue
            if best is None or score > best_score:
                best, best_off, best_score = (p, q), off, score
        if best is None and fallback:
            # sem parede (envidraçado): a linha longa paralela mais forte e mais próxima
            cand = []
            for p, q, _t in fallback:
                p, q = np.array(p), np.array(q)
                v = q - p
                lv = np.linalg.norm(v)
                if lv < 1e-6 or abs(np.dot(v / lv, u)) < math.cos(math.radians(3)):
                    continue
                tp, tq = sorted((np.dot(p - a, u), np.dot(q - a, u)))
                ov = max(0.0, min(L, tq) - max(0.0, tp))
                off = np.dot((p + q) / 2 - a, nrm)
                if ov >= 0.5 * L and abs(off) * mpp <= reach_m:
                    cand.append((ov, -abs(off), off))
            if cand:
                best_off = max(cand)[2]
                best = True
        if best is not None:
            matched += 1
            a = a + nrm * best_off
        new_lines.append((a, u))
        flags.append(best is not None)
    out = _rebuild(new_lines)
    snap_outline.last = (new_lines, flags)
    return out, matched / max(n, 1)


def _rebuild(new_lines):
    n = len(new_lines)
    pts = []
    for i in range(n):
        (p1, u1), (p2, u2) = new_lines[i - 1], new_lines[i]
        den = u1[0] * u2[1] - u1[1] * u2[0]
        if abs(den) < 1e-6:
            pts.append(tuple(p2))
            continue
        s = ((p2[0] - p1[0]) * u2[1] - (p2[1] - p1[1]) * u2[0]) / den
        pts.append((p1[0] + u1[0] * s, p1[1] + u1[1] * s))
    out = Polygon(pts).buffer(0)
    if out.geom_type != "Polygon":
        out = max(out.geoms, key=lambda g: g.area)
    return out


def correct_with_dims(lines, flags, dims_px, segs, mpp, tol=0.015):
    """Regra das duas fontes: se uma cota geral escrita não bate com o contorno (> 1,5 %), a fachada extrema
    NÃO encaixada nessa direção é deslocada até a cota bater e volta a encaixar numa parede a ≤ 0,3 m."""
    lines = [(np.array(a, float), np.array(u, float)) for a, u in lines]
    fixed = []
    for value_m, u_dim in dims_px:
        u_dim = u_dim / (np.linalg.norm(u_dim) + 1e-9)
        poly = _rebuild(lines)
        proj = [float(np.dot(np.array(c), u_dim)) for c in poly.exterior.coords]
        lo, hi = min(proj), max(proj)
        meas = (hi - lo) * mpp
        if abs(meas - value_m) / value_m <= tol:
            continue
        delta = (value_m - meas) / mpp
        # arestas perpendiculares à cota, nos extremos
        ext = []
        for i, (a, u) in enumerate(lines):
            if abs(np.dot(u, u_dim)) > math.sin(math.radians(10)):
                continue
            pa = float(np.dot(a, u_dim))
            if abs(pa - lo) < 0.25 / mpp:
                ext.append((i, -1))
            elif abs(pa - hi) < 0.25 / mpp:
                ext.append((i, +1))
        free = [(i, sgn) for i, sgn in ext if not flags[i]] or ext
        sides = {sgn for _, sgn in free}
        if len(sides) != 1:
            continue
        sgn = sides.pop()
        for i, _ in [e for e in free if e[1] == sgn]:
            a, u = lines[i]
            a2 = a + u_dim * sgn * delta
            # reencaixe fino numa parede paralela a ≤ 0,3 m
            best = None
            for p, q, t in segs:
                p, q = np.array(p), np.array(q)
                v = q - p
                lv = np.linalg.norm(v)
                if lv < 1e-6 or abs(np.dot(v / lv, u)) < math.cos(math.radians(4)):
                    continue
                off = float(np.dot((p + q) / 2 - a2, u_dim)) + sgn * (t / mpp) / 2
                if abs(off) * mpp <= 0.3 and (best is None or abs(off) < abs(best)):
                    best = off
            lines[i] = (a2 + (u_dim * best if best is not None else 0), u)
            flags[i] = True
            fixed.append((value_m, round(meas, 2)))
    return _rebuild(lines), fixed


def outline_by_closing(mask, mpp: float, R_m=3.0):
    """Sem IA: fecho morfológico das paredes (vãos ≤ 2R fechados), maior componente."""
    from .pdf_vector import _mask_polygons

    polys = _mask_polygons(mask, 1)
    if not polys:
        return None
    R = R_m / mpp
    u = unary_union(polys).buffer(R, join_style=2).buffer(-R, join_style=2)
    g = max(getattr(u, "geoms", [u]), key=lambda x: x.area)
    return Polygon(g.exterior)


# ----------------------------------------------------------------------------- IA de visão
LAYOUT_SYSTEM = ("És um técnico de medições a ler uma planta de arquitetura (pode ser digitalizada, fotografada ou desenhada "
                 "à mão). Respondes SÓ com JSON válido. Nunca inventes cotas: null se não estiverem escritas.")
LAYOUT_PROMPT = """Imagem: planta de um edifício. Coordenadas normalizadas: x e y de 0 a 1000 (0,0 = canto superior esquerdo da imagem).
Devolve:
{
  "is_floor_plan": true/false,
  "scale": "1:100" ou null (escala escrita na folha),
  "outline": [[x,y], ...]  contorno EXTERIOR da área coberta do edifício (faces exteriores das paredes), vértices por ordem, sem o terreno nem muros do lote,
  "courtyards": [[[x,y], ...], ...]  pátios/saguões descobertos DENTRO do contorno (vazio se não houver),
  "covered_outside": [[[x,y], ...]]  palas/alpendres cobertos fora das paredes (vazio se não houver),
  "overall_dims": [{"value_m": 25.10, "from": [x,y], "to": [x,y]}, ...]  2 a 4 cotas GERAIS escritas (as mais compridas), com as extremidades na imagem,
  "declared_area_m2": área de construção escrita na legenda ou null,
  "storeys_shown": número de pisos desenhados nesta folha
}"""


def _png_b64(img, max_side=1600) -> str:
    import cv2

    h, w = img.shape[:2]
    k = min(1.0, max_side / max(h, w))
    small = cv2.resize(img, (int(w * k), int(h * k)), interpolation=cv2.INTER_AREA) if k < 1 else img
    ok, buf = cv2.imencode(".png", small)
    return base64.b64encode(buf.tobytes()).decode()


async def ask_layout(llm, img) -> dict:
    if llm is None:
        return {}
    try:
        txt = await llm(LAYOUT_SYSTEM, LAYOUT_PROMPT, images=[_png_b64(img)], max_tokens=3000)
        m = re.search(r"\{.*\}", txt or "", re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("bet_geo layout AI failed: %s", type(exc).__name__)
        return {}


CORRECTION_PROMPT = """Primeira imagem: a planta. Segunda imagem: a mesma planta com o contorno que medimos a VERMELHO e as
arestas numeradas. As cotas gerais escritas não batem com o medido: {devs}.
Corrige: devolve o JSON completo como antes ("outline", "courtyards", "overall_dims"…), com o contorno EXTERIOR
correto (faces exteriores das paredes, coordenadas 0–1000 da primeira imagem). Não inventes cotas."""


async def ask_correction(llm, img, outline_px, devs, lay) -> dict:
    import cv2

    try:
        over = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        pts = np.array([[int(x), int(y)] for x, y in outline_px.exterior.coords], np.int32)
        cv2.polylines(over, [pts], True, (0, 0, 220), max(2, img.shape[1] // 600))
        for i, (p, q) in enumerate(zip(pts[:-1], pts[1:])):
            m = (p + q) // 2
            cv2.putText(over, f"E{i + 1}", (int(m[0]), int(m[1])), cv2.FONT_HERSHEY_SIMPLEX,
                        max(0.6, img.shape[1] / 2500), (0, 0, 220), 2)
        ok, buf = cv2.imencode(".png", cv2.resize(over, None, fx=min(1.0, 1600 / max(img.shape)), fy=min(1.0, 1600 / max(img.shape))))
        txt = await llm(LAYOUT_SYSTEM, LAYOUT_PROMPT + "\n\n" + CORRECTION_PROMPT.format(
            devs="; ".join(f"{v:.2f} m escrito vs {m_:.2f} m medido" for v, m_ in devs) or "ver contorno"),
            images=[_png_b64(img), base64.b64encode(buf.tobytes()).decode()], max_tokens=3000)
        m = re.search(r"\{.*\}", txt or "", re.S)
        return json.loads(m.group(0)) if m else {}
    except Exception as exc:  # noqa: BLE001
        log.warning("bet_geo correction AI failed: %s", type(exc).__name__)
        return {}


def _norm_poly(pts, w, h) -> Polygon | None:
    try:
        p = Polygon([(float(x) / 1000 * w, float(y) / 1000 * h) for x, y in pts]).buffer(0)
    except (TypeError, ValueError):
        return None
    if p.is_empty or p.area <= 0:
        return None
    return p if p.geom_type == "Polygon" else max(p.geoms, key=lambda g: g.area)


# ----------------------------------------------------------------------------- leitura completa
async def read(data: bytes | None, *, llm=None, page_index: int = 0, country: str = "PT", name: str = "",
               mm_per_px: float | None = None, scale_hint: int | None = None, layout: dict | None = None,
               image=None, m_per_px: float | None = None) -> Building | None:
    """data = PDF/imagem; ou image (cinzento) + m_per_px exato (DXF/IFC desenhados à escala)."""
    if image is not None:
        img, paper_mm_px, skew = image, None, 0.0
    else:
        img, paper_mm_px = load_gray(data, page_index)
        if mm_per_px:
            paper_mm_px = mm_per_px
        img, skew = deskew(img)
    h, w = img.shape
    lay = layout if layout is not None else await ask_layout(llm, img)
    if lay and lay.get("is_floor_plan") is False:
        return None
    checks = []
    # ---- escala (1): papel × escala escrita
    mpp = None
    sc = scale_hint
    m = re.search(r"1\s*[:/]\s*(\d{2,4})", str(lay.get("scale") or ""))
    if m:
        sc = int(m.group(1))
    if m_per_px:
        mpp = m_per_px
        checks.append({"item": "escala", "valor": round(m_per_px * 1000, 2), "unidade": "mm/píxel",
                       "metodo": "exata: unidades do ficheiro CAD/BIM"})
        paper_mm_px, sc = m_per_px * 1000, 1
    elif paper_mm_px and sc:
        mpp = paper_mm_px / 1000 * sc
        checks.append({"item": "escala", "valor": f"1:{sc}", "unidade": "", "metodo": "formato da folha × escala escrita"})
    dims = [d for d in (lay.get("overall_dims") or []) if isinstance(d, dict) and d.get("value_m")]
    # ---- escala (2): cotas gerais (fotografia sem tamanho de papel)
    if mpp is None and dims:
        ests = []
        for d in dims:
            try:
                (x0, y0), (x1, y1) = d["from"], d["to"]
                px = math.hypot((x1 - x0) / 1000 * w, (y1 - y0) / 1000 * h)
                if px > 20:
                    ests.append(float(d["value_m"]) / px)
            except (KeyError, TypeError, ValueError):
                continue
        if ests:
            mpp = float(np.median(ests))
            checks.append({"item": "escala", "valor": round(mpp * 1000, 3), "unidade": "mm/píxel",
                           "metodo": f"{len(ests)} cota(s) geral(is) lida(s) na planta (provisória, afinada pelas paredes)"})
    if mpp is None:
        return None                                         # sem escala fiável: não inventar medidas
    mask = wall_mask(img, mpp)
    segs = segments(mask, mpp)
    if not segs:
        return None
    longs = long_lines(img, mpp)
    calib_by_dims = "cota" in checks[0]["metodo"]

    def outline_from(lay_):
        """Contorno + pátios a partir de uma resposta da IA; devolve também o desvio às cotas escritas."""
        ck = []
        ai_outline = _norm_poly(lay_.get("outline") or [], w, h) if lay_ else None
        if ai_outline is not None:
            outline, frac = snap_outline(ai_outline, segs, mpp, fallback=longs)
            ck.append({"item": "contorno", "valor": round(frac * 100), "unidade": "% das arestas encaixadas em paredes",
                       "metodo": "forma lida pela IA, precisão pelas faces das paredes na imagem", "ok": frac >= 0.5})
            if dims and not calib_by_dims:              # escala conhecida: as cotas corrigem fachadas mal lidas
                dpx = []
                for d in dims:
                    try:
                        (x0, y0), (x1, y1) = d["from"], d["to"]
                        dpx.append((float(d["value_m"]), np.array([(x1 - x0) / 1000 * w, (y1 - y0) / 1000 * h])))
                    except (KeyError, TypeError, ValueError):
                        continue
                lines_, flags_ = snap_outline.last
                outline2, fixed = correct_with_dims(lines_, list(flags_), dpx, segs, mpp)
                if fixed:
                    outline = outline2
                    ck.append({"item": "correção automática pelas cotas", "valor": len(fixed), "unidade": "fachada(s)",
                               "metodo": "; ".join(f"cota {v:.2f} m (lido {m_:.2f} m)" for v, m_ in fixed)})
        else:
            outline, frac = outline_by_closing(mask, mpp), 0.0
            if outline is None:
                return None
            ck.append({"item": "contorno", "valor": None, "unidade": "",
                       "metodo": "fecho morfológico das paredes (sem IA): pátios não detetados", "ok": None})
        holes_ = []
        for c in (lay_ or {}).get("courtyards") or []:
            p = _norm_poly(c, w, h)
            if p is not None and outline.contains(p.representative_point()):
                hp, _ = snap_outline(p, segs, mpp, reach_m=0.6, fallback=longs)
                holes_.append(hp.intersection(outline))
        devs = []
        for d in dims:
            try:
                (x0, y0), (x1, y1) = d["from"], d["to"]
                u = np.array([(x1 - x0) / 1000 * w, (y1 - y0) / 1000 * h])
            except (KeyError, TypeError, ValueError):
                continue
            u = u / (np.linalg.norm(u) + 1e-9)
            proj = [float(np.dot(np.array(c), u)) for c in outline.exterior.coords]
            meas = (max(proj) - min(proj)) * mpp
            if meas > 1:
                devs.append((float(d["value_m"]), meas))
        worst = max((abs(m_ - v) / v for v, m_ in devs), default=0.0)
        return outline, holes_, frac, devs, worst, ck

    res = outline_from(lay)
    if res is None:
        return None
    # regra das duas fontes: fora da tolerância → a IA refaz a leitura vendo o que foi medido (1 nova tentativa)
    if llm is not None and lay and (res[4] > 0.015 or res[2] < 0.6):
        lay2 = await ask_correction(llm, img, res[0], res[3], lay)
        if lay2.get("outline"):
            res2 = outline_from({**lay, **lay2})
            if res2 is not None and (res2[4], -res2[2]) < (res[4], -res[2]):
                res = res2
                res[5].append({"item": "leitura refeita pela IA", "valor": None, "unidade": "",
                               "metodo": "confrontação fora da tolerância → contorno corrigido e novamente medido"})
    outline, holes, frac, devs, worst, ck = res
    checks += ck
    if devs:
        if calib_by_dims:                                    # fotografia: escala afinada pelas paredes reais
            k = float(np.median([v / m_ for v, m_ in devs]))
            mpp *= k
            worst = max(abs(m_ * k - v) / v for v, m_ in devs)
            devs = [(v, m_ * k) for v, m_ in devs]
        checks.append({"item": "cotas gerais vs. medida", "valor": round(worst * 100, 1), "unidade": "% desvio máx.",
                       "metodo": ", ".join(f"{v:.2f} m escrito / {m_:.2f} m medido" for v, m_ in devs[:4]).replace(".", ","),
                       "ok": worst <= 0.03})
    covered = []
    for c in lay.get("covered_outside") or []:
        p = _norm_poly(c, w, h)
        if p is not None:
            covered.append(p.difference(outline).buffer(0))
    # ---- para metros (y para cima), origem no canto inferior esquerdo
    from shapely.affinity import affine_transform

    def to_m(g):
        return affine_transform(g, [mpp, 0, 0, -mpp, 0, h * mpp])

    fp = Polygon(to_m(outline).exterior, [to_m(hh).exterior for hh in holes if not hh.is_empty and hh.area > 0])
    ox, oy = fp.bounds[0], fp.bounds[1]
    from shapely.affinity import translate
    fp = translate(fp, -ox, -oy)
    covered = [translate(to_m(c), -ox, -oy) for c in covered if c.area > 0]
    covered = [c for c in covered if c.area > 0.5]
    walls = []
    for a, b, t in segments(mask, mpp):
        L = translate(to_m(LineString([a, b])), -ox, -oy)
        if L.length < 0.45 or t < 0.06 or not fp.buffer(0.6).contains(L):
            continue
        for piece, ext in split_by_boundary(L, fp):
            (ax, ay), (bx, by) = piece.coords[0], piece.coords[-1]
            walls.append(Wall((round(ax, 3), round(ay, 3)), (round(bx, 3), round(by, 3)),
                              round(min(max(t, 0.10), 0.40), 2), exterior=bool(ext), source="raster"))
    from .pdf_vector import snap_directions
    walls = snap_directions(walls, fp)
    b = Building(footprint=fp, covered=covered, walls=walls, country=country,
                 sources=[f"planta raster {name or ''} (endireitada {skew:+.1f}°)".replace("  ", " ")])
    decl = lay.get("declared_area_m2")
    b.checks = checks + [{"item": "área de construção (contorno lido)", "valor": round(fp.area, 2), "unidade": "m²",
                          "metodo": "planta raster: paredes na imagem + forma da IA"}]
    if decl:
        try:
            decl = float(decl)
            diff = (fp.area - decl) / decl
            b.checks.append({"item": "área declarada na legenda (2.ª fonte)", "valor": decl, "unidade": "m²",
                             "metodo": f"diferença {diff * 100:+.1f} %".replace(".", ","), "ok": abs(diff) <= 0.05})
        except (TypeError, ValueError):
            pass
    b.hypotheses["_reader"] = "raster"
    return b
