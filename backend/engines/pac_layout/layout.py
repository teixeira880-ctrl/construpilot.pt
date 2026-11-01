"""Implantation d'une PAC air-eau réversible : plancher chauffant-rafraîchissant + ventilo-convecteurs plafond.

Entrée : niveaux lus par `plans.read_plans` (pièces en pixels de planche). Sortie : dict sérialisable (équipements, boucles,
ventilo-convecteurs, réseaux, contrôles) — tout en pixels de la planche de chaque niveau (DPI de travail) + valeurs en m / m².

Règles (pré-dimensionnement, à confirmer par l'étude thermique RE2020) :
- plancher : pas 10 cm en pièces d'eau, 15 cm ailleurs ; boucle ≤ 120 m amenées comprises ; tube PER Ø16 ;
- ventilo-convecteurs (eau ≈ 7 °C) : séjour / bureau / bibliothèque, chambres, cuisine ; 1 unité ≤ 25 m², 2 ≤ 45 m², sinon 3 ;
- condensats : pompe de relevage par unité vers la pièce d'eau la plus proche ;
- module hydraulique + ballon tampon : local technique > buanderie > cellier > entrée/dégagement > garage (hors gel) ;
- collecteur : à côté du module ; aux étages, à l'aplomb de la colonne montante (gaine) dans une circulation ;
- groupe extérieur : contre une façade pleine (jamais devant une porte, une baie ou une porte de garage), au plus près du module.
Chaque position peut être imposée par l'utilisateur (pièce + mur commun avec une autre pièce ou côté)."""
from __future__ import annotations

import math
import re

import numpy as np

from .plans import Level, Room, level_key, norm

L_MAX = 120.0
EQ_HALF_M = 0.30

TYPES = [
    ("exterieur", r"terrasse|balcon|patio|loggia|porche|\bcour\b|jardin|terraco|varanda|alpendre|logradouro|quintal"),
    ("vide", r"\bvide\b|tremie|\bvazio\b|pe direito duplo"),
    ("escalier", r"escalier|\besc\b|escada"),
    ("garage", r"garage|carport|\babri\b|garagem|aparcamento|estacionamento"),
    ("buanderie", r"buanderie|lingerie|lavandaria|tratamento de roupa|engomadoria"),
    ("technique", r"local tech|chaufferie|\btechnique\b|^lt\b|area tecnica|casa das maquinas|zona tecnica"),
    ("cellier", r"cellier|\bcave\b|remise|atelier|arrecadacao|adega|oficina"),
    ("sdb", r"\bsd[bea]\b|salle d.?eau|salle de bain|douche|casa de banho|instalacao sanitaria|\bi\.? ?s\b|\bisw?\b"),
    ("wc", r"\bwc\b|toilette|lavabo"),
    ("cuisine", r"cuisine|kitchen|kitchenette|cozinha|copa"),
    ("sejour", r"sejour|salon|living|salle a manger|\bsam\b|piece de vie|biblioth|bureau|jeux|mezzanine|veranda|\bsala\b|escritorio|estar|jantar|biblioteca"),
    ("chambre", r"chambre|\bcb ?\d*\b|\bch ?\d+\b|\bsuite\b|quarto|\bq ?\d+\b"),
    ("circulation", r"entree|\bhall\b|degagement|\bdgt\b|couloir|palier|circulation|\bsas\b|entrada|corredor|circulacao|atrio|patamar|vestibulo"),
    ("rangement", r"dressing|placard|rangement|closet|roupeiro|despensa|arrumos"),
]
HEATED = {"sejour", "chambre", "cuisine", "sdb", "wc", "buanderie", "circulation", "rangement", "autre"}
VC_TYPES = {"sejour", "chambre", "cuisine"}
WET = {"sdb", "wc", "buanderie", "cuisine"}
MODULE_PRIORITY = ["technique", "buanderie", "cellier", "circulation", "garage"]
SIDES = {"nord": "top", "haut": "top", "sud": "bottom", "bas": "bottom", "ouest": "left", "gauche": "left",
         "est": "right", "droite": "right", "norte": "top", "cima": "top", "sul": "bottom", "baixo": "bottom",
         "oeste": "left", "esquerda": "left", "este": "right", "leste": "right", "direita": "right"}


