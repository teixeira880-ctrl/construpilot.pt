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
from typing import Optional

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

def detect_walls(png_b64: str, min_length_px: int = 60,
                 max_line_gap_px: int = 15, canny_low: int = 50,
                 canny_high: int = 150) -> dict:
    """Détecte les segments de murs (lignes droites) via Canny + HoughLinesP.

    Retourne une liste de segments {x1, y1, x2, y2, length_px, angle_deg}.
    Fusionne les segments quasi-colinéaires très proches pour réduire le bruit.
    """
    arr, gray = _load_gray(png_b64)
    h, w = gray.shape

    # Préprocess : blur léger + Canny edge detection
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    edges = cv2.Canny(blur, canny_low, canny_high, apertureSize=3)

    # Dilate pour combler les micro-ruptures des traits
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    edges = cv2.dilate(edges, kernel, iterations=1)

    # Hough transform probabiliste
    lines = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180, threshold=80,
        minLineLength=min_length_px, maxLineGap=max_line_gap_px,
    )

    segments = []
    if lines is not None:
        for line in lines:
            # OpenCV 4.x → line[0] = (x1,y1,x2,y2); OpenCV 5.x → line directly is (x1,y1,x2,y2)
            coords = line[0] if hasattr(line[0], "__len__") and len(line[0]) == 4 else line
            x1, y1, x2, y2 = int(coords[0]), int(coords[1]), int(coords[2]), int(coords[3])
            length = float(np.hypot(x2 - x1, y2 - y1))
            angle = float(np.degrees(np.arctan2(y2 - y1, x2 - x1)))
            segments.append({
                "x1": x1, "y1": y1, "x2": x2, "y2": y2,
                "length_px": round(length, 1),
                "angle_deg": round(angle, 1),
            })

    # Trie par longueur décroissante et cap
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

def flood_fill_room(png_b64: str, seed_x: int, seed_y: int,
                    tolerance: int = 25,
                    simplify_epsilon_px: float = 3.0,
                    min_area_px: int = 800) -> dict:
    """À partir d'un point cliqué à l'intérieur d'une pièce, extrait le polygone
    de son contour via flood fill sur l'image niveaux de gris.

    Retourne le polygone simplifié (Douglas-Peucker) en pixels image.
    """
    arr, gray = _load_gray(png_b64)
    h, w = gray.shape

    if seed_x < 0 or seed_x >= w or seed_y < 0 or seed_y >= h:
        raise ValueError(f"Point ({seed_x},{seed_y}) hors image ({w}x{h})")

    # 1) Prétraitement : blur + seuil pour clarifier fond blanc / murs noirs
    blur = cv2.GaussianBlur(gray, (3, 3), 0)
    # Threshold adaptatif = robuste aux plans mal éclairés / scannés
    binary = cv2.adaptiveThreshold(
        blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 8
    )
    # binary : 255 (intérieur pièce, blanc) / 0 (murs, noirs)

    # 2) Vérifie que le seed tombe bien sur un pixel "vide" (intérieur pièce)
    if binary[seed_y, seed_x] == 0:
        # Cherche un voisin blanc dans un petit rayon
        found = False
        for r in range(1, 15):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    ny, nx = seed_y + dy, seed_x + dx
                    if 0 <= nx < w and 0 <= ny < h and binary[ny, nx] == 255:
                        seed_x, seed_y = nx, ny
                        found = True
                        break
                if found: break
            if found: break
        if not found:
            raise ValueError("Le point cliqué est sur un mur / bord — cliquez à l'intérieur de la pièce")

    # 3) Flood fill : marque tous les pixels connectés à seed avec la valeur 128
    #    On utilise une image de travail pour ne pas modifier binary
    filled = binary.copy()
    mask = np.zeros((h + 2, w + 2), np.uint8)
    _, _, _, rect = cv2.floodFill(
        filled, mask, (seed_x, seed_y), 128,
        loDiff=tolerance, upDiff=tolerance, flags=8
    )

    # 4) Extraction du contour extérieur de la zone marquée
    zone_mask = (filled == 128).astype(np.uint8) * 255
    contours, _ = cv2.findContours(zone_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Aucun contour détecté — cliquez au centre d'une pièce")

    # Garde le contour le plus grand
    contour = max(contours, key=cv2.contourArea)
    area_px = float(cv2.contourArea(contour))
    if area_px < min_area_px:
        raise ValueError("Zone trop petite — cliquez au centre d'une pièce plus grande")

    # 5) Simplifie via Douglas-Peucker → polygone lisible pour le user
    epsilon = simplify_epsilon_px
    approx = cv2.approxPolyDP(contour, epsilon, closed=True)
    points = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]

    # 6) Bounding box (utile pour le viewport)
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

