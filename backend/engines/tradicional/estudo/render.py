"""Render da estrutura tradicional montada (Mitsuba 3, mesmo cenário que LSF / CLT) — geometria exata dos elementos calculados."""
from __future__ import annotations

import numpy as np

from engines.clt.render import _CF, _CUBE, _prisma
from engines.clt.render import render as _render
from engines.lsf.geom import subtract_rects

MAT = {"sapata": "betao", "viga_fundacao": "betao", "pilar": "betao", "viga": "betao", "laje": "betao", "alvenaria": "tijolo", "empena": "tijolo",
       "cobertura": "betao"}


def malhas(res: dict):
    grupos = {}

    def push(mat, V, F):
        g = grupos.setdefault(mat, [[], [], 0])
        g[0].append(V)
        g[1].append(F + g[2])
        g[2] += len(V)

    for it in res["itens"]:
        o, u, v, w = (np.array(it[k], dtype=np.float64) for k in ("o", "u", "v", "w"))
        mat = MAT[it["tipo"]]
        if len(it["contorno"]) == 4:
            L, H = it["contorno"][1][0], it["contorno"][2][1]
            for cl in subtract_rects({"x0": 0, "x1": L, "z0": 0, "z1": H}, it.get("recortes") or []):
                Vl = _CUBE.copy()
                Vl[:, 0] = cl["x0"] + Vl[:, 0] * (cl["x1"] - cl["x0"])
                Vl[:, 1] = cl["z0"] + Vl[:, 1] * (cl["z1"] - cl["z0"])
                Vl[:, 2] *= it["esp"]
                push(mat, (o + Vl[:, :1] * u + Vl[:, 1:2] * v + Vl[:, 2:3] * w) / 1000.0, _CF)
        else:
            Vl, F = _prisma(it["contorno"])
            Vl[:, 2] *= it["esp"]
            push(mat, (o + Vl[:, :1] * u + Vl[:, 1:2] * v + Vl[:, 2:3] * w) / 1000.0, F)
    return {k: (np.vstack(v[0]), np.vstack(v[1])) for k, v in grupos.items()}


def render(res: dict, vistas=None, largura: int = 1600, altura: int = 900, spp: int = 96, orcamento_s: float | None = 240):
    def princ(rgb, rough, spec=0.5):
        return {"type": "twosided", "bsdf": {"type": "principled", "base_color": {"type": "rgb", "value": list(rgb)}, "roughness": rough, "specular": spec}}
    mats = {"betao": princ((0.62, 0.62, 0.60), 0.85, 0.25), "tijolo": princ((0.70, 0.36, 0.22), 0.9, 0.2)}
    return _render(res, vistas, largura, altura, spp, orcamento_s, gm=malhas(res), materiais=mats)
