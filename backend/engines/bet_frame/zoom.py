"""Agrandissements lisibles des grandes planches (lot 21).

Une planche A1 au 1:100 rendue à 1568 px de large : 1 px ≈ 5 cm réels, une cote de 2 mm de haut fait 4 px — illisible.
L'IA ne lit alors aucune cote et invente la géométrie. On repère donc le bâtiment dessiné (zone la plus dense en traits :
murs, hachures, mobilier) et on en fournit des agrandissements (vue entière du bâtiment + deux moitiés) où les cotes sont lisibles.
"""
from __future__ import annotations

import base64

import numpy as np


def _gray(pg, k: float) -> np.ndarray:
    import fitz
    pix = pg.get_pixmap(matrix=fitz.Matrix(k, k), colorspace=fitz.csGRAY, alpha=False)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def building_box(pg, cells: int = 48) -> tuple[float, float, float, float] | None:
    """Rectangle (points PDF) du bâtiment : composante connexe des cases les plus denses en encre, autour de la plus dense."""
    k = 1400 / max(pg.rect.width, pg.rect.height)
    g = _gray(pg, k)
    h, w = g.shape
    ink = (g < 140).astype(np.float32)
    cw, ch = max(1, w // cells), max(1, h // cells)
    ny, nx = h // ch, w // cw
    d = ink[:ny * ch, :nx * cw].reshape(ny, ch, nx, cw).mean(axis=(1, 3))
    d[:, :1] = d[:, -1:] = 0
    d[:1, :] = d[-1:, :] = 0                       # cadre et cartouche de bord
    if d.max() < 0.05:
        return None
    thr = 0.30 * float(np.percentile(d[d > 0], 99))
    mask = d >= thr
    sy, sx = np.unravel_index(int(np.argmax(np.where(mask, d, 0) * mask)), d.shape)
    seen = np.zeros_like(mask)
    stack = [(sy, sx)]
    while stack:                                   # composante connexe (8-voisins, tolère un trou d'une case)
        y, x = stack.pop()
        if y < 0 or x < 0 or y >= ny or x >= nx or seen[y, x] or not mask[y, x]:
            continue
        seen[y, x] = True
        for dy in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                if dy or dx:
                    stack.append((y + dy, x + dx))
    ys, xs = np.nonzero(seen)
    x0, x1 = xs.min() * cw, (xs.max() + 1) * cw
    y0, y1 = ys.min() * ch, (ys.max() + 1) * ch
    mx, my = 0.25 * (x1 - x0) + cw, 0.25 * (y1 - y0) + ch          # marge : chaînes de cotes extérieures
    x0, x1 = max(0, x0 - mx), min(w, x1 + mx)
    y0, y1 = max(0, y0 - my), min(h, y1 + my)
    if (x1 - x0) * (y1 - y0) > 0.8 * w * h:
        return None
    return (x0 / k, y0 / k, x1 / k, y1 / k)


def zooms(pdf: bytes, page: int, max_px: int = 1568) -> list[str]:
    """PNG base64 : bâtiment entier puis deux moitiés le long de la grande dimension (recouvrement 12 %)."""
    import fitz
    out = []
    with fitz.open(stream=pdf, filetype="pdf") as doc:
        pg = doc[page - 1]
        if max(pg.rect.width, pg.rect.height) < 1500:          # < A2 : la page entière est déjà lisible
            return out
        bb = building_box(pg)
        if not bb:
            return out
        x0, y0, x1, y1 = bb
        rects = [(x0, y0, x1, y1)]
        if x1 - x0 >= y1 - y0:
            mid, ov = (x0 + x1) / 2, 0.06 * (x1 - x0)
            rects += [(x0, y0, mid + ov, y1), (mid - ov, y0, x1, y1)]
        else:
            mid, ov = (y0 + y1) / 2, 0.06 * (y1 - y0)
            rects += [(x0, y0, x1, mid + ov), (x0, mid - ov, x1, y1)]
        for r in rects:
            clip = fitz.Rect(*r)
            k = max_px / max(clip.width, clip.height, 1)
            pix = pg.get_pixmap(matrix=fitz.Matrix(k, k), clip=clip, alpha=False)
            out.append(base64.b64encode(pix.tobytes("png")).decode())
    return out
