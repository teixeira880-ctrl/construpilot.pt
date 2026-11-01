"""Leitura das plantas de arquitetura (PDF vetorial) para a implantação da bomba de calor (PAC).

Plantas portuguesas (« Planta do R/C », « Piso 1 », « Cave », áreas « A = xx m² » / « Área: xx m² ») e francesas.

Lecture des plans d'architecte (PDF vectoriel) pour l'implantation PAC.

Pour chaque planche « Plan RDC / R+1 / R-1… » :
- niveau, échelle (cartouche « 1:50 » / « 50ème »), rendu raster de la planche ;
- pièces : étiquettes de l'architecte (nom + « S : xx,xx m² ») ;
- contour de chaque pièce dans le repère pixels de la planche : murs = traits sombres du PDF (les menuiseries et le mobilier
  sont en gris clair), petites ouvertures (portes) refermées, partage géodésique de l'espace libre entre étiquettes,
  puis ajustement à la surface écrite. L'écart surface mesurée / surface écrite est conservé comme contrôle.

Tout est déterministe : aucune IA, aucune cote inventée. Repère : pixels de la planche rendue à DPI, y vers le bas."""
from __future__ import annotations

import re
import unicodedata
from collections import deque
from dataclasses import dataclass, field

import numpy as np

DPI = 100                      # résolution de travail (masques, géométrie)
RENDER_DPI = 150               # résolution du fond de plan affiché
PIECE_MIN_M = 0.6              # tronçon de mur minimal pris en compte pour refermer une ouverture
OPENING_MAX_M = 6.0            # plus grande ouverture refermée (baie, porte de garage)
DOOR_MAX_M = 1.05              # ouverture ≤ : porte, toujours refermée
WALL_MAX_GRAY = 0.30           # traits « murs » : gris ≤ 30 % (noir)

LEVEL_RE = re.compile(r"\b(?:plan|planta)\s+(?:do|da|de|du)?\s*(r\s*/\s*c|r[ée]s[- ]do[- ]ch[ãa]o|piso\s*-?\s*\d|\d\s*[ºo°]\s*(?:piso|andar)|cave|s[óo]t[ãa]o|andar\s*\d+|r\s*[-+]\s*\d|rdc|rez[- ]de[- ]chauss[ée]e|sous[- ]sol|combles?|[ée]tage\s*\d*)", re.I)
AREA_RE = re.compile(r"(?:\bS\s*:|\bA\s*[=:]|\b[ÁA]rea\s*[:=]?)\s*(\d+(?:[.,]\d+)?)\s*m", re.I)
SCALE_RE = re.compile(r"(?:\b1\s*[:/]\s*(\d{2,3})\b|\b(\d{2,3})\s*[èe]me\b)", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def level_key(name: str) -> tuple[int, str]:
    """Ordem vertical : Cave < R/C < Piso 1 < Piso 2 … (R-1 < RDC < R+1 …)."""
    n = norm(name).replace(" ", "")
    m = re.search(r"r([-+])(\d)", n)
    if m:
        return (int(m.group(2)) * (1 if m.group(1) == "+" else -1), name)
    m = re.search(r"piso(-?\d)|(\d)[o°]?(?:piso|andar)|andar(\d)", n)
    if m:
        return (int(next(g for g in m.groups() if g is not None)), name)
    if "cave" in n or "sous-sol" in n or "soussol" in n:
        return (-1, name)
    if "sotao" in n or "comble" in n:
        return (9, name)
    m = re.search(r"etage(\d*)", n)
    if m:
        return (int(m.group(1) or 1), name)
    return (0, name)


def level_label(raw: str) -> str:
    n = norm(raw).replace(" ", "")
    m = re.search(r"r([-+])(\d)", n)
    if m:
        return f"R{m.group(1)}{m.group(2)}"
    if n.startswith("r/c") or "resdochao" in n or "res-do-chao" in n:
        return "R/C"
    m = re.search(r"piso(-?\d)|(\d)[o°]?(?:piso|andar)|andar(\d)", n)
    if m:
        k = int(next(g for g in m.groups() if g is not None))
        return "R/C" if k == 0 else ("Cave" if k < 0 else f"Piso {k}")
    if n.startswith("rdc") or "rez" in n:
        return "RDC"
    if "cave" in n or "sous" in n:
        return "Cave"
    if "sotao" in n or "comble" in n:
        return "Sótão"
    return raw.strip().title()


@dataclass
class Room:
    name: str
    area_label: float | None          # surface écrite par l'architecte (m²)
    label_xy: tuple[float, float]     # position de l'étiquette (px)
    mask: np.ndarray | None = None    # bool, même taille que la planche
    area_measured: float | None = None
    status: str = "ok"                # ok | ajusté | incertain

    @property
    def px(self):
        ys, xs = np.nonzero(self.mask)
        return xs, ys

    def bbox(self):
        xs, ys = self.px
        return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())

    def centroid(self):
        xs, ys = self.px
        return float(xs.mean()), float(ys.mean())


