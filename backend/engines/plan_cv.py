"""Computer Vision Engine — Wall Detection + Room Auto Fill + Deskew photo.

Trois pipelines :
- **detect_walls** : Hough Line Detection sur plan scanné → segments de murs.
- **flood_fill_room** : à partir d'un clic intérieur, extrait le contour polygonal fermé.
- **deskew_photo** : détecte les 4 coins d'une feuille de plan photographiée
  au smartphone, applique une correction de perspective (warp) puis renvoie l'image.

Toutes les coordonnées retournées sont en pixels de l'image d'origine.
"""
from __future__ import annotations

import base64
import io
import logging

import cv2
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)


def _load_gray(png_b64: str) -> tuple[np.ndarray, np.ndarray]:
    """Décode base64 PNG → (image originale RGB, image niveaux de gris)."""
    raw = base64.b64decode(png_b64)
    img = Image.open(io.BytesIO(raw))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    arr = np.array(img)
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    return arr, gray


# ============ WALL DETECTION ============

def _cv_preprocess(gray: "np.ndarray", canny_low: int, canny_high: int) -> "np.ndarray":
    """Blur + Canny edge detection + dilate — returns binary edges image."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, canny_low, canny_high, apertureSize=3)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    return cv2.dilate(edges, kernel, iterations=1)


def _cv_distance_transform(gray: "np.ndarray") -> "np.ndarray":
    """Otsu-inverted binary + distanceTransform — used to sample wall thickness."""
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    _, bin_inv = cv2.threshold(blur, 0, 255,
                                cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    return cv2.distanceTransform(bin_inv, cv2.DIST_L2, 3)


def _wall_type_from_thickness(t: float) -> str:
    """Classify a wall segment by pixel thickness (150 dpi baseline)."""
    if t >= 8.0:
        return "porteur"
    if t >= 3.5:
        return "cloison"
    return "doublage"


def _sample_thickness(dist: "np.ndarray", x1: int, y1: int, x2: int, y2: int,
                      w: int, h: int, n_samples: int = 5) -> float:
    """Sample `n_samples` points along the segment, return median * 2 (px thickness)."""
    thicknesses: list[float] = []
    for k in range(n_samples):
        ratio = (k + 1) / (n_samples + 1)
        sx = int(x1 + (x2 - x1) * ratio)
        sy = int(y1 + (y2 - y1) * ratio)
        x0, xn = max(0, sx - 3), min(w, sx + 4)
        y0, yn = max(0, sy - 3), min(h, sy + 4)
        patch = dist[y0:yn, x0:xn]
        if patch.size:
            thicknesses.append(float(patch.max()))
    return round(2.0 * float(np.median(thicknesses)) if thicknesses else 0.0, 1)


def _build_segment(line, dist: "np.ndarray", w: int, h: int, token_hex) -> dict:
    """Turn a single OpenCV Hough line into a full segment dict."""
    coords = line[0] if hasattr(line[0], "__len__") and len(line[0]) == 4 else line
    x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
    length = float(np.hypot(x2 - x1, y2 - y1))
    angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
    thickness_px = _sample_thickness(dist, x1, y1, x2, y2, w, h)
    return {
        "wall_id": "w_" + token_hex(3),
        "x1": x1, "y1": y1, "x2": x2, "y2": y2,
        "length_px": round(length, 1),
        "angle_deg": round(angle, 1),
        "thickness_px": thickness_px,
        "wall_type": _wall_type_from_thickness(thickness_px),
    }


# ---- Filtrage traits de cote (iter62) ----

def _angle_close(a: float, b: float, tol: float = 12.0) -> bool:
    d = abs((a % 180) - (b % 180))
    return min(d, 180 - d) <= tol


def _point_seg_distance(px: float, py: float, x1: float, y1: float,
                        x2: float, y2: float) -> float:
    dx, dy = x2 - x1, y2 - y1
    l2 = dx * dx + dy * dy
    if l2 == 0:
        return float(np.hypot(px - x1, py - y1))
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / l2))
    return float(np.hypot(px - (x1 + t * dx), py - (y1 + t * dy)))


def _matches_dim_zone(seg: dict, dim_zones: list[dict], dist_tol: float = 18.0) -> bool:
    """Un segment est un trait de cote s'il est proche ET parallèle à une cote IA."""
    mx, my = (seg["x1"] + seg["x2"]) / 2, (seg["y1"] + seg["y2"]) / 2
    for z in dim_zones or []:
        if _point_seg_distance(mx, my, z["x1"], z["y1"], z["x2"], z["y2"]) > dist_tol:
            continue
        z_angle = float(np.degrees(np.arctan2(z["y2"] - z["y1"], z["x2"] - z["x1"])))
        if _angle_close(seg["angle_deg"], z_angle):
            return True
    return False


