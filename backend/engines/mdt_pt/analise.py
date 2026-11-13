"""Análises do terreno sobre o MDT: estatísticas, declives, exposição, curvas de nível, escorrência (linhas de água
potenciais), perfil longitudinal, movimentos de terras e malha 3D. Tudo em PT-TM06 (metros), sem cotas inventadas.
"""
from __future__ import annotations

import heapq
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import pttm06 as TM
from .geotiff import Raster

# Classes de declive (%) usadas nas cartas de declives para edificação
CLASSES_DECLIVE = [
    (0, 5, "0–5 % · plano", "#1a9850"),
    (5, 10, "5–10 % · suave", "#91cf60"),
    (10, 15, "10–15 % · moderado", "#d9ef8b"),
    (15, 25, "15–25 % · acentuado", "#fee08b"),
    (25, 50, "25–50 % · muito acentuado", "#fc8d59"),
    (50, 1e9, "> 50 % · escarpado", "#d73027"),
]


# ------------------------------------------------------------------ utilitários
def centros(r: Raster) -> Tuple[np.ndarray, np.ndarray]:
    ny, nx = r.z.shape
    return r.x0 + (np.arange(nx) + 0.5) * r.px, r.y0 - (np.arange(ny) + 0.5) * r.py


def amostrar(r: Raster, x, y) -> np.ndarray:
    """Interpolação bilinear nas coordenadas TM (x, y). NaN fora da grelha."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    fc = (x - r.x0) / r.px - 0.5
    fr = (r.y0 - y) / r.py - 0.5
    ny, nx = r.z.shape
    c0 = np.clip(np.floor(fc).astype(int), 0, nx - 2)
    r0 = np.clip(np.floor(fr).astype(int), 0, ny - 2)
    tc = np.clip(fc - c0, 0, 1)
    tr = np.clip(fr - r0, 0, 1)
    z = r.z
    v = (z[r0, c0] * (1 - tc) * (1 - tr) + z[r0, c0 + 1] * tc * (1 - tr)
         + z[r0 + 1, c0] * (1 - tc) * tr + z[r0 + 1, c0 + 1] * tc * tr)
    fora = (fc < -0.5) | (fr < -0.5) | (fc > nx - 0.5) | (fr > ny - 0.5)
    return np.where(fora, np.nan, v)


def mascara_poligono(r: Raster, poligono_ll: Optional[Sequence[Tuple[float, float]]]) -> np.ndarray:
    if not poligono_ll or len(poligono_ll) < 3:
        return np.ones(r.z.shape, dtype=bool)
    from matplotlib.path import Path
    lat = np.array([p[0] for p in poligono_ll])
    lon = np.array([p[1] for p in poligono_ll])
    px, py = TM.para_tm(lat, lon)
    xc, yc = centros(r)
    X, Y = np.meshgrid(xc, yc)
    m = Path(np.c_[px, py]).contains_points(np.c_[X.ravel(), Y.ravel()]).reshape(r.z.shape)
    if not m.any():                # polígono menor do que uma célula: usar a célula do centroide
        i = int(np.clip((r.y0 - py.mean()) / r.py, 0, r.z.shape[0] - 1))
        j = int(np.clip((px.mean() - r.x0) / r.px, 0, r.z.shape[1] - 1))
        m[i, j] = True
    return m


def _preencher_nan(z: np.ndarray) -> np.ndarray:
    """Substitui NaN pelo vizinho válido mais próximo (só para cálculo de gradientes nas bordas)."""
    if not np.isnan(z).any():
        return z
    z = z.copy()
    for _ in range(50):
        m = np.isnan(z)
        if not m.any():
            break
        p = np.pad(z, 1, mode="edge")
        viz = np.stack([p[:-2, 1:-1], p[2:, 1:-1], p[1:-1, :-2], p[1:-1, 2:]])
        with np.errstate(all="ignore"):
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                media = np.nanmean(viz, axis=0)
        z[m] = media[m]
    z[np.isnan(z)] = np.nanmean(z) if not np.isnan(z).all() else 0.0
    return z


# ------------------------------------------------------------------ derivadas
def declive_exposicao(r: Raster) -> Tuple[np.ndarray, np.ndarray]:
    """Declive (%) e exposição (graus, 0 = norte, sentido horário, para onde a encosta está virada)."""
    z = _preencher_nan(r.z.astype(np.float64))
    dzdy_lin, dzdx = np.gradient(z, r.py, r.px)
    dzdy = -dzdy_lin                     # linhas crescem para sul
    decl = np.hypot(dzdx, dzdy) * 100.0
    expo = (np.degrees(np.arctan2(-dzdx, -dzdy)) + 360.0) % 360.0
    nan = np.isnan(r.z)
    decl[nan] = np.nan
    expo[nan] = np.nan
    return decl.astype(np.float32), expo.astype(np.float32)


def sombreado(r: Raster, azimute: float = 315.0, altitude: float = 45.0, exagero: float = 1.0) -> np.ndarray:
    z = _preencher_nan(r.z.astype(np.float64)) * exagero
    dzdy_lin, dzdx = np.gradient(z, r.py, r.px)
    dzdy = -dzdy_lin
    slope = np.arctan(np.hypot(dzdx, dzdy))
    aspect = np.arctan2(-dzdx, -dzdy)
    az, alt = math.radians(azimute), math.radians(altitude)
    hs = np.sin(alt) * np.cos(slope) + np.cos(alt) * np.sin(slope) * np.cos(az - aspect)
    return np.clip(hs, 0, 1).astype(np.float32)


def classes_declive(decl: np.ndarray, mascara: np.ndarray, area_celula: float) -> List[Dict[str, Any]]:
    v = decl[mascara & ~np.isnan(decl)]
    tot = max(v.size, 1)
    out = []
    for lo, hi, nome, cor in CLASSES_DECLIVE:
        n = int(((v >= lo) & (v < hi)).sum())
        out.append({"classe": nome, "min": lo, "max": None if hi > 1e8 else hi, "cor": cor,
                    "area_m2": round(n * area_celula, 1), "pct": round(100.0 * n / tot, 1)})
    return out


def estatisticas(r: Raster, decl: np.ndarray, expo: np.ndarray, mascara: np.ndarray) -> Dict[str, Any]:
    v = r.z[mascara & ~np.isnan(r.z)]
    if v.size == 0:
        return {"ok": False}
    d = decl[mascara & ~np.isnan(decl)]
    e = expo[mascara & ~np.isnan(expo) & (decl > 2)]
    if e.size:
        ang = np.radians(e)
        med = (math.degrees(math.atan2(np.sin(ang).mean(), np.cos(ang).mean())) + 360) % 360
        rumo = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"][int(((med + 22.5) % 360) // 45)]
    else:
        med, rumo = None, "plano"
    area_cel = r.px * r.py
    return {
        "ok": True,
        "cota_min": round(float(v.min()), 2), "cota_max": round(float(v.max()), 2),
        "cota_media": round(float(v.mean()), 2), "desnivel": round(float(v.max() - v.min()), 2),
        "declive_medio_pct": round(float(d.mean()), 1) if d.size else None,
        "declive_max_pct": round(float(np.percentile(d, 99)), 1) if d.size else None,
        "exposicao_graus": None if med is None else round(med, 0), "exposicao": rumo,
        "area_m2": round(float(mascara.sum() * area_cel), 1),
        "tem_desnivel": bool(v.max() - v.min() >= 1.5 or (d.size and d.mean() >= 5)),
    }


# ------------------------------------------------------------------ curvas de nível
def equidistancia_auto(desnivel: float) -> float:
    for e in (0.25, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0):
        if desnivel / e <= 40:
            return e
    return 50.0


def curvas_nivel(r: Raster, equid: float, mestra_cada: int = 5) -> List[Dict[str, Any]]:
    """Curvas de nível em TM: [{"cota", "mestra", "xy": [[x, y], …]}]."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    z = r.z
    if np.isnan(z).all():
        return []
    lo = math.ceil(float(np.nanmin(z)) / equid) * equid
    hi = math.floor(float(np.nanmax(z)) / equid) * equid
    if hi < lo:
        return []
    niveis = np.arange(lo, hi + equid / 2, equid)
    xc, yc = centros(r)
    fig = plt.figure()
    try:
        cs = plt.contour(xc, yc, np.ma.masked_invalid(z), levels=niveis)
        out = []
        segs_all = cs.allsegs
        for nivel, segs in zip(cs.levels, segs_all):
            mestra = abs((nivel / equid) % mestra_cada) < 1e-6 or abs((nivel / equid) % mestra_cada - mestra_cada) < 1e-6
            for s in segs:
                if len(s) < 2:
                    continue
                out.append({"cota": round(float(nivel), 3), "mestra": bool(mestra),
                            "xy": [[round(float(a), 2), round(float(b), 2)] for a, b in s]})
        return out
    finally:
        plt.close(fig)


