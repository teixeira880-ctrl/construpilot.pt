"""Obtém o MDT de uma zona de Portugal continental numa grelha regular PT-TM06.

Ordem das fontes (a primeira que responder):
  1. DGT LiDAR — MDT 50 cm (zonas até 0,36 km²) ou 2 m (até 9 km²), oficial, exatidão vertical < 10 cm;
  2. altimetria de recurso já usada no licenciamento (Google Elevation se houver chave, senão EU-DEM 25 m Copernicus),
     marcada como INDICATIVA.
Nunca se inventam cotas: sem fonte disponível devolve-se erro.
"""
from __future__ import annotations

import asyncio
import logging
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import cdd, geotiff, pttm06 as TM
from .geotiff import Raster

log = logging.getLogger(__name__)

PT_BBOX = (-9.6, 36.9, -6.1, 42.2)        # Portugal continental (lon_min, lat_min, lon_max, lat_max)
MAX_LADO_M = 3000.0                        # zona máxima analisada: 3 km × 3 km
MAX_PX = 900                               # grelha máxima de análise (lado)


class MdtErro(RuntimeError):
    pass


def dentro_de_portugal(lat: float, lon: float) -> bool:
    return PT_BBOX[1] <= lat <= PT_BBOX[3] and PT_BBOX[0] <= lon <= PT_BBOX[2]


def caixa_tm(pontos_ll: Sequence[Tuple[float, float]], margem_m: float) -> Tuple[float, float, float, float]:
    lat = np.array([p[0] for p in pontos_ll])
    lon = np.array([p[1] for p in pontos_ll])
    x, y = TM.para_tm(lat, lon)
    return float(x.min() - margem_m), float(y.min() - margem_m), float(x.max() + margem_m), float(y.max() + margem_m)


def _caixa_ll(cx: Tuple[float, float, float, float]) -> Tuple[float, float, float, float]:
    xs = np.array([cx[0], cx[2], cx[0], cx[2]])
    ys = np.array([cx[1], cx[1], cx[3], cx[3]])
    la, lo = TM.para_ll(xs, ys)
    return float(lo.min()), float(la.min()), float(lo.max()), float(la.max())


def _grelha_vazia(cx, res: float) -> Raster:
    x0 = math.floor(cx[0] / res) * res
    y1 = math.ceil(cx[3] / res) * res
    nx = int(math.ceil((cx[2] - x0) / res))
    ny = int(math.ceil((y1 - cx[1]) / res))
    return Raster(np.full((ny, nx), np.nan, dtype=np.float32), x0, y1, res, res)


def _colar(dest: Raster, src: Raster) -> None:
    """Copia src para dest (vizinho mais próximo no centro de cada célula de dest)."""
    ny, nx = dest.z.shape
    xc = dest.x0 + (np.arange(nx) + 0.5) * dest.px
    yc = dest.y0 - (np.arange(ny) + 0.5) * dest.py
    ci = np.floor((xc - src.x0) / src.px).astype(int)
    ri = np.floor((src.y0 - yc) / src.py).astype(int)
    okc = (ci >= 0) & (ci < src.z.shape[1])
    okr = (ri >= 0) & (ri < src.z.shape[0])
    if not okc.any() or not okr.any():
        return
    cols, rows = np.where(okc)[0], np.where(okr)[0]
    bloco = src.z[np.ix_(ri[rows], ci[cols])]
    alvo = dest.z[np.ix_(rows, cols)]
    m = ~np.isnan(bloco)
    alvo[m] = bloco[m]
    dest.z[np.ix_(rows, cols)] = alvo