def _in_text_zone(seg: dict, text_zones: list[dict], pad: float = 2.0) -> bool:
    mx, my = (seg["x1"] + seg["x2"]) / 2, (seg["y1"] + seg["y2"]) / 2
    for t in text_zones or []:
        if (t["x"] - pad <= mx <= t["x"] + t["w"] + pad
                and t["y"] - pad <= my <= t["y"] + t["h"] + pad):
            return True
    return False


def _has_parallel_partner(seg: dict, others: list[dict],
                          min_gap: float = 4.5, max_gap: float = 28.0,
                          min_overlap: float = 0.35) -> bool:
    """Les murs « creux » sont dessinés en 2 traits parallèles proches.
    Un trait fin ISOLÉ (sans partenaire parallèle) est très probablement une cote.

    ⚠️ `min_gap` doit rester ≥ ~4 px : Canny détecte les DEUX bords d'un même
    trait fin (échos à 1-3 px). Sans ce plancher, une ligne de cote isolée
    « trouve » son propre écho Canny comme faux partenaire et échappe au filtre
    (bug corrigé iter88 — les cotes étaient comptées comme des murs)."""
    mx = (seg["x1"] + seg["x2"]) / 2
    my = (seg["y1"] + seg["y2"]) / 2
    for o in others:
        if o is seg or not _angle_close(seg["angle_deg"], o["angle_deg"], 8.0):
            continue
        d = _point_seg_distance(mx, my, o["x1"], o["y1"], o["x2"], o["y2"])
        if not (min_gap <= d <= max_gap):
            continue
        horiz = abs(seg["x2"] - seg["x1"]) >= abs(seg["y2"] - seg["y1"])
        if horiz:
            a0, a1 = sorted((seg["x1"], seg["x2"]))
            b0, b1 = sorted((o["x1"], o["x2"]))
        else:
            a0, a1 = sorted((seg["y1"], seg["y2"]))
            b0, b1 = sorted((o["y1"], o["y2"]))
        overlap = max(0.0, min(a1, b1) - max(a0, b0))
        if overlap / max(1.0, a1 - a0) >= min_overlap:
            return True
    return False


def _wall_footprint(segments: list[dict], thick_px: float = 3.0,
                    min_len_ratio: float = 0.28) -> tuple | None:
    """Bounding box (x0, y0, x1, y1) de la masse des VRAIS murs structurels.

    Sert de référence pour rejeter les traits fins situés dans les marges
    (cotes, annotations, cartouche, titre). On ne retient comme référence que
    les segments à la fois ÉPAIS et LONGS (les grands murs porteurs/refends) —
    sinon le titre en gras ou une cote totale fausserait l'emprise. Retourne
    None si trop peu de murs fiables (plans dessinés en traits fins uniquement)."""
    if not segments:
        return None
    span = max((max(s["x1"], s["x2"]) for s in segments), default=0)
    span = max(span, max((max(s["y1"], s["y2"]) for s in segments), default=0))
    min_len = min_len_ratio * span
    seeds = [s for s in segments
             if s.get("thickness_px", 0) >= thick_px and s.get("length_px", 0) >= min_len]
    if len(seeds) < 3:
        return None
    xs = [c for s in seeds for c in (s["x1"], s["x2"])]
    ys = [c for s in seeds for c in (s["y1"], s["y2"])]
    return (min(xs), min(ys), max(xs), max(ys))