def room_type(name: str) -> str:
    n = norm(name)
    for t, rx in TYPES:
        if re.search(rx, n):
            return t
    return "autre"


# --------------------------------------------------------------------------------------------- géométrie
def _mask_pts(mask: np.ndarray):
    ys, xs = np.nonzero(mask)
    return xs, ys


def _nearest_in(mask: np.ndarray, x: float, y: float) -> tuple[float, float]:
    xs, ys = _mask_pts(mask)
    if xs.size == 0:
        return x, y
    j = int(np.argmin((xs - x) ** 2 + (ys - y) ** 2))
    return float(xs[j]), float(ys[j])


def _inset(mask: np.ndarray, x: float, y: float, d: float) -> tuple[float, float]:
    """Point du masque le plus proche de (x, y) situé à ≥ d px des bords (sinon le plus intérieur possible)."""
    import cv2
    dt = cv2.distanceTransform(mask.astype(np.uint8), cv2.DIST_L2, 3)
    ok = dt >= min(d, float(dt.max()) * 0.9)
    return _nearest_in(ok, x, y)


def _band(mask: np.ndarray, side: str, width: float) -> np.ndarray:
    xs, ys = _mask_pts(mask)
    out = np.zeros_like(mask)
    if xs.size == 0:
        return out
    if side == "top":
        sel = ys <= ys.min() + width
    elif side == "bottom":
        sel = ys >= ys.max() - width
    elif side == "left":
        sel = xs <= xs.min() + width
    else:
        sel = xs >= xs.max() - width
    out[ys[sel], xs[sel]] = True
    return out


def _shared_band(mask: np.ndarray, other: np.ndarray, reach: float) -> np.ndarray:
    import cv2
    k = int(reach) | 1
    near = cv2.dilate(other.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
    return mask & near


def _corners(mask: np.ndarray) -> list[tuple[float, float]]:
    xs, ys = _mask_pts(mask)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    return [_nearest_in(mask, cx, cy) for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1))]


def manhattan(a, b, first="h"):
    (ax, ay), (bx, by) = a, b
    return [a, (bx, ay), b] if first == "h" else [a, (ax, by), b]