@dataclass
class Level:
    name: str                          # RDC, R+1 …
    page: int                          # 0-based
    scale: int                         # dénominateur (50 …)
    px_per_m: float                    # à DPI
    size: tuple[int, int]              # (w, h) px à DPI
    walls: np.ndarray                  # bool
    rooms: list[Room] = field(default_factory=list)
    footprint: np.ndarray | None = None
    notes: list[str] = field(default_factory=list)
    offset: tuple[float, float] = (0.0, 0.0)   # recalage sur le niveau de référence (px)
    openings: np.ndarray | None = None         # portes / baies refermées (pixels), pour ne rien poser devant

    def room(self, name: str) -> Room | None:
        k = norm(name)
        for r in self.rooms:
            if norm(r.name) == k:
                return r
        for r in self.rooms:
            if k and (k in norm(r.name) or norm(r.name) in k):
                return r
        return None

    def room_at(self, x: float, y: float) -> Room | None:
        xi, yi = int(round(x)), int(round(y))
        if not (0 <= yi < self.size[1] and 0 <= xi < self.size[0]):
            return None
        for r in self.rooms:
            if r.mask is not None and r.mask[yi, xi]:
                return r
        return None


# --------------------------------------------------------------------------------------------- pages / niveaux / échelle
def plan_pages(pdf: bytes) -> list[dict]:
    """Planches de plans d'étage avec étiquettes de pièces : [{page, level, scale}] (ordre vertical)."""
    import pymupdf
    out = []
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        for i, pg in enumerate(doc):
            text = pg.get_text()
            m = LEVEL_RE.search(text)
            if not m or len(AREA_RE.findall(text)) < 2:
                continue
            sc = [int(a or b) for a, b in SCALE_RE.findall(text) if 20 <= int(a or b) <= 200]
            out.append({"page": i, "level": level_label(m.group(1)), "scale": sc[0] if sc else 50})
    seen, uniq = set(), []
    for p in sorted(out, key=lambda p: level_key(p["level"])):
        if p["level"] not in seen:
            seen.add(p["level"])
            uniq.append(p)
    return uniq


def render_page(pdf: bytes, page: int, dpi: int = RENDER_DPI) -> bytes:
    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        return doc[page].get_pixmap(dpi=dpi).tobytes("png")


def _labels(pg, k: float) -> list[tuple[str, float | None, tuple[float, float]]]:
    """Étiquettes : nom (petit texte juste au-dessus) + « S : xx m² ». k = facteur pt → px."""
    spans = []
    for b in pg.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            for s in ln["spans"]:
                t = s["text"].strip()
                if t:
                    spans.append((t, s["bbox"], s["size"]))
    out = []
    for t, bb, size in spans:
        m = AREA_RE.search(t)
        if not m:
            continue
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        best, bd = None, 1e9
        pre = t[:m.start()].strip(" -–:|")
        if re.search(r"[A-Za-zÀ-ÿ]{2,}", pre):
            out.append((pre, float(m.group(1).replace(",", ".")), (cx * k, cy * k)))
            continue
        for t2, bb2, s2 in spans:
            if t2 == t or AREA_RE.search(t2) or re.fullmatch(r"[\d.,\s]+", t2):
                continue
            c2x, c2y = (bb2[0] + bb2[2]) / 2, (bb2[1] + bb2[3]) / 2
            dy = cy - c2y
            if 0 < dy < 3.5 * size and abs(c2x - cx) < 6 * size:
                d = dy + abs(c2x - cx) * 0.5
                if d < bd:
                    best, bd = t2, d
        out.append((best or f"Compartimento {len(out) + 1}", float(m.group(1).replace(",", ".")), (cx * k, cy * k)))
    return out


def _is_wall(col, fill, w) -> tuple[bool, bool]:
    st = col is not None and max(col) <= WALL_MAX_GRAY and w >= 0.1
    fi = fill is not None and max(fill) <= WALL_MAX_GRAY
    return st, fi


def _is_ink(col, fill, w) -> tuple[bool, bool]:
    """Traits d'ouvrage (murs, menuiseries, garde-corps) : gris jusqu'à 75 %, hors cotations rouges et végétation."""
    def ok(c):
        return c is not None and max(c) <= 0.75 and not (c[0] > 0.7 and c[1] < 0.6) and not (c[1] > c[0] + 0.25)
    return ok(col) and w >= 0.05, False