def _outside_footprint(seg: dict, fp: tuple, margin: float) -> bool:
    """Le milieu du segment est-il hors de l'emprise du bâti (± marge) ?"""
    mx, my = (seg["x1"] + seg["x2"]) / 2, (seg["y1"] + seg["y2"]) / 2
    x0, y0, x1, y1 = fp
    return (mx < x0 - margin or mx > x1 + margin
            or my < y0 - margin or my > y1 + margin)


def filter_cote_segments(segments: list[dict], dim_zones: list | None = None,
                         text_zones: list | None = None,
                         thin_px: float = 3.0) -> tuple[list[dict], int]:
    """Sépare vrais murs / traits de cote. Retourne (murs, nb_cotes_filtrées).

    4 critères d'exclusion :
    1. proche + parallèle d'un trait de cote localisé par l'IA (bbox_norm)
    2. milieu du segment dans une zone de texte du plan (PDF vectoriel)
    3. trait fin (< thin_px) SANS partenaire parallèle réel (mur creux = 2 traits
       espacés de ≥4 px, pas les échos Canny d'une même ligne).
    4. milieu du segment situé HORS de l'enveloppe du bâti (± marge). Les vrais
       murs extérieurs sont SUR le bord de l'emprise (donc dans la marge) et les
       cloisons à l'intérieur ; ce qui tombe dans les marges est cote / titre /
       cartouche / annotation. Ce critère n'est appliqué que si l'emprise est
       fiable (≥3 longs murs épais), sinon on ne rejette rien par position.
    """
    fp = _wall_footprint(segments)
    margin = 0.0
    if fp:
        margin = 0.02 * max(fp[2] - fp[0], fp[3] - fp[1])
    kept: list[dict] = []
    removed = 0
    for s in segments:
        thin = s.get("thickness_px", 99) < thin_px
        if dim_zones and _matches_dim_zone(s, dim_zones):
            removed += 1
            continue
        if text_zones and _in_text_zone(s, text_zones):
            removed += 1
            continue
        if fp and _outside_footprint(s, fp, margin):
            removed += 1
            continue
        if thin and not _has_parallel_partner(s, segments):
            removed += 1
            continue
        kept.append(s)
    return kept, removed


def detect_walls(png_b64: str, min_length_px: int = 60,
                 max_line_gap_px: int = 15, canny_low: int = 50,
                 canny_high: int = 150,
                 dim_zones: list | None = None,
                 text_zones: list | None = None,
                 filter_cotes: bool = True,
                 orthogonal_only: bool = False) -> dict:
    """Détecte les segments de murs (lignes droites) via Canny + HoughLinesP.

    Retourne une liste de segments {x1, y1, x2, y2, length_px, angle_deg,
    thickness_px, wall_type} où wall_type ∈ {porteur, cloison, doublage}
    est déterminé par l'épaisseur via distance transform.

    Refactorisé (iter36) : 4 helpers privés (`_cv_preprocess`,
    `_cv_distance_transform`, `_sample_thickness`, `_build_segment`) ramènent
    le corps de `detect_walls` à ~25 lignes.
    """
    import secrets as _sec
    _, gray = _load_gray(png_b64)
    h, w = gray.shape

    edges = _cv_preprocess(gray, canny_low, canny_high)
    dist = _cv_distance_transform(gray)

    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=80,
        minLineLength=min_length_px, maxLineGap=max_line_gap_px,
    )
    segments = [_build_segment(line, dist, w, h, _sec.token_hex)
                for line in (lines if lines is not None else [])]

    filtered_cotes = 0
    if filter_cotes and segments:
        segments, filtered_cotes = filter_cote_segments(segments, dim_zones, text_zones)

    segments.sort(key=lambda s: -s["length_px"])

    # Détection « plan structure/béton » : forte proportion de diagonales (aciers, hachures)
    def _is_diag(s):
        a = s.get("angle_deg", 0)
        return not (_angle_close(a, 0, 12) or _angle_close(a, 90, 12) or _angle_close(a, 180, 12))
    raw_n = len(segments)
    diag_n = sum(1 for s in segments if _is_diag(s))
    diag_ratio = round(diag_n / raw_n, 3) if raw_n else 0.0
    structural_hint = raw_n >= 400 or diag_ratio >= 0.35

    filtered_diagonals = 0
    if orthogonal_only:
        ortho = [s for s in segments if not _is_diag(s)]
        filtered_diagonals = len(segments) - len(ortho)
        segments = ortho

    segments = segments[:500]

    return {
        "image_width": int(w),
        "image_height": int(h),
        "segment_count": len(segments),
        "filtered_cotes": filtered_cotes,
        "filtered_diagonals": filtered_diagonals,
        "diagonal_ratio": diag_ratio,
        "structural_hint": bool(structural_hint),
        "segments": segments,
        "params": {
            "canny_low": canny_low, "canny_high": canny_high,
            "min_length_px": min_length_px, "max_line_gap_px": max_line_gap_px,
            "orthogonal_only": orthogonal_only,
        },
    }