# ------------------------------------------------------------------ escorrência (linhas de água potenciais)
_D8 = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def _preencher_depressoes(z: np.ndarray) -> np.ndarray:
    """Priority-flood (Barnes 2014) com ε, para que toda a água encontre saída pela borda."""
    ny, nx = z.shape
    f = z.copy()
    vis = np.zeros(z.shape, dtype=bool)
    h: List[Tuple[float, int, int]] = []
    for i in range(ny):
        for j in (0, nx - 1):
            if not vis[i, j]:
                vis[i, j] = True
                heapq.heappush(h, (f[i, j], i, j))
    for j in range(nx):
        for i in (0, ny - 1):
            if not vis[i, j]:
                vis[i, j] = True
                heapq.heappush(h, (f[i, j], i, j))
    eps = 1e-4
    while h:
        c, i, j = heapq.heappop(h)
        for di, dj in _D8:
            a, b = i + di, j + dj
            if 0 <= a < ny and 0 <= b < nx and not vis[a, b]:
                vis[a, b] = True
                if f[a, b] <= c:
                    f[a, b] = c + eps
                heapq.heappush(h, (f[a, b], a, b))
    return f


def escorrencia(r: Raster, limiar_m2: Optional[float] = None, max_celulas: int = 160_000) -> Dict[str, Any]:
    """Direções D8 + acumulação de fluxo → linhas de água potenciais (talvegues) com a bacia drenada de cada troço."""
    rr = r
    while rr.z.size > max_celulas:
        from .grelha import reamostrar
        rr = reamostrar(rr, rr.px * 2)
    z = _preencher_nan(rr.z.astype(np.float64))
    f = _preencher_depressoes(z)
    ny, nx = f.shape
    dist = np.array([rr.py, math.hypot(rr.px, rr.py), rr.px, math.hypot(rr.px, rr.py)] * 2)
    p = np.pad(f, 1, mode="constant", constant_values=np.inf)
    quedas = np.stack([(f - p[1 + di:1 + di + ny, 1 + dj:1 + dj + nx]) / dist[k] for k, (di, dj) in enumerate(_D8)])
    dirk = np.argmax(quedas, axis=0)
    tem_saida = np.max(quedas, axis=0) > 0
    # acumulação: das células mais altas para as mais baixas
    ordem = np.argsort(-f, axis=None)
    acc = np.ones(ny * nx, dtype=np.float64)
    di = np.array([d[0] for d in _D8])
    dj = np.array([d[1] for d in _D8])
    I, J = np.unravel_index(ordem, f.shape)
    K = dirk[I, J]
    A = I + di[K]
    B = J + dj[K]
    valido = tem_saida[I, J] & (A >= 0) & (A < ny) & (B >= 0) & (B < nx)
    jusante = np.where(valido, A * nx + B, -1)
    for idx, dn in zip(ordem.tolist(), jusante.tolist()):
        if dn >= 0:
            acc[dn] += acc[idx]
    acc = acc.reshape(ny, nx)
    cel = rr.px * rr.py
    area_tot = ny * nx * cel
    limiar = limiar_m2 or max(1500.0, 0.02 * area_tot)
    rio = acc * cel >= limiar
    jus = jusante.reshape(-1)
    jus_de = np.full(ny * nx, -1)
    jus_de[ordem] = jus
    # cabeceiras: células de rio sem nenhum afluente de rio
    afl = np.zeros(ny * nx, dtype=np.int32)
    rf = rio.ravel()
    for idx in np.where(rf)[0]:
        d = jus_de[idx]
        if d >= 0 and rf[d]:
            afl[d] += 1
    xc, yc = centros(rr)
    linhas = []
    visit = np.zeros(ny * nx, dtype=bool)
    inicios = [i for i in np.where(rf)[0] if afl[i] == 0]
    for ini in inicios:
        cur, pts = ini, []
        while cur >= 0 and rf[cur]:
            a, b = divmod(int(cur), nx)
            pts.append([round(float(xc[b]), 2), round(float(yc[a]), 2)])
            if visit[cur]:
                break
            visit[cur] = True
            cur = jus_de[cur]
        if len(pts) >= 2:
            fim = pts[-1]
            ia, ib = int(round((yc[0] - fim[1]) / rr.py)), int(round((fim[0] - xc[0]) / rr.px))
            bacia = float(acc[min(max(ia, 0), ny - 1), min(max(ib, 0), nx - 1)] * cel)
            linhas.append({"xy": pts, "bacia_m2": round(bacia, 0)})
    return {"linhas": linhas, "limiar_m2": round(limiar, 0), "acumulacao": acc.astype(np.float32), "raster": rr}


