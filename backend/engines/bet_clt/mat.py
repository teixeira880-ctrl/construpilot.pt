"""Matériaux : lamellé-collé EN 14080:2013 (classes homogènes), lamelles C24 EN 338 pour le CLT (EN 16351 / ETA courantes),
gammes de compositions CLT usuelles en Europe (épaisseurs de plis 20 à 40 mm, plis alternés L/T)."""
from __future__ import annotations

# MPa (N/mm²), masse volumique kg/m³
GL = {
    "GL24h": {"fm": 24.0, "ft0": 19.2, "fc0": 24.0, "fc90": 2.5, "fv": 3.5, "E0": 11500.0, "E05": 9600.0, "G": 650.0, "rk": 385, "rm": 420},
    "GL28h": {"fm": 28.0, "ft0": 22.3, "fc0": 28.0, "fc90": 2.5, "fv": 3.5, "E0": 12600.0, "E05": 10500.0, "G": 650.0, "rk": 425, "rm": 460},
    "GL30h": {"fm": 30.0, "ft0": 24.0, "fc0": 30.0, "fc90": 2.5, "fv": 3.5, "E0": 13600.0, "E05": 11300.0, "G": 650.0, "rk": 430, "rm": 480},
    "GL32h": {"fm": 32.0, "ft0": 25.6, "fc0": 32.0, "fc90": 2.5, "fv": 3.5, "E0": 14200.0, "E05": 11800.0, "G": 650.0, "rk": 440, "rm": 490},
}
# CLT, lamelles C24 : f_m (k_sys non pris en compte), cisaillement roulant f_R (prudent, plis non collés sur chant),
# E0 lamelles, E90 ≈ 0 (négligé dans les plis transversaux), G = 690, G_R = 50 (EN 16351)
CLT = {"fm": 24.0, "ft0": 14.5, "fc0": 21.0, "fc90": 2.5, "fv": 3.5, "fR": 0.80, "E0": 11000.0, "E05": 7400.0, "G": 690.0, "GR": 50.0,
       "rk": 350, "rm": 420, "grade": "C24"}
STEEL = {"S235": 235.0, "S275": 275.0, "S355": 355.0}

# Compositions (mm) des plis, du dessus vers le dessous ; plis impairs (1, 3, 5, 7) longitudinaux.
LAYUPS = [
    ("80 L3s", (20, 40, 20)),
    ("100 L3s", (30, 40, 30)),
    ("120 L3s", (40, 40, 40)),
    ("140 L5s", (40, 20, 20, 20, 40)),
    ("160 L5s", (40, 20, 40, 20, 40)),
    ("180 L5s", (40, 30, 40, 30, 40)),
    ("200 L5s", (40, 40, 40, 40, 40)),
    ("220 L7s", (40, 20, 40, 20, 40, 20, 40)),
    ("240 L7s", (40, 30, 40, 20, 40, 30, 40)),
    ("260 L7s", (40, 30, 40, 40, 40, 30, 40)),
    ("280 L7s", (40, 40, 40, 40, 40, 40, 40)),
]
WALL_LAYUPS = [x for x in LAYUPS if x[0].split()[0] in ("100", "120", "140", "160", "200")]

PANEL_MAX_W = 2.95     # m — largeur maximale de panneau (presse et transport)
PANEL_MAX_L = 13.50    # m — longueur maximale transportable sans convoi exceptionnel

GL_WIDTHS = (140, 160, 180, 200, 220, 240, 265, 280, 300)
GL_COLS = [(b, b) for b in (200, 240, 280, 320, 360, 400, 440, 480, 520, 560, 600)]


def beam_sizes():
    out = []
    for b in GL_WIDTHS:
        for h in range(240, 1641, 40):
            if 1.5 <= h / b <= 6.0:
                out.append((b, h))
    out.sort(key=lambda bh: (bh[0] * bh[1], bh[1]))
    return out