# ============ ROOM AUTO FILL (flood fill contour) ============

def _binarize_plan(png_b64: str) -> tuple["np.ndarray", int, int]:
    """Return (binary image where interior=255 walls=0, width, height)."""
    _, gray = _load_gray(png_b64)
    h, w = gray.shape
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 8)
    return binary, w, h


def _snap_seed_to_interior(binary: "np.ndarray", seed_x: int, seed_y: int,
                             w: int, h: int, radius: int = 15) -> tuple[int, int]:
    """If the seed lands on a wall pixel, walk outward until an interior pixel
    is found. Raises ValueError if none in `radius` px."""
    if binary[seed_y, seed_x] == 255:
        return seed_x, seed_y
    for r in range(1, radius):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                ny, nx = seed_y + dy, seed_x + dx
                if 0 <= nx < w and 0 <= ny < h and binary[ny, nx] == 255:
                    return nx, ny
    raise ValueError(
        "O ponto clicado está numa parede / bordo — clique dentro da divisão")


def _extract_largest_contour(zone_mask: "np.ndarray", min_area_px: int):
    """Return (contour, area_px) or raise ValueError if none is large enough."""
    contours, _ = cv2.findContours(zone_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Nenhum contorno detetado — clique no centro de uma divisão")
    contour = max(contours, key=cv2.contourArea)
    area_px = float(cv2.contourArea(contour))
    if area_px < min_area_px:
        raise ValueError("Zona demasiado pequena — clique no centro de uma divisão maior")
    return contour, area_px


def flood_fill_room(png_b64: str, seed_x: int, seed_y: int,
                    tolerance: int = 25,
                    simplify_epsilon_px: float = 3.0,
                    min_area_px: int = 800) -> dict:
    """À partir d'un point cliqué à l'intérieur d'une pièce, extrait le polygone
    de son contour via flood fill sur l'image niveaux de gris.

    Retourne le polygone simplifié (Douglas-Peucker) en pixels image.

    Refactorisé (iter37) : 3 helpers privés (`_binarize_plan`,
    `_snap_seed_to_interior`, `_extract_largest_contour`) — nesting depth
    ramenée de 5 à 2, complexité cyclomatique 18 → ~5.
    """
    binary, w, h = _binarize_plan(png_b64)

    if not (0 <= seed_x < w and 0 <= seed_y < h):
        raise ValueError(f"Point ({seed_x},{seed_y}) hors image ({w}x{h})")

    seed_x, seed_y = _snap_seed_to_interior(binary, seed_x, seed_y, w, h)

    # Flood fill sur une copie (préserve `binary` pour un éventuel re-run)
    filled = binary.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    cv2.floodFill(filled, mask, (seed_x, seed_y), 128,
                  loDiff=tolerance, upDiff=tolerance, flags=8)

    zone_mask = (filled == 128).astype(np.uint8) * 255
    contour, area_px = _extract_largest_contour(zone_mask, min_area_px)

    # Simplification Douglas-Peucker
    approx = cv2.approxPolyDP(contour, simplify_epsilon_px, closed=True)
    points = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]
    x, y, ww, hh = cv2.boundingRect(contour)

    return {
        "image_width": int(w),
        "image_height": int(h),
        "seed_x": int(seed_x),
        "seed_y": int(seed_y),
        "points": points,
        "point_count": len(points),
        "area_px2": round(area_px, 1),
        "bounding_box": {"x": int(x), "y": int(y), "w": int(ww), "h": int(hh)},
        "params": {"tolerance": tolerance, "simplify_epsilon_px": simplify_epsilon_px},
    }


