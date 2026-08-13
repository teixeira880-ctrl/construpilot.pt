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


def detect_walls(png_b64: str, min_length_px: int = 60,
                 max_line_gap_px: int = 15, canny_low: int = 50,
                 canny_high: int = 150) -> dict:
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

    segments.sort(key=lambda s: -s["length_px"])
    segments = segments[:500]

    return {
        "image_width": int(w),
        "image_height": int(h),
        "segment_count": len(segments),
        "segments": segments,
        "params": {
            "canny_low": canny_low, "canny_high": canny_high,
            "min_length_px": min_length_px, "max_line_gap_px": max_line_gap_px,
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
        "Le point cliqué est sur un mur / bord — cliquez à l'intérieur de la pièce")


def _extract_largest_contour(zone_mask: "np.ndarray", min_area_px: int):
    """Return (contour, area_px) or raise ValueError if none is large enough."""
    contours, _ = cv2.findContours(zone_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Aucun contour détecté — cliquez au centre d'une pièce")
    contour = max(contours, key=cv2.contourArea)
    area_px = float(cv2.contourArea(contour))
    if area_px < min_area_px:
        raise ValueError("Zone trop petite — cliquez au centre d'une pièce plus grande")
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


def deskew_photo(png_bytes: bytes) -> dict:
    """Corrige la perspective d'une photo smartphone de plan/document.

    Pipeline : grayscale → blur → Canny → contours → plus grand quadrilatère
    → order corners → warpPerspective. Renvoie l'image corrigée en PNG bytes.

    Si aucun quadrilatère fiable n'est trouvé, renvoie l'image originale avec
    `applied: false` (l'utilisateur pourra quand même calibrer manuellement).
    """
    img_bytes = png_bytes
    # Décodage direct via OpenCV (plus rapide que PIL)
    arr = np.frombuffer(img_bytes, dtype=np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Image invalide")
    h0, w0 = img.shape[:2]

    # Redimensionne pour vitesse (facteur mémoire)
    max_side = 1200
    scale = max(w0, h0) / max_side if max(w0, h0) > max_side else 1.0
    if scale > 1.0:
        img_small = cv2.resize(img, (int(w0 / scale), int(h0 / scale)))
    else:
        img_small = img

    gray = cv2.cvtColor(img_small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 30, 120)
    # Dilate pour combler
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=1)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return _encode_png(img, applied=False, reason="Aucun contour détecté")

    # Cherche le plus grand quadrilatère (approxPolyDP)
    h_small, w_small = img_small.shape[:2]
    total_area = h_small * w_small
    quad = None
    for c in sorted(contours, key=cv2.contourArea, reverse=True)[:8]:
        area = cv2.contourArea(c)
        if area < total_area * 0.15:   # ignore petites zones
            break
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            quad = approx.reshape(4, 2).astype(np.float32)
            break

    if quad is None:
        return _encode_png(img, applied=False, reason="Aucun quadrilatère (feuille) détecté")

    # Remise à l'échelle originale
    quad *= scale
    ordered = _order_corners(quad)

    # Dimensions cible : min largeur / min hauteur → carte utile
    (tl, tr, br, bl) = ordered
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_w = int(max(width_a, width_b))
    max_h = int(max(height_a, height_b))
    if max_w < 200 or max_h < 200:
        return _encode_png(img, applied=False, reason="Quadrilatère trop petit")

    dst = np.array([[0, 0], [max_w - 1, 0],
                    [max_w - 1, max_h - 1], [0, max_h - 1]], dtype=np.float32)
    M = cv2.getPerspectiveTransform(ordered, dst)
    warped = cv2.warpPerspective(img, M, (max_w, max_h))

    return _encode_png(warped, applied=True, reason="Perspective corrigée",
                       corners=ordered.tolist(),
                       original_size=[w0, h0], new_size=[max_w, max_h])


def _encode_png(img_bgr: np.ndarray, applied: bool, reason: str, **extra) -> dict:
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        raise ValueError("Encodage PNG impossible")
    return {
        "applied": applied,
        "reason": reason,
        "image_png_b64": base64.b64encode(buf.tobytes()).decode("ascii"),
        "width": int(img_bgr.shape[1]),
        "height": int(img_bgr.shape[0]),
        **extra,
    }