def route(lv: Level, a, b):
    """Tracé orthogonal (L) qui reste le plus possible DANS les pièces (évite de passer par un patio ou l'extérieur)."""
    inside = getattr(lv, "_inside", None)
    if inside is None:
        inside = np.zeros(lv.walls.shape, bool)
        for r in lv.rooms:
            if r.mask is not None and room_type(r.name) not in ("exterieur", "vide"):
                inside |= r.mask
        inside |= lv.walls
        lv._inside = inside
    best, bs = None, -1.0
    for first in ("h", "v"):
        pth = manhattan(a, b, first)
        n = ok = 0
        for p, q in zip(pth, pth[1:]):
            steps = int(max(abs(q[0] - p[0]), abs(q[1] - p[1])) // 4) + 1
            for t in np.linspace(0, 1, steps):
                x, y = int(p[0] + (q[0] - p[0]) * t), int(p[1] + (q[1] - p[1]) * t)
                n += 1
                if 0 <= y < inside.shape[0] and 0 <= x < inside.shape[1] and inside[y, x]:
                    ok += 1
        sc = ok / max(1, n)
        if sc > bs + 1e-6:
            best, bs = pth, sc
    return best


def _len_m(path, ppm):
    return sum(abs(p[0] - q[0]) + abs(p[1] - q[1]) for p, q in zip(path, path[1:])) / ppm


def loops_for(area: float, pitch: float, dist_m: float) -> tuple[int, float]:
    n = 1
    while area / pitch / n + 2 * dist_m > L_MAX and n < 12:
        n += 1
    return n, area / pitch / n + 2 * dist_m


# --------------------------------------------------------------------------------------------- placement
def _heated_centroid(lv: Level) -> tuple[float, float]:
    pts = [(r.centroid(), r.area_label or 1) for r in lv.rooms if room_type(r.name) in HEATED and r.mask is not None and r.mask.any()]
    if not pts:
        return lv.size[0] / 2, lv.size[1] / 2
    w = sum(a for _, a in pts)
    return sum(c[0] * a for c, a in pts) / w, sum(c[1] * a for c, a in pts) / w


def _place_in_room(lv: Level, room: Room, near: Room | None, side: str | None, toward: tuple[float, float]) -> tuple[float, float]:
    """Point d'un équipement mural dans `room` : le long du mur commun avec `near`, ou du côté `side`, sinon dans l'angle
    de la pièce le plus proche de `toward` ; décalé de l'épaisseur de l'équipement vers l'intérieur."""
    ins = EQ_HALF_M * lv.px_per_m
    band = None
    if near is not None and near.mask is not None:
        band = _shared_band(room.mask, near.mask, 0.6 * lv.px_per_m)
        if not band.any():
            band = None
    if band is None and side:
        band = _band(room.mask, SIDES.get(norm(side), "top"), 0.35 * lv.px_per_m)
    if band is not None:
        # extrémité de la bande la plus proche d'un angle de la pièce (on range l'équipement dans l'angle)
        cs = _corners(room.mask)
        xs, ys = _mask_pts(band)
        best = min(((float(x), float(y)) for x, y in zip(xs, ys)),
                   key=lambda p: min(math.hypot(p[0] - c[0], p[1] - c[1]) for c in cs) * 3 + math.hypot(p[0] - toward[0], p[1] - toward[1]) * 0.2)
        return _inset(room.mask, *best, ins)
    c = min(_corners(room.mask), key=lambda p: math.hypot(p[0] - toward[0], p[1] - toward[1]))
    return _inset(room.mask, *c, ins)


def _next_to(lv: Level, room: Room, p: tuple[float, float], gap_m: float = 0.75) -> tuple[float, float]:
    """Position à côté de p, le long du mur, dans la direction où la pièce est la plus longue."""
    xs, ys = _mask_pts(room.mask)
    dx = 1 if abs(p[0] - xs.min()) < abs(p[0] - xs.max()) else -1
    dy = 1 if abs(p[1] - ys.min()) < abs(p[1] - ys.max()) else -1
    g = gap_m * lv.px_per_m
    cand = [(p[0], p[1] + dy * g), (p[0] + dx * g, p[1])] if (ys.max() - ys.min()) >= (xs.max() - xs.min()) else \
        [(p[0] + dx * g, p[1]), (p[0], p[1] + dy * g)]
    for c in cand:
        xi, yi = int(c[0]), int(c[1])
        if 0 <= yi < lv.size[1] and 0 <= xi < lv.size[0] and room.mask[yi, xi]:
            return c
    return _inset(room.mask, *cand[0], EQ_HALF_M * lv.px_per_m)


def _outdoor_candidates(lv: Level) -> np.ndarray:
    """Pixels extérieurs à 0,3–0,8 m d'un mur, hors pièces, hors ouvertures (± 1 m) et à ≤ 1,5 m de l'emprise (pas chez le voisin)."""
    import cv2
    ppm = lv.px_per_m
    rooms = np.zeros(lv.walls.shape, bool)
    for r in lv.rooms:
        if r.mask is not None:
            rooms |= r.mask
    solid = lv.walls.astype(np.uint8)
    dt = cv2.distanceTransform((solid == 0).astype(np.uint8), cv2.DIST_L2, 3)
    cand = (dt >= 0.30 * ppm) & (dt <= 0.80 * ppm) & ~rooms & ~lv.walls
    if lv.footprint is not None:
        k = int(1.5 * ppm) | 1
        near_fp = cv2.dilate(lv.footprint.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
        cand &= near_fp
    if getattr(lv, "openings", None) is not None and lv.openings.any():
        k = int(1.6 * ppm) | 1
        cand &= ~(cv2.dilate(lv.openings.astype(np.uint8), np.ones((k, k), np.uint8)) > 0)
    # extérieur = hors emprise, ou cour / patio dans l'emprise mais ouvert sur l'extérieur (≥ 2,5 × 2,5 m) — jamais une cage
    # d'escalier ou un recoin intérieur
    hull = lv.footprint if lv.footprint is not None else np.zeros_like(cand)
    inside_open = ~rooms & ~lv.walls & hull
    if getattr(lv, "openings", None) is not None:
        inside_open &= ~lv.openings
    k = int(2.5 * ppm) | 1
    opened = cv2.morphologyEx(inside_open.astype(np.uint8), cv2.MORPH_OPEN, np.ones((k, k), np.uint8))
    n, cc = cv2.connectedComponents(opened, connectivity=4)
    outside = ~hull
    touch = cv2.dilate(outside.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0
    courts = np.zeros_like(cand)
    for i in range(1, n):
        comp = cc == i
        if (comp & touch).any():
            courts |= comp
    # dans une cour : à ≥ 1,2 m des pièces chauffées (bruit, vitrages ; écarte aussi les circulations intérieures sans étiquette)
    heated = np.zeros_like(cand)
    for r in lv.rooms:
        if r.mask is not None and room_type(r.name) in HEATED:
            heated |= r.mask
    far = cv2.distanceTransform((~heated).astype(np.uint8), cv2.DIST_L2, 3) >= 1.2 * ppm
    return cand & (outside | (courts & far))


def _outdoor(lv: Level, module_xy, against: Room | None, side: str | None) -> tuple[float, float] | None:
    cand = _outdoor_candidates(lv)
    if against is not None and against.mask is not None:
        import cv2
        k = int(1.3 * lv.px_per_m) | 1
        cand &= cv2.dilate(against.mask.astype(np.uint8), np.ones((k, k), np.uint8)) > 0
        if side:
            x0, y0, x1, y1 = against.bbox()
            xs, ys = _mask_pts(cand)
            s = SIDES.get(norm(side), "top")
            sel = {"top": ys < y0, "bottom": ys > y1, "left": xs < x0, "right": xs > x1}[s]
            keep = np.zeros_like(cand)
            keep[ys[sel], xs[sel]] = True
            cand = keep
    xs, ys = _mask_pts(cand)
    if xs.size == 0:
        return None
    # pénalité près des chambres (bruit)
    pen = np.zeros(xs.size)
    for r in lv.rooms:
        if room_type(r.name) == "chambre" and r.mask is not None:
            cx, cy = r.centroid()
            near = np.hypot(xs - cx, ys - cy) < 3.0 * lv.px_per_m
            pen[near] += 3.0 * lv.px_per_m
    # pas dans un angle rentrant (murs sur deux côtés à moins de 1 m) : soufflage gêné, mur nommé ambigu
    if xs.size > 4000:
        sel = np.linspace(0, xs.size - 1, 4000).astype(int)
        xs, ys, pen = xs[sel], ys[sel], pen[sel]
    reach = int(1.0 * lv.px_per_m)
    h, w = lv.walls.shape
    for j in range(xs.size):
        x, y = int(xs[j]), int(ys[j])
        hits = 0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            for k in range(3, reach, 3):
                xx, yy = x + dx * k, y + dy * k
                if not (0 <= xx < w and 0 <= yy < h):
                    break
                if lv.walls[yy, xx]:
                    hits += 1
                    break
        if hits >= 2:
            pen[j] += 1.5 * lv.px_per_m
    # contre un local non chauffé (garage, cellier) : préférable (bruit, vibrations)
    for j in range(xs.size):
        r = _behind_wall(lv, (xs[j], ys[j]))
        if r is not None and room_type(r.name) in ("garage", "cellier", "technique"):
            pen[j] -= 1.0 * lv.px_per_m
    d = np.hypot(xs - module_xy[0], ys - module_xy[1]) + pen
    j = int(np.argmin(d))
    return float(xs[j]), float(ys[j])


def _behind_wall(lv: Level, p) -> Room | None:
    """Pièce derrière le mur contre lequel l'équipement extérieur est posé (mur le plus proche dans les 4 directions)."""
    h, w = lv.walls.shape
    best = None
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        for k in range(1, int(1.2 * lv.px_per_m)):
            x, y = int(p[0] + dx * k), int(p[1] + dy * k)
            if not (0 <= x < w and 0 <= y < h):
                break
            if lv.walls[y, x]:
                if best is None or k < best[0]:
                    best = (k, dx, dy, x, y)
                break
    if best is None:
        return None
    _, dx, dy, x, y = best
    for k in range(1, int(1.5 * lv.px_per_m)):
        r = lv.room_at(x + dx * k, y + dy * k)
        if r is not None:
            return r
    return None


def _vc_points(lv: Level, room: Room, n: int) -> list[tuple[float, float]]:
    import cv2
    m = room.mask.astype(np.uint8)
    xs, ys = _mask_pts(room.mask)
    parts = [room.mask]
    if n > 1:
        horiz = (xs.max() - xs.min()) >= (ys.max() - ys.min())
        lo, hi = (xs.min(), xs.max()) if horiz else (ys.min(), ys.max())
        cuts = [lo + (hi - lo) * k / n for k in range(n + 1)]
        parts = []
        for a, b in zip(cuts, cuts[1:]):
            sel = np.zeros_like(room.mask)
            if horiz:
                sel[:, int(a):int(b) + 1] = True
            else:
                sel[int(a):int(b) + 1, :] = True
            parts.append(room.mask & sel)
    pts = []
    for p in parts:
        if not p.any():
            continue
        dt = cv2.distanceTransform(p.astype(np.uint8), cv2.DIST_L2, 3)
        y, x = np.unravel_index(int(np.argmax(dt)), dt.shape)
        pts.append((float(x), float(y)))
    del m
    return pts


# --------------------------------------------------------------------------------------------- moteur
def _find(levels: list[Level], level_name: str | None, room_name: str | None):
    lvs = [lv for lv in levels if not level_name or norm(lv.name) == norm(level_name)] or levels
    for lv in lvs:
        r = lv.room(room_name) if room_name else None
        if r is not None:
            return lv, r
    return (lvs[0], None) if lvs else (None, None)


def compute(levels: list[Level], placements: list[dict] | None = None) -> dict:
    placements = placements or []
    pl = {}
    vc_count = {}
    for p in placements:
        eq = norm(p.get("equipment") or "").replace(" ", "_")
        if eq == "vc":
            if p.get("room") and p.get("count") is not None:
                vc_count[(norm(p.get("level") or ""), norm(p["room"]))] = max(0, int(p["count"]))
        elif eq:
            key = eq if eq != "collecteur" else f"collecteur:{norm(p.get('level') or '')}"
            pl[key] = p
    levels = sorted(levels, key=lambda lv: level_key(lv.name))
    heated_levels = [lv for lv in levels if any(room_type(r.name) in HEATED for r in lv.rooms)]
    if not heated_levels:
        return {"ok": False, "error": "Nenhum compartimento aquecido reconhecido nas plantas."}
    base = min(heated_levels, key=lambda lv: abs(level_key(lv.name)[0]))
    checks, decisions = [], []
    out_levels = {lv.name: {"equipment": [], "loops": [], "vc": [], "networks": [], "thermostats": [], "rooms": []} for lv in levels}

    def eq(lv, kind, ident, xy, label, room=None):
        out_levels[lv.name]["equipment"].append({"kind": kind, "id": ident, "x": xy[0], "y": xy[1], "label": label,
                                                 "room": room.name if room else None})

    # ---- module hydraulique + ballon tampon
    toward = _heated_centroid(base)
    p = pl.get("module")
    mod_room = None
    if p:
        lvm, mod_room = _find(levels, p.get("level"), p.get("room"))
        if mod_room is not None:
            base = lvm
            near = base.room(p["near_room"]) if p.get("near_room") else None
            mod_xy = _place_in_room(base, mod_room, near, p.get("side"), toward)
            decisions.append(f"Módulo hidráulico + depósito de inércia : {mod_room.name} ({base.name})" +
                             (f", contra a parede comum com {near.name}" if near else (f", lado {p['side']}" if p.get("side") else "")) + " — posição imposta.")
    if mod_room is None:
        for t in MODULE_PRIORITY:
            cands = [r for r in base.rooms if room_type(r.name) == t and r.mask is not None and r.mask.any()]
            if t == "circulation":
                cands.sort(key=lambda r: (0 if re.search(r"entree|entrada|hall|vestibulo", norm(r.name)) else 1, -(r.area_label or 0)))
            if cands:
                mod_room = cands[0]
                break
        if mod_room is None:
            mod_room = max(base.rooms, key=lambda r: r.area_label or 0)
        mod_xy = _place_in_room(base, mod_room, None, None, toward)
        decisions.append(f"Módulo hidráulico + depósito de inércia : {mod_room.name} ({base.name}), canto mais próximo do centro dos compartimentos aquecidos — proposta automática.")
    if room_type(mod_room.name) in ("garage", "cellier"):
        checks.append(f"Módulo em « {mod_room.name} » (não aquecido) : proteção anticongelamento (glicol ou isolamento) ; em alternativa, colocá-lo no volume aquecido.")
    else:
        checks.append(f"Armário técnico em « {mod_room.name} » : cerca de 0,8 × 0,9 m em planta com acesso frontal ; manter uma passagem livre suficiente.")
    eq(base, "module", "module", mod_xy, "MH\n+\nBT", mod_room)

    # ---- collecteur du niveau de base
    p = pl.get(f"collecteur:{norm(base.name)}") or pl.get("collecteur:")
    coll = {}
    if p:
        _, cr = _find([base], base.name, p.get("room"))
        cr = cr or mod_room
        near = base.room(p["near_room"]) if p.get("near_room") else None
        cxy = _place_in_room(base, cr, near, p.get("side"), mod_xy) if (near or p.get("side") or cr is not mod_room) else _next_to(base, cr, mod_xy)
        decisions.append(f"Coletor {base.name} : {cr.name} — posição imposta.")
    else:
        cr = mod_room
        cxy = _next_to(base, mod_room, mod_xy)
    coll[base.name] = (cxy, cr)

    # ---- colonne montante + collecteurs des autres niveaux
    riser_ref = (mod_xy[0] + (0.40 * base.px_per_m if cxy[0] <= mod_xy[0] + 1 else -0.40 * base.px_per_m), mod_xy[1] + 0.45 * base.px_per_m)
    others = [lv for lv in heated_levels if lv is not base]
    risers = {}
    if others:
        eq(base, "colonne", "colonne", riser_ref, "Colonne", mod_room)
        risers[base.name] = riser_ref
    for lv in others:
        bx, by = base.offset
        ox, oy = lv.offset
        rxy = (riser_ref[0] + bx - ox, riser_ref[1] + by - oy)
        here = lv.room_at(*rxy)
        p = pl.get(f"collecteur:{norm(lv.name)}")
        if p and p.get("room"):
            _, cr = _find([lv], lv.name, p.get("room"))
            near = lv.room(p["near_room"]) if p.get("near_room") else None
            cxy = _place_in_room(lv, cr, near, p.get("side"), rxy) if cr else rxy
            decisions.append(f"Coletor {lv.name} : {cr.name if cr else '?'} — posição imposta.")
        elif here is not None and room_type(here.name) in ("circulation", "rangement"):
            cr, cxy = here, _next_to(lv, here, _nearest_in(here.mask, *rxy), 0.35)
        else:
            circ = [r for r in lv.rooms if room_type(r.name) in ("circulation", "rangement") and r.mask is not None and r.mask.any()]
            if circ:
                cr = min(circ, key=lambda r: math.hypot(*(np.subtract(_nearest_in(r.mask, *rxy), rxy))))
                cxy = _inset(cr.mask, *_nearest_in(cr.mask, *rxy), EQ_HALF_M * lv.px_per_m)
                if here is not None:
                    checks.append(f"{lv.name} : a coluna montante chega a « {here.name} » — courete a revestir no canto ou deslocar o módulo.")
            else:
                cr = here or max(lv.rooms, key=lambda r: r.area_label or 0)
                cxy = _inset(cr.mask, *_nearest_in(cr.mask, *rxy), EQ_HALF_M * lv.px_per_m)
        coll[lv.name] = (cxy, cr)
        risers[lv.name] = rxy
        eq(lv, "colonne", "colonne", rxy, "Colonne", here)
    if others:
        checks.append("Courete da coluna montante : negativo / atravessamento da laje a coordenar com o projetista de estruturas e o arquiteto.")

    # ---- groupe extérieur
    p = pl.get("groupe_exterieur")
    against = None
    if p and p.get("room"):
        _, against = _find([base], base.name, p.get("room"))
    oxy = _outdoor(base, mod_xy, against, p.get("side") if p else None) if p else _outdoor(base, mod_xy, None, None)
    if oxy is None and p:
        checks.append("Posição pedida para a unidade exterior impossível (fachada com vão ou fora do lote) : mantida a proposta automática.")
        oxy = _outdoor(base, mod_xy, None, None)
    if oxy is None:
        xs, ys = _mask_pts(base.footprint) if base.footprint is not None else (np.array([mod_xy[0]]), np.array([mod_xy[1]]))
        oxy = (float(xs.max()) + 0.6 * base.px_per_m, float(mod_xy[1]))
        checks.append("Nenhuma fachada cega encontrada perto do módulo : posição da unidade exterior a definir em obra.")
    near_room = _behind_wall(base, oxy) or min((r for r in base.rooms if r.mask is not None and r.mask.any()),
                                               key=lambda r: math.hypot(*(np.subtract(_nearest_in(r.mask, *oxy), oxy))))
    where = f"contra « {near_room.name} »"
    decisions.append(f"Unidade exterior : {where} ({base.name})" + (" — posição imposta." if p else " — fachada cega mais próxima do módulo, proposta automática."))
    checks.append("Unidade exterior : sobre apoios antivibráticos, descarga de ar desimpedida ; verificar a acústica (RGR : quartos, vãos, vizinhança), "
                  "as regras do PDM / câmara municipal e a drenagem dos condensados da descongelação.")
    out_levels[base.name]["equipment"].append({"kind": "pac", "id": "groupe_exterieur", "x": oxy[0], "y": oxy[1], "label": "PAC",
                                               "room": near_room.name})
    out_levels[base.name]["networks"].append({"kind": "pac", "path": [oxy, (oxy[0], mod_xy[1]), mod_xy]})

    # ---- par niveau : boucles, VC, thermostats, réseaux
    vc_n = 0
    totals = {"loops": 0, "area": 0.0, "vc": 0}
    for lv in heated_levels:
        ppm = lv.px_per_m
        cxy, croom = coll[lv.name]
        eq(lv, "collecteur", f"collecteur_{lv.name}", cxy, "Collecteur", croom)
        src = mod_xy if lv is base else risers[lv.name]
        L = out_levels[lv.name]
        if lv is base:
            L["networks"].append({"kind": "module_collecteur", "path": manhattan(mod_xy, cxy, "v")})
            if lv.name in risers:
                L["networks"].append({"kind": "module_colonne", "path": manhattan(mod_xy, risers[lv.name], "h")})
        else:
            L["networks"].append({"kind": "colonne_collecteur", "path": manhattan(risers[lv.name], cxy, "h")})
        n_coll = 0
        for r in lv.rooms:
            t = room_type(r.name)
            info = {"name": r.name, "type": t, "area": r.area_label, "measured": r.area_measured, "status": r.status,
                    "heated": t in HEATED}
            L["rooms"].append(info)
            if t not in HEATED or r.mask is None or not r.mask.any():
                continue
            entry = _nearest_in(r.mask, *cxy)
            d = _len_m(manhattan(cxy, entry), ppm) + 1.0
            pitch = 0.10 if t in ("sdb", "wc") else 0.15
            area = r.area_label or r.area_measured or 0.0
            n, length = loops_for(area, pitch, d)
            n_coll += n
            L["loops"].append({"room": r.name, "area": round(area, 2), "pitch": pitch, "loops": n, "length": round(length, 1),
                               "dist": round(d, 1)})
            L["networks"].append({"kind": "amenee", "path": route(lv, cxy, entry), "room": r.name})
            # thermostat : angle de la pièce le plus proche du collecteur… côté porte, à 0,3 m du mur
            tx, ty = _inset(r.mask, *entry, 0.35 * ppm)
            L["thermostats"].append({"x": tx, "y": ty, "room": r.name})
            # ventilo-convecteurs
            if t in VC_TYPES:
                k = vc_count.get((norm(lv.name), norm(r.name)), vc_count.get(("", norm(r.name))))
                n_vc = k if k is not None else (1 if area <= 25 else 2 if area <= 45 else 3)
                wet = [w for w in lv.rooms if room_type(w.name) in WET and w.mask is not None and w.mask.any() and w is not r]
                for (vx, vy) in _vc_points(lv, r, n_vc) if n_vc else []:
                    vc_n += 1
                    vid = f"VC{vc_n}"
                    if t == "cuisine" or not wet:
                        dest_room, dxy = r, None
                    else:
                        dest_room = min(wet, key=lambda w: math.hypot(*(np.subtract(_nearest_in(w.mask, vx, vy), (vx, vy)))))
                        dxy = _nearest_in(dest_room.mask, vx, vy)
                    L["vc"].append({"id": vid, "x": vx, "y": vy, "room": r.name, "drain_to": dest_room.name})
                    L["networks"].append({"kind": "eau_froide", "path": route(lv, src, (vx, vy)), "vc": vid})
                    if dxy is not None:
                        L["networks"].append({"kind": "condensats", "path": route(lv, (vx, vy), dxy), "vc": vid})
        L["collector_outlets"] = n_coll
        if n_coll > 12:
            checks.append(f"{lv.name} : {n_coll} circuitos — prever dois coletores (12 saídas no máximo cada).")
        totals["loops"] += n_coll
        totals["area"] += sum(x["area"] for x in L["loops"])
        totals["vc"] += len(L["vc"])
        unc = [r.name for r in lv.rooms if r.status == "incertain"]
        if unc:
            checks.append(f"{lv.name} : contorno lido com incerteza para {', '.join(unc)} — circuitos calculados com a área escrita pelo arquiteto.")
    checks.insert(0, "Estudo térmico REH (SCE) : potência da bomba de calor, dos ventiloconvectores e passo de assentamento definitivos.")
    checks.append("Tetos falsos : altura disponível para as cassetes e para a rede de água fria isolada (anticondensação).")
    return {"ok": True, "base_level": base.name, "levels": out_levels, "order": [lv.name for lv in levels],
            "heated_levels": [lv.name for lv in heated_levels], "totals": totals, "decisions": decisions, "checks": checks}