def _binarize_and_close(png_b64: str) -> tuple:
    """Preprocessing : binarize plan + light morphological close to seal wall gaps."""
    binary, w, h = _binarize_plan(png_b64)
    kernel = np.ones((3, 3), np.uint8)
    closed = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)
    return closed, w, h


def _is_valid_room_contour(c, total_area: int, min_area_px: int) -> tuple[bool, tuple]:
    """Filter a contour : reject noise, page border, thin strips. Returns (ok, bbox)."""
    area = float(cv2.contourArea(c))
    if area < min_area_px or area > total_area * 0.6:
        return False, ()
    x, y, ww, hh = cv2.boundingRect(c)
    if ww < 20 or hh < 20:
        return False, ()
    ratio = area / (ww * hh) if ww and hh else 0
    if ratio < 0.35:      # too concave → probably not a room
        return False, ()
    return True, (area, x, y, ww, hh)


def _contour_to_room(c, area: float, bbox: tuple, simplify_epsilon_px: float) -> dict | None:
    """Convert an accepted contour into a normalized room dict, or None if degenerate."""
    x, y, ww, hh = bbox
    approx = cv2.approxPolyDP(c, simplify_epsilon_px, closed=True)
    points = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]
    if len(points) < 3:
        return None
    M = cv2.moments(c)
    cx = int(M["m10"] / M["m00"]) if M["m00"] else x + ww // 2
    cy = int(M["m01"] / M["m00"]) if M["m00"] else y + hh // 2
    return {
        "points": points,
        "point_count": len(points),
        "area_px2": round(area, 1),
        "centroid": [cx, cy],
        "bounding_box": {"x": int(x), "y": int(y), "w": int(ww), "h": int(hh)},
    }


