"""Leitura dos vetores de uma página PDF : segmentos traçados, polígonos preenchidos e palavras, em pontos PDF com origem no canto
superior esquerdo. Usa PyMuPDF ; se não estiver instalado, recorre ao pdfplumber (mesmo resultado, só para ambientes sem PyMuPDF)."""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import numpy as np


@dataclass
class Folha:
    largura: float
    altura: float
    segs: np.ndarray                                   # N×4 : x0, y0, x1, y1
    seg_lum: np.ndarray                                # luminância do traço de cada segmento (0 preto … 1 branco)
    seg_trac: np.ndarray                               # True se o segmento foi traçado com padrão de interrompido (dash)
    cheios: list = field(default_factory=list)         # polígonos preenchidos a escuro (n×2)
    palavras: list = field(default_factory=list)       # (x0, y0, x1, y1, texto)
    texto: str = ""
    motor: str = ""


def _lum(c) -> float:
    """Luminância 0 (preto) … 1 (branco) de uma cor PDF (cinzento, RGB ou CMYK)."""
    if c is None:
        return 1.0
    if isinstance(c, (int, float)):
        return float(c)
    c = [float(v) for v in c]
    if len(c) == 1:
        return c[0]
    if len(c) == 3:
        return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    if len(c) == 4:
        return max(0.0, 1.0 - min(1.0, 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2] + c[3]))
    return 1.0


def _bezier(p0, p1, p2, p3, n=6):
    t = np.linspace(0, 1, n + 1)[:, None]
    return ((1 - t) ** 3) * p0 + 3 * ((1 - t) ** 2) * t * p1 + 3 * (1 - t) * t * t * p2 + (t ** 3) * p3


ESCURO = 0.35          # um preenchimento mais escuro do que isto é uma secção cortada (trama cheia)


def _fitz(data: bytes, pagina: int) -> Folha:
    import fitz
    doc = fitz.open(stream=data, filetype="pdf")
    pg = doc[pagina]
    m = pg.rotation_matrix if pg.rotation else None

    def P(p):
        if m is not None:
            p = fitz.Point(p) * m
        return (float(p[0]), float(p[1]))

    segs, lums, tracs, cheios = [], [], [], []
    for d in pg.get_drawings():
        tipo = d.get("type") or ""
        traco = "s" in tipo and d.get("color") is not None
        cheio = "f" in tipo and d.get("fill") is not None and _lum(d.get("fill")) < ESCURO
        sub, atual = [], []
        for it in d.get("items") or []:
            k = it[0]
            if k == "l":
                pts = [P(it[1]), P(it[2])]
            elif k == "c":
                pts = [tuple(v) for v in _bezier(*[np.array(P(q)) for q in it[1:5]])]
            elif k == "re":
                r = it[1]
                pts = [P(r.tl), P(r.tr), P(r.br), P(r.bl), P(r.tl)]
            elif k == "qu":
                q = it[1]
                pts = [P(q.ul), P(q.ur), P(q.lr), P(q.ll), P(q.ul)]
            else:
                continue
            if atual and (abs(atual[-1][0] - pts[0][0]) > 0.01 or abs(atual[-1][1] - pts[0][1]) > 0.01 or k in ("re", "qu")):
                sub.append(atual)
                atual = []
            atual = atual[:-1] + list(pts) if atual else list(pts)
        if atual:
            sub.append(atual)
        for pts in sub:
            if traco:
                segs += [(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])]
                lums += [_lum(d.get("color"))] * (len(pts) - 1)
                tracs += [bool(re.search(r"\d", (d.get("dashes") or "").split("]")[0]))] * (len(pts) - 1)
            if cheio and len(pts) >= 3:
                cheios.append(np.array(pts, dtype=np.float32))
    palavras = []
    for w in pg.get_text("words"):
        a, b = P((w[0], w[1])), P((w[2], w[3]))
        palavras.append((min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]), str(w[4])))
    r = pg.rect
    return Folha(float(r.width), float(r.height), np.array(segs, dtype=np.float64).reshape(-1, 4), np.array(lums, dtype=np.float64),
                 np.array(tracs, dtype=bool), cheios, palavras, pg.get_text("text"), "pymupdf")


def _plumber(data: bytes, pagina: int) -> Folha:
    import pdfplumber
    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pg = pdf.pages[pagina]
        segs, lums, tracs, cheios = [], [], [], []
        for o in list(pg.lines) + list(pg.curves) + list(pg.rects):
            pts = o.get("pts")
            if not pts or o.get("object_type") == "rect":
                pts = [(o["x0"], o["top"]), (o["x1"], o["top"]), (o["x1"], o["bottom"]), (o["x0"], o["bottom"]), (o["x0"], o["top"])]
            if o.get("fill") and _lum(o.get("non_stroking_color")) < ESCURO and len(pts) >= 3:
                cheios.append(np.array(pts, dtype=np.float32))
            if o.get("stroke", True) and not (o.get("fill") and not o.get("stroke")):
                segs += [(a[0], a[1], b[0], b[1]) for a, b in zip(pts, pts[1:])]
                lums += [_lum(o.get("stroking_color"))] * (len(pts) - 1)
                dash = o.get("dash")
                tracs += [bool(dash and dash[0])] * (len(pts) - 1)
        palavras = []
        for w in pg.extract_words(x_tolerance=1.5, y_tolerance=1.5, extra_attrs=["upright"]):
            t = w["text"]
            palavras.append((w["x0"], w["top"], w["x1"], w["bottom"], t if w.get("upright", True) else "↻" + t))
        return Folha(float(pg.width), float(pg.height), np.array(segs, dtype=np.float64).reshape(-1, 4), np.array(lums, dtype=np.float64),
                     np.array(tracs, dtype=bool), cheios, palavras, pg.extract_text() or "", "pdfplumber")


def n_paginas(data: bytes) -> int:
    try:
        import fitz
        return fitz.open(stream=data, filetype="pdf").page_count
    except ImportError:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            return len(pdf.pages)


def ler(data: bytes, pagina: int = 0) -> Folha:
    try:
        import fitz  # noqa: F401
    except ImportError:
        return _plumber(data, pagina)
    return _fitz(data, pagina)