# ------------------------------------------------------------------ perfil e volumes
def perfil(r: Raster, linha_ll: Sequence[Tuple[float, float]], passo: Optional[float] = None) -> List[Dict[str, float]]:
    lat = np.array([p[0] for p in linha_ll])
    lon = np.array([p[1] for p in linha_ll])
    x, y = TM.para_tm(lat, lon)
    passo = passo or max(r.px, 0.5)
    out, acum = [], 0.0
    for k in range(len(x) - 1):
        L = math.hypot(x[k + 1] - x[k], y[k + 1] - y[k])
        n = max(int(L / passo), 1)
        t = np.linspace(0, 1, n, endpoint=(k == len(x) - 2))
        xs, ys = x[k] + t * (x[k + 1] - x[k]), y[k] + t * (y[k + 1] - y[k])
        zs = amostrar(r, xs, ys)
        for tt, zz in zip(t, zs):
            if not np.isnan(zz):
                out.append({"d": round(acum + float(tt) * L, 2), "z": round(float(zz), 2)})
        acum += L
    return out


def movimento_terras(r: Raster, mascara: np.ndarray, cota: Optional[float] = None) -> Dict[str, Any]:
    """Escavação / aterro para uma plataforma horizontal à cota dada (por omissão: a cota que equilibra volumes)."""
    v = r.z[mascara & ~np.isnan(r.z)].astype(np.float64)
    if v.size == 0:
        return {"ok": False}
    cel = r.px * r.py
    lo, hi = float(v.min()), float(v.max())
    for _ in range(60):
        mid = (lo + hi) / 2
        if (np.clip(v - mid, 0, None).sum() - np.clip(mid - v, 0, None).sum()) > 0:
            lo = mid
        else:
            hi = mid
    equil = (lo + hi) / 2
    c = equil if cota is None else float(cota)
    esc = float(np.clip(v - c, 0, None).sum() * cel)
    ate = float(np.clip(c - v, 0, None).sum() * cel)
    return {"ok": True, "cota_plataforma": round(c, 2), "cota_equilibrio": round(equil, 2),
            "escavacao_m3": round(esc, 1), "aterro_m3": round(ate, 1), "saldo_m3": round(esc - ate, 1),
            "area_m2": round(v.size * cel, 1),
            "altura_max_escavacao": round(float(max(v.max() - c, 0)), 2),
            "altura_max_aterro": round(float(max(c - v.min(), 0)), 2),
            "nota": "Volumes geométricos (sem empolamento nem taludes); confirmar com levantamento topográfico."}


# ------------------------------------------------------------------ 3D
def malha3d(r: Raster, max_lado: int = 220) -> Dict[str, Any]:
    from .grelha import reamostrar
    rr = r
    while max(rr.z.shape) > max_lado:
        rr = reamostrar(rr, rr.px * 2)
    z = _preencher_nan(rr.z.astype(np.float64))
    ny, nx = z.shape
    return {"nx": nx, "ny": ny, "dx": rr.px, "dy": rr.py, "largura_m": nx * rr.px, "altura_m": ny * rr.py,
            "z_min": round(float(z.min()), 2), "z_max": round(float(z.max()), 2),
            "z": [round(float(v), 2) for v in z.ravel()]}


def tm_para_ll_lista(xy: Sequence[Sequence[float]]) -> List[List[float]]:
    a = np.asarray(xy, dtype=float)
    la, lo = TM.para_ll(a[:, 0], a[:, 1])
    return [[round(float(p), 7), round(float(q), 7)] for p, q in zip(la, lo)]