def detect_all_rooms(png_b64: str,
                     simplify_epsilon_px: float = 3.0,
                     min_area_px: int = 800,
                     max_rooms: int = 30) -> dict:
    """Detect ALL enclosed rooms on a plan image automatically (no seed click).

    Pipeline: binarize+close → findContours(RETR_CCOMP) → filter by area, aspect,
    concavity → simplify polygon → return polygons in image pixel coords.
    """
    closed, w, h = _binarize_and_close(png_b64)
    contours, _ = cv2.findContours(closed, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return {"image_width": w, "image_height": h, "rooms": []}

    total_area = w * h
    candidates: list[tuple] = []
    for c in contours:
        ok, bbox = _is_valid_room_contour(c, total_area, min_area_px)
        if ok:
            candidates.append((bbox[0], c, bbox[1:]))    # (area, contour, (x,y,w,h))

    # Keep top N largest
    candidates.sort(key=lambda t: t[0], reverse=True)
    rooms = []
    for area, c, bbox in candidates[:max_rooms]:
        room = _contour_to_room(c, area, bbox, simplify_epsilon_px)
        if room:
            rooms.append(room)

    return {"image_width": w, "image_height": h, "rooms": rooms}


# ============ DESKEW (perspective correction photo smartphone) ============

def _order_corners(pts: np.ndarray) -> np.ndarray:
    """Ordonne 4 coins : top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]    # top-left = min sum
    rect[2] = pts[np.argmax(s)]    # bottom-right = max sum
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]  # top-right = min diff
    rect[3] = pts[np.argmax(diff)]  # bottom-left = max diff
    return rect


def _decode_and_resize(png_bytes: bytes, max_side: int = 1200):
    """Décodage OpenCV + redimensionnement pour vitesse. Renvoie (img_orig, img_small, scale)."""
    arr = np.frombuffer(png_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Imagem inválida")
    h0, w0 = img.shape[:2]
    scale = max(w0, h0) / max_side if max(w0, h0) > max_side else 1.0
    img_small = cv2.resize(img, (int(w0 / scale), int(h0 / scale))) if scale > 1.0 else img
    return img, img_small, scale


def _find_page_quadrilateral(img_small: "np.ndarray") -> "np.ndarray | None":
    """Cherche le plus grand quadrilatère (feuille de plan) via Canny + approxPolyDP.
    Renvoie 4 points (float32) ou None si aucun contour fiable."""
    gray = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 30, 120)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    h_small, w_small = img_small.shape[:2]
    total_area = h_small * w_small
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        if cv2.contourArea(c) < total_area * 0.15:
            break
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype(np.float32)
    return None


def _warp_to_rect(img: "np.ndarray", quad: "np.ndarray") -> "tuple[np.ndarray, np.ndarray, int, int] | None":
    """Applique warpPerspective sur `img` avec les 4 coins `quad`.
    Renvoie (warped, ordered_corners, max_w, max_h) ou None si trop petit."""
    ordered = _order_corners(quad)
    tl, tr, br, bl = ordered
    max_w = int(max(np.linalg.norm(br - bl), np.linalg.norm(tr - tl)))
    max_h = int(max(np.linalg.norm(tr - br), np.linalg.norm(tl - bl)))
    if max_w < 200 or max_h < 200:
        return None
    dst = np.array([[0, 0], [max_w - 1, 0],
                    [max_w - 1, max_h - 1], [0, max_h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(ordered, dst)
    return cv2.warpPerspective(img, M, (max_w, max_h)), ordered, max_w, max_h


def deskew_photo(png_bytes: bytes) -> dict:
    """Corrige la perspective d'une photo smartphone de plan/document.

    Pipeline : decode+resize → Canny+contours → plus grand quadrilatère →
    order corners → warpPerspective. Renvoie l'image corrigée en PNG bytes.

    Si aucun quadrilatère fiable n'est trouvé, renvoie l'image originale avec
    `applied: false` (l'utilisateur pourra quand même calibrer manuellement).
    """
    img, img_small, scale = _decode_and_resize(png_bytes)
    h0, w0 = img.shape[:2]

    quad = _find_page_quadrilateral(img_small)
    if quad is None:
        return _encode_png(img, applied=False, reason="Nenhum quadrilátero (folha) detetado")

    quad *= scale
    result = _warp_to_rect(img, quad)
    if result is None:
        return _encode_png(img, applied=False, reason="Quadrilátero demasiado pequeno")

    warped, ordered, max_w, max_h = result
    return _encode_png(warped, applied=True, reason="Perspetiva corrigida",
                       corners=ordered.tolist(),
                       original_size=[w0, h0], new_size=[max_w, max_h])


def _encode_png(img_bgr: np.ndarray, applied: bool, reason: str, **extra) -> dict:
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        raise ValueError("Codificação PNG impossível")
    return {
        "applied": applied,
        "reason": reason,
        "image_png_b64": base64.b64encode(buf.tobytes()).decode("ascii"),
        "width": int(img_bgr.shape[1]),
        "height": int(img_bgr.shape[0]),
        **extra,
    }

