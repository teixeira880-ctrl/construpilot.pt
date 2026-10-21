"""Annexe graphique « dimensions intérieures mur à mur » : ligne entre les deux faces exactes, extrémités, identifiant,
valeur, couleur par statut — étiquettes placées sans chevauchement (recherche de position libre)."""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw

from engines.plan_cotes_pdf import _font

STATUS_COL = {"confirmed": (22, 163, 74), "probable": (37, 99, 235), "to_confirm": (234, 88, 12), "unreadable": (220, 38, 38)}
WALL_COL = (100, 116, 139, 90)


def _free_spot(boxes: list[tuple], cand: list[tuple], w: int, h: int, W: int, H: int) -> tuple:
    """Première position candidate dont la boîte ne chevauche aucune étiquette déjà posée (puis décalages croissants)."""
    def ok(x, y):
        if x < 0 or y < 0 or x + w > W or y + h > H:
            return False
        return not any(x < bx2 and x + w > bx1 and y < by2 and y + h > by1 for bx1, by1, bx2, by2 in boxes)
    for step in range(0, 12):
        for (x, y, dx, dy) in cand:
            xx, yy = x + dx * step * (h + 2), y + dy * step * (h + 2)
            if ok(xx, yy):
                return xx, yy
    x, y, _, _ = cand[0]
    return min(max(0, x), W - w), min(max(0, y), H - h)


def render_interior_overlay(image_b64: str, interior: dict, highlight: str | None = None, draw_walls: bool = True) -> bytes:
    img = Image.open(io.BytesIO(base64.b64decode(image_b64))).convert("RGB")
    d = ImageDraw.Draw(img, "RGBA")
    W, H = img.size
    scale = max(W, H) / 1000.0
    lw, tick = max(2, int(2.5 * scale)), max(5, int(8 * scale))
    font = _font(max(10, 10.5 * scale))
    pad = max(2, int(3 * scale))
    if draw_walls:
        for w in interior.get("walls") or []:
            f1, f2 = w["face_1"], w["face_2"]
            d.polygon([(f1["x1"], f1["y1"]), (f1["x2"], f1["y2"]), (f2["x2"], f2["y2"]), (f2["x1"], f2["y1"])], fill=WALL_COL)
            ax = w["axis"]
            d.text(((ax["x1"] + ax["x2"]) / 2 - 3 * scale, (ax["y1"] + ax["y2"]) / 2 - 3 * scale), w["wall_id"], fill=(71, 85, 105, 255), font=_font(max(8, 8 * scale)))
    boxes: list[tuple] = []
    meas = sorted(interior.get("interior_measurements") or [], key=lambda m: m["measurement_id"] == highlight)
    for m in meas:
        c = m["coordinates"]
        hl = highlight and m["measurement_id"] == highlight
        col = STATUS_COL.get(m["status"], (100, 100, 100)) + (255,)
        p1, p2 = (c["x1"], c["y1"]), (c["x2"], c["y2"])
        horiz = m["direction"] == "horizontal"
        if hl:
            d.line([p1, p2], fill=(250, 204, 21, 160), width=lw * 4)
        d.line([p1, p2], fill=col, width=lw)
        for (x, y) in (p1, p2):
            d.line([(x, y - tick), (x, y + tick)] if horiz else [(x - tick, y), (x + tick, y)], fill=col, width=lw)
            d.ellipse([x - lw, y - lw, x + lw, y + lw], fill=col)
        val = m.get("written_dimension_m")
        txt = f"{m['measurement_id']} {m['geometric_dimension_m']:.2f} m" + (f" (cote {val:.2f})" if val is not None and abs(val - m['geometric_dimension_m']) > 0.0105 else "")
        bx1, by1, bx2, by2 = d.textbbox((0, 0), txt, font=font)
        tw, th = bx2 - bx1 + 2 * pad, by2 - by1 + 2 * pad
        mx, my = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
        if not horiz:  # étiquette au tiers du segment pour éviter le croisement central des mesures
            my = p1[1] + 0.3 * (p2[1] - p1[1])
        cand = ([(mx - tw / 2, my - th - tick, 0, -1), (mx - tw / 2, my + tick, 0, 1), (mx - tw / 2 - tw, my - th / 2, -1, 0), (mx + tw / 2 + tick, my - th / 2, 1, 0)]
                if horiz else [(mx + tick, my - th / 2, 1, 0), (mx - tw - tick, my - th / 2, -1, 0), (mx - tw / 2, my - th - tick, 0, -1), (mx - tw / 2, my + tick, 0, 1)])
        x, y = _free_spot(boxes, [(int(a), int(b), dx, dy) for a, b, dx, dy in cand], int(tw), int(th), W, H)
        boxes.append((x, y, x + tw, y + th))
        d.rectangle([x, y, x + tw, y + th], fill=col[:3] + (235,), outline=(250, 204, 21, 255) if hl else None, width=lw if hl else 1)
        d.text((x + pad, y + pad), txt, fill=(255, 255, 255, 255), font=font)
        # petit trait de rappel étiquette → mesure si l'étiquette a été déplacée
        lx, ly = x + tw / 2, y + th / 2
        if abs(lx - mx) > tw or abs(ly - my) > th * 2:
            d.line([(lx, ly), (mx, my)], fill=col[:3] + (140,), width=max(1, lw // 2))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