def reamostrar(r: Raster, res: float) -> Raster:
    """Reduz a resolução por média de blocos (fator inteiro) — conserva as cotas médias."""
    f = int(round(res / r.px))
    if f <= 1:
        return r
    ny, nx = (r.z.shape[0] // f) * f, (r.z.shape[1] // f) * f
    with np.errstate(all="ignore"):
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            z = np.nanmean(r.z[:ny, :nx].reshape(ny // f, f, nx // f, f), axis=(1, 3)).astype(np.float32)
    return Raster(z, r.x0, r.y0, r.px * f, r.py * f)


async def _dgt(cx, colecao: str, res: float) -> Raster:
    folhas = await cdd.pesquisar(_caixa_ll(cx), colecao)
    if not folhas:
        raise MdtErro(f"sem folhas {colecao} na DGT para esta zona")
    if len(folhas) > 16:
        raise MdtErro("zona demasiado grande para o MDT LiDAR")
    sem = asyncio.Semaphore(4)

    async def uma(f):
        async with sem:
            b = await cdd.folha(colecao, f["id"], f["url"])
        return await asyncio.to_thread(geotiff.ler, b)

    rasters = await asyncio.gather(*(uma(f) for f in folhas), return_exceptions=True)
    bons = [r for r in rasters if isinstance(r, Raster)]
    for r in rasters:
        if not isinstance(r, Raster):
            log.warning("MDT DGT: folha ilegível: %s", r)
    if not bons:
        raise MdtErro("folhas LiDAR da DGT ilegíveis")
    nativa = bons[0].px
    dest = _grelha_vazia(cx, nativa)
    for r in bons:
        _colar(dest, r)
    if np.isnan(dest.z).mean() > 0.5:
        raise MdtErro("cobertura LiDAR incompleta nesta zona")
    return reamostrar(dest, res)


async def _recurso(cx, res_alvo: float) -> Tuple[Raster, Dict[str, Any]]:
    from engines.urbanismo_pt.auto import geo
    lado = max(cx[2] - cx[0], cx[3] - cx[1])
    passo = max(12.5, lado / 36.0)
    g = _grelha_vazia(cx, passo)
    ny, nx = g.z.shape
    xc = g.x0 + (np.arange(nx) + 0.5) * passo
    yc = g.y0 - (np.arange(ny) + 0.5) * passo
    X, Y = np.meshgrid(xc, yc)
    la, lo = TM.para_ll(X.ravel(), Y.ravel())
    r = await geo.elevacoes(list(zip(la.tolist(), lo.tolist())))
    if not r.get("ok"):
        raise MdtErro("nenhuma fonte de altimetria disponível neste momento")
    z = np.array([np.nan if v is None else float(v) for v in r["data"]["z"]], dtype=np.float32).reshape(ny, nx)
    g.z = z
    return g, {"fonte": r.get("fonte") or "altimetria de recurso", "oficial": False,
               "resolucao_nativa_m": r["data"].get("resolucao_m"), "nota": r.get("nota")}


async def obter(pontos_ll: Sequence[Tuple[float, float]], resolucao: Optional[float] = None,
                margem_m: float = 15.0, so_dgt: bool = False) -> Tuple[Raster, Dict[str, Any]]:
    """MDT da zona que envolve os pontos (lat, lon). resolucao: 0.5, 1, 2… ou None (automática)."""
    for a, b in pontos_ll:
        if not dentro_de_portugal(a, b):
            raise MdtErro("a zona tem de ficar em Portugal continental (Açores e Madeira ainda não têm LiDAR da DGT)")
    cx = caixa_tm(pontos_ll, margem_m)
    lx, ly = cx[2] - cx[0], cx[3] - cx[1]
    if max(lx, ly) > MAX_LADO_M:
        raise MdtErro(f"zona demasiado grande ({lx:.0f} × {ly:.0f} m): máximo {MAX_LADO_M:.0f} m de lado")
    lado = max(lx, ly)
    colecao = "MDT-50cm" if lado <= 600 else "MDT-2m"
    nativa = 0.5 if colecao == "MDT-50cm" else 2.0
    res = max(float(resolucao or 0) or nativa, nativa)
    while lado / res > MAX_PX:
        res *= 2
    avisos: List[str] = []
    if cdd.configurado():
        try:
            r = await _dgt(cx, colecao, res)
            return r, {"fonte": cdd.FONTE, "colecao": colecao, "oficial": True, "resolucao_nativa_m": nativa,
                       "resolucao_m": r.px, "url": cdd.SITE,
                       "nota": "MDT LiDAR oficial da DGT (2023-2024), exatidão altimétrica < 10 cm. Não dispensa o "
                               "levantamento topográfico exigido no projeto de licenciamento."}
        except Exception as e:  # noqa: BLE001
            log.warning("MDT DGT indisponível: %s", e)
            if so_dgt:
                raise
            avisos.append(f"MDT LiDAR da DGT indisponível ({e}); usada altimetria de recurso, indicativa.")
    elif so_dgt:
        raise MdtErro("MDT LiDAR da DGT não configurado")
    else:
        avisos.append("Acesso ao MDT LiDAR da DGT por configurar (conta gratuita do CDD): usada altimetria de recurso, indicativa.")
    g, meta = await _recurso(cx, res)
    meta.update({"resolucao_m": g.px, "avisos": avisos})
    return g, meta


async def cotas(pontos_ll: Sequence[Tuple[float, float]]) -> Optional[Dict[str, Any]]:
    """Cota DGT LiDAR em pontos (lat, lon) — None se a DGT não estiver configurada/disponível (o chamador usa o recurso)."""
    if not pontos_ll or not cdd.configurado():
        return None
    try:
        r, meta = await obter(pontos_ll, None, margem_m=6.0, so_dgt=True)
    except Exception as e:  # noqa: BLE001
        log.info("cotas DGT: %s", e)
        return None
    if not meta.get("oficial"):
        return None
    from .analise import amostrar
    lat = np.array([p[0] for p in pontos_ll])
    lon = np.array([p[1] for p in pontos_ll])
    x, y = TM.para_tm(lat, lon)
    z = amostrar(r, x, y)
    if np.isnan(z).any():
        return None
    return {"z": [round(float(v), 2) for v in z], "resolucao_m": r.px, "fonte": meta["fonte"], "url": meta.get("url"),
            "nota": meta["nota"]}
