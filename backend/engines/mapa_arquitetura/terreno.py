"""Terreno natural lido no levantamento topográfico incluído no DWFX de arquitetura.

Os pontos cotados do levantamento (camada «…Texto_Cota», p. ex. «T03-AL-Texto_Cota») vêm desenhados como traços (não como
texto) : a camada é desenhada numa imagem e lida por OCR (tesseract), cada leitura «ddd.dd» fica no centro do seu rótulo.
O lote é o contorno convexo da camada «limite lote» / «estrema». A cota média do terreno no lote é a média ponderada por
área da superfície triangulada (Delaunay) dos pontos lidos, recortada pelo lote — não é uma média simples dos pontos."""
from __future__ import annotations

import math
import re

CAMADA_COTA = re.compile(r"texto[_ ]?cota", re.I)
CAMADA_LOTE = re.compile(r"limite[_ ]?lote|^estrema$", re.I)


def _ocr(els, escala=100):
    from PIL import Image, ImageDraw
    import pytesseract
    pts = [(x, y) for e in els for p in e.pls for x, y in p if not (math.isnan(x) or math.isnan(y))]
    if not pts:
        return []
    x0, y0 = min(p[0] for p in pts) - 1, min(p[1] for p in pts) - 1
    x1, y1 = max(p[0] for p in pts) + 1, max(p[1] for p in pts) + 1
    W, H = int((x1 - x0) * escala), int((y1 - y0) * escala)
    if W * H > 9e7:                                  # desenho demasiado grande para esta escala : reduzir
        escala = escala * math.sqrt(9e7 / (W * H))
        W, H = int((x1 - x0) * escala), int((y1 - y0) * escala)
    im = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(im)
    for e in els:
        for p in e.pls:
            q = [((x - x0) * escala, (y - y0) * escala) for x, y in p if not (math.isnan(x) or math.isnan(y))]
            if len(q) >= 2:
                d.line(q, fill=0, width=3)
    r = pytesseract.image_to_data(im, config="--psm 11 -c tessedit_char_whitelist=0123456789.", output_type=pytesseract.Output.DICT)
    out = []
    for i, t in enumerate(r["text"]):
        if re.fullmatch(r"\d{2,4}\.\d{2}", t or ""):
            out.append((float(t), x0 + (r["left"][i] + r["width"][i] / 2) / escala, y0 + (r["top"][i] + r["height"][i] / 2) / escala))
    return out


def ler(z, lista) -> dict:
    """{"pontos": [(z, x, y)], "lote": Polygon, "cota_media": m, "cota_min", "cota_max", "n", "folha"} ou {}."""
    from shapely.geometry import MultiPoint, Point, Polygon
    from . import dwfx
    best = None
    for i in range(len(lista)):
        try:
            f = dwfx.ler(z, i, lista)
        except Exception:  # noqa: BLE001
            continue
        els = [e for e in f.elementos if CAMADA_COTA.search(e.camada or "") and e.pls]
        lote = []
        for rx in (r"limite[_ ]?lote", r"^estrema$"):              # o limite do lote primeiro ; a estrema só sem ele
            lote = [(x, y) for e in f.elementos if re.search(rx, e.camada or "", re.I) for p in e.pls for x, y in p
                    if not (math.isnan(x) or math.isnan(y))]
            if len(lote) >= 3:
                break
        n = sum(len(e.pls) for e in els)
        if els and len(lote) >= 3 and (best is None or n > best[0]):
            best = (n, i, f, els, lote)
    if not best:
        return {}
    _, i, f, els, lote = best
    L = MultiPoint(lote).convex_hull
    pts = [c for c in _ocr(els) if L.contains(Point(c[1], c[2]))]
    if len(pts) < 3 or L.area <= 0:
        return {}
    # superfície triangulada recortada pelo lote
    import numpy as np
    from scipy.spatial import Delaunay
    xy = np.array([(c[1], c[2]) for c in pts])
    tri = Delaunay(xy)
    num = den = 0.0
    for s in tri.simplices:
        t = Polygon(xy[s]).intersection(L)
        if t.area > 0:
            num += t.area * sum(pts[j][0] for j in s) / 3
            den += t.area
    if den <= 0:
        return {}
    zs = [c[0] for c in pts]
    return {"folha": f.nome, "indice": i, "pontos": pts, "lote": L, "area_lote": L.area, "n": len(pts),
            "cota_media": num / den, "cota_min": min(zs), "cota_max": max(zs), "area_triangulada": den}
