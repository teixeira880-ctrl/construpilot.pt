"""Render da estrutura CLT montada (Mitsuba 3, sol + céu físicos) — mesma geometria que o cálculo.

Cada painel é extrudido a partir do seu contorno real, com os recortes dos vãos (decomposição em blocos retangulares
para os painéis retangulares, triangulação do contorno para as empenas). Nada é desenhado por IA.
Sem Mitsuba → ImportError tratado pelo chamador (o dossier sai sem render).
"""
from __future__ import annotations

import math
import os
import tempfile
import time

import numpy as np

from engines.lsf.geom import subtract_rects
from engines.lsf.render import _ear_clip

_CUBE = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64)
_CF = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])


def _prisma(pts):
    n = len(pts)
    tris = _ear_clip(pts)
    V = np.array([[a, b, 0.0] for a, b in pts] + [[a, b, 1.0] for a, b in pts])
    F = [(i, k, j) for i, j, k in tris] + [(i + n, j + n, k + n) for i, j, k in tris]
    for i in range(n):
        j = (i + 1) % n
        F += [(i, j, j + n), (i, j + n, i + n)]
    return V, np.array(F)


def malhas(res: dict):
    grupos = {}

    def push(mat, V, F):
        g = grupos.setdefault(mat, [[], [], 0])
        g[0].append(V)
        g[1].append(F + g[2])
        g[2] += len(V)

    for p in res["paineis"]:
        o, u, v, w = (np.array(p[k], dtype=np.float64) for k in ("o", "u", "v", "w"))
        mat = {"parede": "clt", "empena": "clt", "laje": "clt_laje", "cobertura": "clt_laje"}[p["tipo"]]
        if len(p["contorno"]) == 4:
            cells = subtract_rects({"x0": 0, "x1": p["L"], "z0": 0, "z1": p["H"]}, p.get("recortes") or [])
            for cl in cells:
                Vl = _CUBE.copy()
                Vl[:, 0] = cl["x0"] + Vl[:, 0] * (cl["x1"] - cl["x0"])
                Vl[:, 1] = cl["z0"] + Vl[:, 1] * (cl["z1"] - cl["z0"])
                Vl[:, 2] *= p["esp"]
                push(mat, (o + Vl[:, :1] * u + Vl[:, 1:2] * v + Vl[:, 2:3] * w) / 1000.0, _CF)
        else:
            Vl, F = _prisma(p["contorno"])
            Vl[:, 2] *= p["esp"]
            push(mat, (o + Vl[:, :1] * u + Vl[:, 1:2] * v + Vl[:, 2:3] * w) / 1000.0, F)
    for b in res.get("vigas") or []:
        o, e, l = (np.array(b[k], dtype=np.float64) for k in ("o", "eixo", "lado"))
        V = o + _CUBE[:, :1] * e * b["L"] + _CUBE[:, 1:2] * l * b["b"] + _CUBE[:, 2:3] * np.array([0, 0, b["h"]])
        push("gl", V / 1000.0, _CF)
    return {k: (np.vstack(v[0]), np.vstack(v[1])) for k, v in grupos.items()}


def _materiais():
    def princ(rgb, rough, spec=0.5):
        return {"type": "principled", "base_color": {"type": "rgb", "value": list(rgb)}, "roughness": rough, "specular": spec}
    return {
        "clt": {"type": "twosided", "bsdf": princ((0.78, 0.60, 0.38), 0.72, 0.3)},        # pinho / abeto C24
        "clt_laje": {"type": "twosided", "bsdf": princ((0.74, 0.55, 0.33), 0.75, 0.3)},
        "gl": {"type": "twosided", "bsdf": princ((0.66, 0.47, 0.27), 0.7, 0.3)},
        "laje": {"type": "twosided", "bsdf": princ((0.58, 0.57, 0.55), 0.9, 0.2)},
        "relva": {"type": "twosided", "bsdf": princ((0.17, 0.24, 0.11), 0.95, 0.1)},
        "saibro": {"type": "twosided", "bsdf": princ((0.52, 0.48, 0.42), 0.95, 0.1)},
    }


def render(res: dict, vistas=None, largura: int = 1600, altura: int = 900, spp: int = 96, orcamento_s: float | None = 240,
           gm: dict | None = None, materiais: dict | None = None) -> list[tuple[str, bytes]]:
    """→ [(nome, PNG)] — estrutura CLT montada (sem acabamentos). `gm` / `materiais`: outras estruturas (construção tradicional)."""
    from engines.calc_lots.render3d import _mi, _png, _ply, _tonemap
    mi = _mi()
    gm = gm or malhas(res)
    allV = np.vstack([v for v, _ in gm.values()])
    (x0, y0, z0), (x1, y1, z1) = allV.min(0), allV.max(0)
    z0 = max(z0, -0.5)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    diag = math.hypot(x1 - x0, y1 - y0)
    fov = 36
    dist = (max(diag, (z1 - z0) * 1.6) * 0.78) / math.tan(math.radians(fov / 2))
    vistas = vistas or [("estrutura", (-0.62, -0.78), 0.55), ("estrutura_tras", (0.70, 0.70), 0.45)]
    out = []
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        files = {}
        for nm, (V, F) in gm.items():
            fn = os.path.join(tmp, f"{nm}.ply")
            _ply(fn, V, F)
            files[nm] = fn
        mats = {**_materiais(), **(materiais or {})}
        for nome, (dx, dy), elev in vistas:
            if out and orcamento_s and (time.time() - t0) * (len(out) + 1) / len(out) > orcamento_s:
                break
            n = math.hypot(dx, dy)
            org = [cx + dx / n * dist, cy + dy / n * dist, z0 + dist * elev]
            tgt = [cx, cy, z0 + (z1 - z0) * 0.40]
            sc = {"type": "scene", "integrator": {"type": "path", "max_depth": 6},
                  "sensor": {"type": "perspective", "fov": fov, "to_world": mi.ScalarTransform4f().look_at(origin=org, target=tgt, up=[0, 0, 1]),
                             "film": {"type": "hdrfilm", "width": largura, "height": altura, "rfilter": {"type": "gaussian"}},
                             "sampler": {"type": "independent", "sample_count": spp}},
                  "ceu": {"type": "sunsky", "sun_direction": [-0.40, -0.65, 0.62], "turbidity": 3.0, "albedo": 0.2}}
            sc.update(mats)
            sc["obj_laje"] = {"type": "cube", "to_world": mi.ScalarTransform4f().translate([cx, cy, z0 - 0.15]).scale([(x1 - x0) / 2 + 0.3, (y1 - y0) / 2 + 0.3, 0.15]),
                              "bsdf": {"type": "ref", "id": "laje"}}
            sc["obj_terreno"] = {"type": "rectangle", "to_world": mi.ScalarTransform4f().translate([cx, cy, z0 - 0.30]).scale([diag * 14, diag * 14, 1]),
                                 "bsdf": {"type": "ref", "id": "relva"}}
            sc["obj_estaleiro"] = {"type": "rectangle", "to_world": mi.ScalarTransform4f().translate([cx, cy, z0 - 0.29]).scale([(x1 - x0) / 2 + 2.5, (y1 - y0) / 2 + 2.5, 1]),
                                   "bsdf": {"type": "ref", "id": "saibro"}}
            for nm, fn in files.items():
                sc["m_" + nm] = {"type": "ply", "filename": fn, "bsdf": {"type": "ref", "id": nm}, "face_normals": True}
            img = mi.render(mi.load_dict(sc), spp=spp)
            out.append((nome, _png(_tonemap(img))))
    return out
