"""Render fotorrealista da estrutura LSF montada (Mitsuba 3, sol + céu físicos) — mesma geometria que o cálculo.

Cada perfil é triangulado a partir do contorno real da sua secção (C / U / fita com espessura) e posicionado com a origem e
os eixos calculados pelo motor; as placas (OSB) são caixas com os recortes dos vãos. Nada é desenhado por IA.
Sem Mitsuba → ImportError tratado pelo chamador (o dossier sai sem render).
"""
from __future__ import annotations

import math
import os
import tempfile
import time

import numpy as np

from .geom import section_outline


def _ear_clip(pts):
    """Triangulação de um polígono simples (lista (u, v)) por orelhas → lista de índices (i, j, k)."""
    n = len(pts)
    idx = list(range(n))
    area = sum(pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1] for i in range(n))
    if area < 0:
        idx.reverse()
    tris = []

    def inside(p, a, b, c):
        def s(p1, p2, p3):
            return (p1[0] - p3[0]) * (p2[1] - p3[1]) - (p2[0] - p3[0]) * (p1[1] - p3[1])
        d1, d2, d3 = s(p, a, b), s(p, b, c), s(p, c, a)
        return not ((d1 < 0 or d2 < 0 or d3 < 0) and (d1 > 0 or d2 > 0 or d3 > 0))

    guard = 0
    while len(idx) > 3 and guard < 10000:
        guard += 1
        for k in range(len(idx)):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % len(idx)]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) <= 1e-12:
                continue
            if any(inside(pts[j], a, b, c) for j in idx if j not in (i0, i1, i2)):
                continue
            tris.append((i0, i1, i2))
            idx.pop(k)
            break
        else:
            break
    if len(idx) == 3:
        tris.append(tuple(idx))
    return tris


_SEC = {}


def _sec_mesh(p):
    """(vértices locais (u, v, w∈{0,1}), faces) de um prisma de secção p (comprimento unitário)."""
    key = (p["tipo"], p["h"], p.get("b"), p.get("c"), p["t"])
    if key in _SEC:
        return _SEC[key]
    pts = section_outline(p)
    n = len(pts)
    V = [(u, v, 0.0) for u, v in pts] + [(u, v, 1.0) for u, v in pts]
    F = []
    for a, b, c in _ear_clip(pts):
        F.append((a, c, b))
        F.append((a + n, b + n, c + n))
    for i in range(n):
        j = (i + 1) % n
        F.append((i, j, j + n))
        F.append((i, j + n, i + n))
    _SEC[key] = (np.array(V, dtype=np.float64), np.array(F, dtype=np.int64))
    return _SEC[key]


def malhas(res: dict, com_placas: bool = True, so_pisos_inf: float | None = None):
    """→ {material: (V, F)} em metros."""
    grupos = {}

    def push(mat, V, F):
        g = grupos.setdefault(mat, [[], [], 0])
        g[0].append(V)
        g[1].append(F + g[2])
        g[2] += len(V)

    for m in res["membros"]:
        if so_pisos_inf is not None and m["bbox"]["min"][2] > so_pisos_inf:
            continue
        Vl, F = _sec_mesh(m["sec"])
        o, u, v, w = (np.array(m[k], dtype=np.float64) for k in ("o", "u", "v", "w"))
        V = o + Vl[:, :1] * u + Vl[:, 1:2] * v + Vl[:, 2:3] * (w * m["L"])
        mat = "aco_verga" if m["tipoPeca"] in ("Verga",) else "aco"
        push(mat, V / 1000.0, F)
    if com_placas:
        cube = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64)
        cf = np.array([[0, 2, 1], [0, 3, 2], [4, 5, 6], [4, 6, 7], [0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]])
        for p in res["placas"]:
            if p["placa"] == "ETICS" or str(p["placa"]).upper().startswith("GC"):
                continue
            pl = p["plano"]
            for r in p["pecas"]:
                dx, dz = r["x1"] - r["x0"], r["z1"] - r["z0"]
                if pl["tipo"] == "parede":
                    if so_pisos_inf is not None and pl["z0"] + r["z0"] > so_pisos_inf:
                        continue
                    o = np.array([pl["A"][0] + pl["d"][0] * r["x0"] + pl["n"][0] * pl["y"], pl["A"][1] + pl["d"][1] * r["x0"] + pl["n"][1] * pl["y"], pl["z0"] + r["z0"]])
                    a, b, c = np.array(pl["d"]) * dx, np.array(pl["n"]) * pl["esp"], np.array([0, 0, dz])
                elif pl["tipo"] == "piso":
                    o = np.array([pl["O"][0] + pl["Pd"][0] * r["x0"] + pl["Sd"][0] * r["z0"], pl["O"][1] + pl["Pd"][1] * r["x0"] + pl["Sd"][1] * r["z0"], pl["z"]])
                    a, b, c = np.array(pl["Pd"]) * dx, np.array(pl["Sd"]) * dz, np.array([0, 0, pl["esp"]])
                else:
                    if so_pisos_inf is not None:
                        continue
                    o = np.array(pl["O"]) + np.array(pl["U"]) * r["x0"] + np.array(pl["Vv"]) * r["z0"]
                    a, b, c = np.array(pl["U"]) * dx, np.array(pl["Vv"]) * dz, np.array(pl["N"]) * pl["esp"]
                V = o + cube[:, :1] * a + cube[:, 1:2] * b + cube[:, 2:3] * c
                push("osb", V / 1000.0, cf)
    return {k: (np.vstack(v[0]), np.vstack(v[1])) for k, v in grupos.items()}