def _wall_mask(pg, dpi: int, pred=None) -> np.ndarray:
    import pymupdf
    pred = pred or _is_wall
    tmp = pymupdf.open()
    p2 = tmp.new_page(width=pg.rect.width, height=pg.rect.height)
    sh = p2.new_shape()
    for d in pg.get_drawings():
        col, fill, w = d.get("color"), d.get("fill"), d.get("width") or 0
        st, fi = pred(col, fill, w)
        if not (st or fi):
            continue
        for it in d["items"]:
            if it[0] == "l":
                sh.draw_line(it[1], it[2])
            elif it[0] == "c":
                sh.draw_bezier(it[1], it[2], it[3], it[4])
            elif it[0] == "re":
                sh.draw_rect(it[1])
            elif it[0] == "qu":
                sh.draw_quad(it[1])
        sh.finish(color=(0, 0, 0) if st else None, fill=(0, 0, 0) if fi else None, width=max(w, 0.6),
                  closePath=d.get("closePath", False))
    sh.commit()
    pix = p2.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY)
    a = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    tmp.close()
    return a < 128


# --------------------------------------------------------------------------------------------- segmentation des pièces
def _geodesic_partition(free: np.ndarray, seeds: list[tuple[int, int]]) -> tuple[np.ndarray, np.ndarray]:
    """BFS multi-sources (8-connexité) : étiquette de la graine la plus proche + distance géodésique."""
    h, w = free.shape
    lab = np.full((h, w), -1, np.int32)
    dist = np.full((h, w), -1, np.int32)
    q = deque()
    for i, (x, y) in enumerate(seeds):
        if 0 <= y < h and 0 <= x < w and free[y, x]:
            lab[y, x], dist[y, x] = i, 0
            q.append((x, y))
    while q:
        x, y = q.popleft()
        d, li = dist[y, x] + 1, lab[y, x]
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1), (x + 1, y + 1), (x - 1, y - 1), (x + 1, y - 1), (x - 1, y + 1)):
            if 0 <= nx < w and 0 <= ny < h and free[ny, nx] and lab[ny, nx] < 0:
                lab[ny, nx], dist[ny, nx] = li, d
                q.append((nx, ny))
    return lab, dist


def _nearest_free(free: np.ndarray, x: int, y: int, r: int = 25) -> tuple[int, int]:
    h, w = free.shape
    if 0 <= y < h and 0 <= x < w and free[y, x]:
        return x, y
    best, bd = (x, y), 1e9
    for yy in range(max(0, y - r), min(h, y + r + 1)):
        for xx in range(max(0, x - r), min(w, x + r + 1)):
            if free[yy, xx]:
                d = (xx - x) ** 2 + (yy - y) ** 2
                if d < bd:
                    best, bd = (xx, yy), d
    return best


def _grow(region: np.ndarray, seed: tuple[int, int], target: int, frac: float = 0.9) -> tuple[int, int, int, int]:
    """Rectangle axe-aligné grandi depuis `seed` tant que le bord reste dans `region` (≥ frac) et que l'aire < target."""
    h, w = region.shape
    x, y = seed
    x0 = x1 = x
    y0 = y1 = y
    blocked = [False] * 4
    while not all(blocked) and (x1 - x0 + 1) * (y1 - y0 + 1) < target:
        for side in range(4):
            if blocked[side]:
                continue
            if side == 0 and x0 > 0:
                strip, nx = region[y0:y1 + 1, x0 - 1], (x0 - 1, x1, y0, y1)
            elif side == 1 and x1 < w - 1:
                strip, nx = region[y0:y1 + 1, x1 + 1], (x0, x1 + 1, y0, y1)
            elif side == 2 and y0 > 0:
                strip, nx = region[y0 - 1, x0:x1 + 1], (x0, x1, y0 - 1, y1)
            elif side == 3 and y1 < h - 1:
                strip, nx = region[y1 + 1, x0:x1 + 1], (x0, x1, y0, y1 + 1)
            else:
                blocked[side] = True
                continue
            if strip.mean() >= frac:
                x0, x1, y0, y1 = nx
            else:
                blocked[side] = True
    return x0, y0, x1, y1


