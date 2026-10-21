"""Iter88 — Non-régression : la détection de murs ne doit PAS garder les traits
de cote (lignes de mesure) même sans analyse IA.

Bug d'origine : les cotes fines étaient comptées comme des murs car
(1) les échos Canny d'une même ligne (~1-3 px) passaient pour un « partenaire
parallèle » et (2) deux cotes empilées dans la marge se prenaient mutuellement
pour un mur double-trait. Correctif : min_gap ≥ 4 px + critère d'emprise du bâti.
"""
from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw

from engines.plan_cv import detect_walls


def _plan_with_cotes() -> str:
    W, H = 900, 700
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    # Murs : double-trait (rectangle extérieur + rectangle intérieur)
    d.rectangle([150, 120, 750, 560], outline="black", width=3)
    d.rectangle([157, 127, 743, 553], outline="black", width=3)
    # Cloison intérieure (double trait)
    d.line([(450, 127), (450, 553)], fill="black", width=3)
    d.line([(457, 127), (457, 553)], fill="black", width=3)
    # Traits de cote FINS dans les marges (à filtrer)
    for (x0, x1, y) in [(150, 450, 90), (457, 750, 90), (150, 750, 60)]:
        d.line([(x0, y), (x1, y)], fill="black", width=1)
        for xx in (x0, x1):
            d.line([(xx, y - 6), (xx, y + 6)], fill="black", width=1)
    for x in (110, 790):
        d.line([(x, 120), (x, 560)], fill="black", width=1)
        for yy in (120, 560):
            d.line([(x - 6, yy), (x + 6, yy)], fill="black", width=1)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def test_cotes_filtered_without_ai():
    res = detect_walls(_plan_with_cotes())
    assert res["filtered_cotes"] >= 10, res["filtered_cotes"]
    # Aucun segment gardé ne doit tomber dans les marges (zones de cote)
    for s in res["segments"]:
        my = (s["y1"] + s["y2"]) / 2
        mx = (s["x1"] + s["x2"]) / 2
        assert my >= 110, f"cote horizontale gardée à y={my}: {s}"
        assert 130 <= mx <= 770, f"cote verticale gardée à x={mx}: {s}"
    # Les vrais murs restent détectés
    assert res["segment_count"] > 0
