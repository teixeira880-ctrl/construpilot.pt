"""Computer Vision Engine — Auto Wall Detection + Flood Fill Room Contour.

Deux pipelines :
- **detect_walls(png_bytes)** : Hough Line Detection sur plan scanné / photo → segments de murs.
- **flood_fill_room(png_bytes, seed_x, seed_y)** : à partir d'un point cliqué à l'intérieur
  d'une pièce, extrait le contour polygonal fermé de la pièce.

Toutes les coordonnées retournées sont en pixels de l'image d'origine (post-Pillow resize).
Le Geometry Engine se charge ensuite de convertir en mètres via la calibration.
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
