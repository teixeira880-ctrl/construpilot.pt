"""Wall bands on a raster plan (JPG/PNG) with OpenCV (Apache 2.0).

A scanned or exported image has no vectors, so every dimension carries the
pixel size as its uncertainty. The reader:

1. keeps the pixels of the wall fill tone (a grey band chosen by the user or
   taken from the darkest frequent grey that is not black text);
2. separates horizontal and vertical walls with long line openings, so an L
   or T of walls drawn as one blob becomes straight bands;
3. measures each band with its minimum rotated rectangle and passes it to the
   wall network engine, which removes the double count at the junctions.

The result is always an image estimate ("estimativa de imagem") with the
uncertainty in metres, never a measured value. Diagonal walls are not read.
"""
from __future__ import annotations

import cv2
import numpy as np

from bim_studio.clt_walls import Floor, analyse, rectangles_to_axes


def _runs(part, long_px):
    """Straight horizontal bands of a binary image: consecutive columns whose
    single vertical run keeps the same top and bottom (±1 px). A stepped
    blob (a thin wall ending in a thick pier) becomes two bands."""
    count, labels = cv2.connectedComponents(part, connectivity=4)
    out = []
    for k in range(1, count):
        ys, xs = np.nonzero(labels == k)
        if xs.max() - xs.min() + 1 < long_px:
            continue
        columns = {}
        for x, y in zip(xs, ys):
            t, b = columns.get(x, (y, y))
            columns[x] = (min(t, y), max(b, y))
        start, prev, ref = None, None, None
        for x in range(xs.min(), xs.max() + 2):
            cur = columns.get(x)
            if start is not None and (cur is None or abs(cur[0] - prev[0]) > 1 or abs(cur[1] - prev[1]) > 1):
                if x - start >= long_px:
                    out.append((start, ref[0], x, ref[1] + 1))
                start = None
            if cur is not None and start is None:
                start, ref = x, cur
            prev = cur
    return out


def detect(data: bytes, *, pixels_per_metre: float, height_m: float, grey=(70, 105), min_length_m=0.4,
           min_thickness_m=0.06, max_thickness_m=0.5, crop=None):
    if not 2 <= pixels_per_metre <= 2000:
        raise ValueError("Escala da imagem inválida (píxeis por metro).")
    image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Imagem ilegível.")
    if image.shape[0] * image.shape[1] > 40_000_000:
        raise ValueError("Imagem demasiado grande (máximo 40 Mpx).")
    if crop:
        x0, y0, x1, y1 = (int(v) for v in crop)
        image = image[y0:y1, x0:x1]
    else:
        x0 = y0 = 0
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    grey_img = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = ((grey_img >= grey[0]) & (grey_img <= grey[1]) & (hsv[:, :, 1] < 40)).astype(np.uint8) * 255
    ppm = pixels_per_metre
    min_t = max(1, int(round(min_thickness_m * ppm)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((min_t, min_t), np.uint8))
    long_px = max(3, int(round(min_length_m * ppm)))
    bands = []
    for horizontal in (True, False):
        kernel = np.ones((1, long_px), np.uint8) if horizontal else np.ones((long_px, 1), np.uint8)
        part = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        if not horizontal:
            part = part.T
        for a, b, c, d in _runs(part, long_px):
            rect = (a, b, c, d) if horizontal else (b, a, d, c)
            thick_px = (d - b)
            if min_thickness_m * ppm <= thick_px <= max_thickness_m * ppm:
                bands.append((rect[0] + x0, rect[1] + y0, rect[2] + x0, rect[3] + y0))
    # A thick blob is seen by both openings: keep the larger band only.
    unique = []
    for b in sorted(bands, key=lambda b: -(b[2] - b[0]) * (b[3] - b[1])):
        area = (b[2] - b[0]) * (b[3] - b[1])
        if any(max(0, min(b[2], u[2]) - max(b[0], u[0])) * max(0, min(b[3], u[3]) - max(b[1], u[1])) > 0.5 * area
               for u in unique):
            continue
        unique.append(b)
    rects = [[(a / ppm, -b / ppm), (c / ppm, -b / ppm), (c / ppm, -d / ppm), (a / ppm, -d / ppm)]
             for a, b, c, d in unique]
    pixel_m = 1 / ppm
    walls, rejected = rectangles_to_axes(rects, height_m=height_m, nominal_mm=tuple(range(50, 510, 10)),
                                         tolerance_mm=pixel_m * 1000, prefix="I",
                                         source=f"imagem, {ppm:.2f} px/m, ±{pixel_m * 1000:.0f} mm por medida")
    h_img, w_img = grey_img.shape
    result = {
        "estado": "estimativa de imagem",
        "pixel_m": round(pixel_m, 4),
        "incerteza": f"cada comprimento e espessura ±{pixel_m * 1000:.0f} mm (1 píxel); "
                     "não cumpre o limite de 2 % das medições vetoriais",
        "paredes": [w.model_dump() for w in walls],
        "bandas_px": [list(map(int, u)) for u in unique],
        "rejeitados": rejected,
        "imagem_px": [int(w_img), int(h_img)],
    }
    if walls:
        result["analise"] = analyse(Floor(name="Imagem", walls=walls))
    return result