def _rect_cover(region: np.ndarray, seed: tuple[int, int], target: int, dist: np.ndarray, max_parts: int = 3,
                own: np.ndarray | None = None) -> np.ndarray:
    """Contour de pièce = 1 à `max_parts` rectangles (pièces rectangulaires, en L, en T) pris dans la zone de la pièce,
    jusqu'à la surface écrite. Le 1er part de l'étiquette ; les suivants des pixels voisins les plus proches (géodésique)."""
    import cv2
    out = np.zeros_like(region)
    if not region.any():
        return out
    sx, sy = seed
    if not region[sy, sx]:
        ys, xs = np.nonzero(region)
        j = int(np.argmin((xs - sx) ** 2 + (ys - sy) ** 2))
        sx, sy = int(xs[j]), int(ys[j])
    x0, y0, x1, y1 = _grow(region, (sx, sy), target)
    out[y0:y1 + 1, x0:x1 + 1] = region[y0:y1 + 1, x0:x1 + 1]
    for _ in range(max_parts - 1):
        deficit = target - int(out.sum())
        if deficit < 0.08 * target:
            break
        rest = (own if own is not None else region) & ~out
        ring = (cv2.dilate(out.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0) & rest
        if not ring.any():
            break
        ys, xs = np.nonzero(ring)
        d = dist[ys, xs]
        j = int(np.argmin(np.where(d >= 0, d, 1 << 30)))
        bx0, by0, bx1, by1 = _grow(rest, (int(xs[j]), int(ys[j])), deficit)
        part = np.zeros_like(region)
        part[by0:by1 + 1, bx0:bx1 + 1] = rest[by0:by1 + 1, bx0:bx1 + 1]
        if part.sum() < 0.02 * target:
            break
        out |= part
    return out


def _merge_closets(lv: "Level", leftover: np.ndarray, lab: np.ndarray, px_area: float) -> None:
    """Placards / dressings fermés sans étiquette, attenants à une pièce dont la surface mesurée est en déficit : rattachés."""
    import cv2
    n, cc = cv2.connectedComponents(leftover.astype(np.uint8), connectivity=4)
    for i in range(1, n):
        comp = cc == i
        a = comp.sum() * px_area
        if a < 0.4:
            continue
        near = cv2.dilate(comp.astype(np.uint8), np.ones((int(0.35 * lv.px_per_m) | 1,) * 2, np.uint8)) > 0
        for r in lv.rooms:
            deficit = (r.area_label or 0) - (r.area_measured or 0)
            if deficit >= 0.6 * a and (near & r.mask).any() and a <= deficit * 1.25:
                r.mask = r.mask | comp
                r.area_measured = float(r.mask.sum()) * px_area
                if r.area_label and abs(r.area_measured - r.area_label) <= 0.12 * r.area_label:
                    r.status = "ok"
                break


def read_level(pdf: bytes, page: int, level: str, scale: int, dpi: int = DPI) -> Level:
    import cv2
    import pymupdf
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        pg = doc[page]
        k = dpi / 72.0
        walls = _wall_mask(pg, dpi)
        ink = _wall_mask(pg, dpi, _is_ink)
        labels = _labels(pg, k)
    ppm = dpi / 25.4 * 1000.0 / scale
    lv = Level(level, page, scale, ppm, (walls.shape[1], walls.shape[0]), walls)
    if not labels:
        lv.notes.append("Nenhuma etiqueta de compartimento legível na planta.")
        return lv
    w8 = walls.astype(np.uint8)
    # murs pleins (hachures comblées), portes refermées
    solid = cv2.morphologyEx(w8, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    # ouvertures (portes, fenêtres, baies, porte de garage) : on relie uniquement des tronçons de mur ALIGNÉS
    # (murs horizontaux entre eux, murs verticaux entre eux) — jamais l'intérieur d'une pièce
    lp = max(3, int(round(PIECE_MIN_M * ppm)))
    lg = max(3, int(round(OPENING_MAX_M * ppm)))
    hz = cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones((1, lp), np.uint8))
    vt = cv2.morphologyEx(solid, cv2.MORPH_OPEN, np.ones((lp, 1), np.uint8))
    bridges = []
    for piece, ker in ((hz, np.ones((1, lg), np.uint8)), (vt, np.ones((lg, 1), np.uint8))):
        br = (cv2.morphologyEx(piece, cv2.MORPH_CLOSE, ker) > 0) & (solid == 0)
        n, cc, stats, _ = cv2.connectedComponentsWithStats(br.astype(np.uint8), 8)
        keep = np.zeros_like(br)
        for i in range(1, n):
            span = max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]) / ppm
            comp = cc == i
            if span <= DOOR_MAX_M:
                keep |= comp                                        # porte : toujours refermée
                continue
            # ouverture large : refermée seulement si une menuiserie (vitrage, porte de garage) est dessinée dans l'épaisseur
            band = cv2.dilate(comp.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
            horiz = stats[i, cv2.CC_STAT_WIDTH] >= stats[i, cv2.CC_STAT_HEIGHT]
            prof = (ink & band).any(axis=0 if horiz else 1)
            ext = band.any(axis=0 if horiz else 1)
            if ext.sum() and prof[ext].mean() >= 0.6:
                keep |= comp
        bridges.append(keep)
    closed = np.maximum(solid, (bridges[0] | bridges[1]).astype(np.uint8))
    lv.openings = bridges[0] | bridges[1]
    # emprise : enveloppe convexe des murs situés autour des étiquettes (baies vitrées et patios ouverts compris)
    xs = [xy[0] for _, _, xy in labels]
    ys = [xy[1] for _, _, xy in labels]
    mg = 4.0 * ppm
    x0, x1 = int(max(0, min(xs) - mg)), int(min(walls.shape[1], max(xs) + mg))
    y0, y1 = int(max(0, min(ys) - mg)), int(min(walls.shape[0], max(ys) + mg))
    zone = np.zeros_like(solid)
    zone[y0:y1, x0:x1] = solid[y0:y1, x0:x1]
    n, cc, stats, _ = cv2.connectedComponentsWithStats(zone, 8)
    keep = np.zeros_like(zone)
    min_len = 1.5 * ppm
    for i in range(1, n):
        if max(stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]) >= min_len:
            keep[cc == i] = 1
    foot = np.zeros_like(solid)
    pts = cv2.findNonZero(keep)
    if pts is not None:
        cv2.fillPoly(foot, [cv2.convexHull(pts)], 1)
    lv.footprint = foot.astype(bool)
    free = (closed == 0) & lv.footprint
    # pas de pièce dans un passage < 0,55 m (liserés entre vide et façade, jours entre traits)
    kn = max(3, int(round(0.55 * ppm)))
    free = cv2.morphologyEx(free.astype(np.uint8), cv2.MORPH_OPEN, np.ones((kn, kn), np.uint8)) > 0
    seeds = [_nearest_free(free, int(x), int(y)) for _, _, (x, y) in labels]
    lab, dist = _geodesic_partition(free, seeds)
    px_area = 1.0 / ppm ** 2
    covered = np.zeros_like(free)
    rooms: dict[int, Room] = {}
    # petites pièces d'abord : une grande pièce ouverte (séjour) ne mange pas la cuisine ou l'entrée voisines
    for i in sorted(range(len(labels)), key=lambda j: labels[j][1] or 0):
        name, area, xy = labels[i]
        target = int((area or 0) / px_area) or int((lab == i).sum())
        m = _rect_cover(free & ~covered, seeds[i], target, dist, own=(lab == i) & ~covered)
        meas = float(m.sum()) * px_area
        st = "ok" if not area or abs(meas - area) <= 0.12 * area else ("incertain" if meas < 0.8 * area else "ajusté")
        covered |= m
        rooms[i] = Room(name, area, xy, m, meas, st)
    lv.rooms = [rooms[i] for i in range(len(labels))]
    _merge_closets(lv, free & ~covered, lab, px_area)
    n_unc = [r.name for r in lv.rooms if r.status == "incertain"]
    if n_unc:
        lv.notes.append(f"{level} : contorno incerto para {', '.join(n_unc)} (área medida < 80 % da área escrita).")
    return lv


def align_levels(ref: Level, other: Level) -> tuple[float, float]:
    """Décalage (dx, dy) de `other` vers `ref` par corrélation de phase des emprises (planches parfois décalées)."""
    import cv2
    a = ref.footprint.astype(np.float32) if ref.footprint is not None else ref.walls.astype(np.float32)
    b = other.footprint.astype(np.float32) if other.footprint is not None else other.walls.astype(np.float32)
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    (dx, dy), resp = cv2.phaseCorrelate(a[:h, :w], b[:h, :w])
    if resp < 0.05 or abs(dx) > w / 4 or abs(dy) > h / 4:
        return 0.0, 0.0
    return -dx, -dy


def read_plans(pdf: bytes, pages: list[dict] | None = None) -> list[Level]:
    pages = pages or plan_pages(pdf)
    levels = [read_level(pdf, p["page"], p["level"], p.get("scale") or 50) for p in pages]
    levels = [lv for lv in levels if lv.rooms]
    if levels:
        ref = min(levels, key=lambda lv: abs(level_key(lv.name)[0]))
        for lv in levels:
            lv.offset = (0.0, 0.0) if lv is ref else align_levels(ref, lv)
    return levels