def _materiais():
    def princ(rgb, rough, spec=0.5, metal=0.0):
        return {"type": "principled", "base_color": {"type": "rgb", "value": list(rgb)}, "roughness": rough, "specular": spec, "metallic": metal}
    return {
        "aco": {"type": "twosided", "bsdf": princ((0.70, 0.72, 0.74), 0.48, 0.5, 0.55)},          # aço galvanizado Z275
        "aco_verga": {"type": "twosided", "bsdf": princ((0.64, 0.66, 0.68), 0.45, 0.5, 0.6)},
        "osb": {"type": "twosided", "bsdf": princ((0.70, 0.52, 0.30), 0.85, 0.25)},
        "laje": {"type": "twosided", "bsdf": princ((0.58, 0.57, 0.55), 0.9, 0.2)},
        "relva": {"type": "twosided", "bsdf": princ((0.17, 0.24, 0.11), 0.95, 0.1)},
        "saibro": {"type": "twosided", "bsdf": princ((0.52, 0.48, 0.42), 0.95, 0.1)},
    }


def render(res: dict, vistas=None, largura: int = 1600, altura: int = 900, spp: int = 96, com_placas: bool = False,
           orcamento_s: float | None = 240) -> list[tuple[str, bytes]]:
    """→ [(nome, PNG)] — estrutura LSF montada (sem acabamentos)."""
    from engines.calc_lots.render3d import _mi, _png, _ply, _tonemap
    mi = _mi()
    gm = malhas(res, com_placas=com_placas)
    allV = np.vstack([v for v, _ in gm.values()])
    (x0, y0, z0), (x1, y1, z1) = allV.min(0), allV.max(0)
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
        mats = _materiais()
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
            m = 14.0
            sc["obj_laje"] = {"type": "cube", "to_world": mi.ScalarTransform4f().translate([cx, cy, z0 - 0.15]).scale([(x1 - x0) / 2 + 0.3, (y1 - y0) / 2 + 0.3, 0.15]),
                          "bsdf": {"type": "ref", "id": "laje"}}
            sc["obj_terreno"] = {"type": "rectangle", "to_world": mi.ScalarTransform4f().translate([cx, cy, z0 - 0.30]).scale([diag * m, diag * m, 1]),
                             "bsdf": {"type": "ref", "id": "relva"}}
            sc["obj_estaleiro"] = {"type": "rectangle", "to_world": mi.ScalarTransform4f().translate([cx, cy, z0 - 0.29]).scale([(x1 - x0) / 2 + 2.5, (y1 - y0) / 2 + 2.5, 1]),
                                   "bsdf": {"type": "ref", "id": "saibro"}}
            for nm, fn in files.items():
                sc["m_" + nm] = {"type": "ply", "filename": fn, "bsdf": {"type": "ref", "id": nm}, "face_normals": True}
            img = mi.render(mi.load_dict(sc), spp=spp)
            out.append((nome, _png(_tonemap(img))))
    return out
