"""Zona livre para edificar e implantação recomendada de um edifício no terreno (sobre a grelha do MDT).

1. Zona livre = terreno − afastamentos (frontal medido à frente virada para a via, lateral/tardoz aos restantes
   limites) − REN/RAN − talvegues (+5 m) − declives ≥ 45 %.
2. Aptidão de cada célula: declive, insolação anual, forma do relevo e proximidade da via.
3. Procura da melhor posição e rotação de um retângulo (implantação do edifício) inteiramente na zona livre,
   penalizando a movimentação de terras da plataforma.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import ndimage

from engines.mdt_pt import analise as AN
from engines.mdt_pt import pttm06 as TM
from engines.mdt_pt.geotiff import Raster

PENAL_FORMA = {"vale": 0.0, "base_encosta": 0.5, "encosta": 0.75, "encosta_alta": 0.85, "plano": 1.0, "cumeada": 0.8}


def _xy_celulas(r: Raster) -> Tuple[np.ndarray, np.ndarray]:
    xc, yc = AN.centros(r)
    return np.meshgrid(xc, yc)


def rasterizar(r: Raster, aneis_ll: List[List[List[float]]]) -> np.ndarray:
    """Máscara das células dentro de qualquer dos anéis (lat, lon)."""
    from matplotlib.path import Path
    X, Y = _xy_celulas(r)
    P = np.c_[X.ravel(), Y.ravel()]
    m = np.zeros(r.z.size, dtype=bool)
    for anel in aneis_ll or []:
        if len(anel) < 3:
            continue
        x, y = TM.para_tm(np.array([p[0] for p in anel]), np.array([p[1] for p in anel]))
        m |= Path(np.c_[x, y]).contains_points(P)
    return m.reshape(r.z.shape)


def _dist_via(X: np.ndarray, Y: np.ndarray, via) -> np.ndarray:
    """Distância de cada célula à via: segmento ((xa, ya), (xb, yb)) ou ponto (x, y)."""
    if len(via) == 2 and hasattr(via[0], "__len__"):
        (ax, ay), (bx, by) = via
        vx, vy = bx - ax, by - ay
        L2 = vx * vx + vy * vy or 1e-9
        t = np.clip(((X - ax) * vx + (Y - ay) * vy) / L2, 0, 1)
        return np.hypot(X - (ax + t * vx), Y - (ay + t * vy))
    return np.hypot(X - via[0], Y - via[1])


def zona_livre(r: Raster, mascara: np.ndarray, afast: Dict[str, float], xy_via,
               exclusoes: Optional[np.ndarray] = None) -> Dict[str, Any]:
    """xy_via: ponto (x, y) ou segmento ((xa, ya), (xb, yb)) da via em PT-TM06, ou None."""
    px = r.px
    borda = mascara & ~ndimage.binary_erosion(mascara)
    d_borda = (ndimage.distance_transform_edt(mascara) - 0.5) * px      # do centro da célula ao limite
    # sem via conhecida não se sabe qual é a frente: aplica-se o maior afastamento a todo o perímetro (lado seguro)
    lat = afast.get("lateral", 3.0) if xy_via is not None else max(afast.values() or [3.0])
    livre = mascara & (d_borda >= lat)
    frente = None
    if xy_via is not None and borda.any():
        X, Y = _xy_celulas(r)
        dv = _dist_via(X, Y, xy_via)
        dmin = float(dv[borda].min())
        frente = borda & (dv <= dmin + max(3.0, 2 * px))
        d_frente = ndimage.distance_transform_edt(~frente) * px
        livre &= d_frente >= afast.get("frontal", 5.0)
        # tardoz: limite oposto à frente (células de borda mais afastadas da via)
        dmax = float(dv[borda].max())
        tard = borda & (dv >= dmax - max(3.0, 2 * px))
        livre &= ndimage.distance_transform_edt(~tard) * px >= afast.get("tardoz", 6.0)
    if exclusoes is not None:
        livre &= ~exclusoes
    return {"mascara": livre, "frente": frente, "area_m2": round(float(livre.sum() * px * r.py), 1)}


def aptidao(r: Raster, relevo: Dict[str, Any], mapa_solar: Optional[np.ndarray], xy_via) -> np.ndarray:
    decl = np.nan_to_num(relevo["_decl"])
    a = 0.4 * (1 - np.clip(decl / 25.0, 0, 1))
    if mapa_solar is not None and np.isfinite(mapa_solar).any():
        s = mapa_solar
        lo, hi = np.nanpercentile(s, 5), np.nanpercentile(s, 95)
        a = a + 0.3 * np.nan_to_num(np.clip((s - lo) / max(hi - lo, 1e-6), 0, 1), nan=0.5)
    else:
        a = a + 0.15
    forma = relevo["_forma"]
    pf = np.vectorize(lambda f: PENAL_FORMA.get(f, 0.7))(forma).astype(float)
    a = a + 0.2 * pf
    if xy_via is not None:
        X, Y = _xy_celulas(r)
        dv = np.hypot(X - xy_via[0], Y - xy_via[1])
        a = a + 0.1 * (1 - np.clip(dv / 80.0, 0, 1))
    else:
        a = a + 0.05
    return a


def _retangulo(cx: float, cy: float, w: float, d: float, ang: float) -> np.ndarray:
    """Cantos (TM) de um retângulo w (ao longo da fachada principal) × d, fachada principal virada para `ang` (azimute)."""
    t = math.radians(ang)
    nx_, ny_ = math.sin(t), math.cos(t)           # normal da fachada principal
    ux, uy = ny_, -nx_                             # direção ao longo da fachada
    hw, hd = w / 2, d / 2
    return np.array([[cx + ux * sw * hw + nx_ * sd * hd, cy + uy * sw * hw + ny_ * sd * hd]
                     for sw, sd in ((-1, 1), (1, 1), (1, -1), (-1, -1))])


def _mascara_poly(r: Raster, cantos: np.ndarray, X: np.ndarray, Y: np.ndarray, janela) -> Optional[np.ndarray]:
    from matplotlib.path import Path
    i0, i1, j0, j1 = janela
    sub = np.c_[X[i0:i1, j0:j1].ravel(), Y[i0:i1, j0:j1].ravel()]
    m = Path(cantos).contains_points(sub).reshape(i1 - i0, j1 - j0)
    return m


def recomendar(r: Raster, mascara: np.ndarray, livre: np.ndarray, apt: np.ndarray, relevo: Dict[str, Any],
               largura: float, profundidade: float, azimute_fachada: float, max_cand: int = 60) -> Dict[str, Any]:
    """Melhor posição/rotação do retângulo largura × profundidade dentro da zona livre."""
    if not livre.any():
        return {"ok": False, "nota": "Não há zona livre para implantar depois de afastamentos e condicionantes."}
    px = r.px
    X, Y = _xy_celulas(r)
    raio = math.hypot(largura, profundidade) / 2
    # centros candidatos: células da zona livre afastadas do limite dela pelo menos meio lado menor
    folga = ndimage.distance_transform_edt(livre) * px
    cand = livre & (folga >= min(largura, profundidade) / 2 - px)
    if not cand.any():
        cand = livre & (folga >= folga.max() - px / 2)
    ii, jj = np.nonzero(cand)
    ordem = np.argsort(-apt[ii, jj])
    passo = max(1, len(ordem) // (max_cand * 3))
    escolha = ordem[::passo][: max_cand * 3]
    # escolher candidatos espaçados
    sel: List[int] = []
    for k in escolha:
        if all(math.hypot(X[ii[k], jj[k]] - X[ii[s], jj[s]], Y[ii[k], jj[k]] - Y[ii[s], jj[s]]) > max(2 * px, raio / 3) for s in sel):
            sel.append(int(k))
        if len(sel) >= max_cand:
            break
    expo = relevo.get("exposicao_graus")
    angs = {round(azimute_fachada) % 360, (round(azimute_fachada) + 15) % 360, (round(azimute_fachada) - 15) % 360}
    if expo is not None:
        angs.add(round(expo) % 360)                              # fachada virada para onde a encosta desce
    best = None
    rc = int(math.ceil(raio / px)) + 1
    ny, nx = r.z.shape
    zfill = AN._preencher_nan(r.z.astype(np.float64))
    for k in sel:
        i, j = ii[k], jj[k]
        cx, cy = float(X[i, j]), float(Y[i, j])
        jan = (max(0, i - rc), min(ny, i + rc + 1), max(0, j - rc), min(nx, j + rc + 1))
        for ang in angs:
            cantos = _retangulo(cx, cy, largura, profundidade, ang)
            m = _mascara_poly(r, cantos, X, Y, jan)
            if m is None or not m.any():
                continue
            # verificação com o retângulo alargado de 1 célula: a pegada real nunca sai da zona livre por discretização
            larga = _mascara_poly(r, _retangulo(cx, cy, largura + 2 * px, profundidade + 2 * px, ang), X, Y, jan)
            sub_livre = livre[jan[0]:jan[1], jan[2]:jan[3]]
            if (larga & ~sub_livre).any():
                continue
            zz = zfill[jan[0]:jan[1], jan[2]:jan[3]][m]
            c = float(np.median(zz))
            terras = float(np.abs(zz - c).mean())                 # m de corte/aterro médio
            dif_az = abs(((ang - azimute_fachada) + 180) % 360 - 180)
            score = float(apt[jan[0]:jan[1], jan[2]:jan[3]][m].mean()) - 0.08 * terras - 0.002 * dif_az
            if best is None or score > best[0]:
                best = (score, cx, cy, ang, cantos, jan, m)
    if best is None:
        return {"ok": False, "nota": f"O edifício de {largura:.0f} × {profundidade:.0f} m não cabe na zona livre: reduza a "
                                    "implantação ou reveja os afastamentos.", "zona_livre_m2": round(float(livre.sum() * px * r.py), 1)}
    score, cx, cy, ang, cantos, jan, m = best
    full = np.zeros(r.z.shape, dtype=bool)
    full[jan[0]:jan[1], jan[2]:jan[3]] = m
    mv = AN.movimento_terras(r, full)
    decl = np.nan_to_num(relevo["_decl"])[full]
    zz = r.z[full]
    la, lo = TM.para_ll(cantos[:, 0], cantos[:, 1])
    cla, clo = TM.ponto_ll(cx, cy)
    return {"ok": True, "centro_latlon": [round(cla, 7), round(clo, 7)], "centro_tm": [round(cx, 2), round(cy, 2)],
            "poligono_latlon": [[round(float(a), 7), round(float(b), 7)] for a, b in zip(la, lo)],
            "poligono_tm": [[round(float(a), 2), round(float(b), 2)] for a, b in cantos],
            "largura_m": largura, "profundidade_m": profundidade, "area_m2": round(largura * profundidade, 1),
            "azimute_fachada_principal": float(ang),
            "cota_soleira_sugerida": mv.get("cota_equilibrio"),
            "terreno_sob_edificio": {"cota_min": round(float(np.nanmin(zz)), 2), "cota_max": round(float(np.nanmax(zz)), 2),
                                     "desnivel_m": round(float(np.nanmax(zz) - np.nanmin(zz)), 2),
                                     "declive_medio_pct": round(float(decl.mean()), 1)},
            "movimento_terras": mv, "aptidao": round(score, 3),
            "solucao_desnivel": ("plataforma única" if (np.nanmax(zz) - np.nanmin(zz)) < 1.2 else
                                 "meio-piso / pisos desnivelados" if (np.nanmax(zz) - np.nanmin(zz)) < 3.5 else
                                 "cave ou piso enterrado a montante com muros de suporte"),
            "_mascara": full}
