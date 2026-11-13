"""Copernicus DEM GLO-30 — segunda fonte oficial de altimetria (depois do MDT LiDAR da DGT, em engines.mdt_pt).

COG público da ESA/Copernicus (© DLR e © Airbus Defence and Space, licença Copernicus), quadrículas de 1° × 1°,
30 m, EPSG:4326. É um modelo de SUPERFÍCIE (DSM): inclui edifícios e copas — serve de recurso onde o LiDAR da DGT não
responde (ou nos Açores e Madeira) e de verificação cruzada; nunca substitui o levantamento topográfico.

Cada quadrícula é descarregada uma vez e guardada na cache do MDT (MDT_CACHE_DIR); a leitura usa o leitor GeoTIFF do
MDT Portugal (engines.mdt_pt.geotiff), por isso não há dependências novas.
"""
from __future__ import annotations

import asyncio
import math
import os
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from engines.urbanismo_pt.auto import geo as G

BASE = "https://copernicus-dem-30m.s3.eu-central-1.amazonaws.com"
FONTE = "Copernicus DEM GLO-30 (© DLR/Airbus, ESA Copernicus) — modelo de superfície, 30 m"
MAX_FICHEIRO = 120 * 1024 * 1024
_RAM: "OrderedDict[str, Any]" = OrderedDict()


_TMP: Dict[str, str] = {}


def _pasta() -> str:
    base = os.environ.get("MDT_CACHE_DIR")
    if not base and G._fetch is not G._http:
        # transporte simulado (testes): nunca ler nem escrever a cache real do servidor
        if "d" not in _TMP:
            import tempfile
            _TMP["d"] = tempfile.mkdtemp(prefix="cp_cop_")
        base = _TMP["d"]
    p = os.path.join(base or os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "mdt_cache")),
                     "copernicus")
    os.makedirs(p, exist_ok=True)
    return p


def nome(lat: float, lon: float) -> str:
    la, lo = math.floor(lat), math.floor(lon)
    return (f"Copernicus_DSM_COG_10_{'N' if la >= 0 else 'S'}{abs(la):02d}_00_"
            f"{'E' if lo >= 0 else 'W'}{abs(lo):03d}_00_DEM")


async def _ficheiro(lat: float, lon: float) -> Optional[str]:
    n = nome(lat, lon)
    destino = os.path.join(_pasta(), n + ".tif")
    if os.path.exists(destino):
        return destino
    st, b = await G._get(f"{BASE}/{n}/{n}.tif", None, want="bytes", tries=2, conc=2)
    if not b or b[:2] not in (b"II", b"MM") or len(b) > MAX_FICHEIRO:
        return None                      # 404 = mar (sem quadrícula) ou serviço indisponível
    tmp = destino + ".part"
    with open(tmp, "wb") as f:
        f.write(b)
    os.replace(tmp, destino)
    return destino


def _ler(caminho: str):
    from engines.mdt_pt import geotiff
    r = _RAM.get(caminho)
    if r is None:
        with open(caminho, "rb") as f:
            r = geotiff.ler(f.read())
        _RAM[caminho] = r
        while len(_RAM) > 4:
            _RAM.popitem(last=False)
    else:
        _RAM.move_to_end(caminho)
    return r


async def cotas(pontos: List[Tuple[float, float]]) -> Dict[str, Any]:
    """Cota Copernicus em cada (lat, lon). ok=False se nenhuma quadrícula estiver disponível."""
    from engines.mdt_pt.analise import amostrar
    if not pontos:
        return G._res(False, nota="sem pontos")
    out: List[Optional[float]] = [None] * len(pontos)
    grupos: Dict[str, List[int]] = {}
    for i, (la, lo) in enumerate(pontos):
        grupos.setdefault(nome(la, lo), []).append(i)
    for idx in grupos.values():
        la, lo = pontos[idx[0]]
        cam = await _ficheiro(la, lo)
        if not cam:
            continue
        try:
            r = await asyncio.to_thread(_ler, cam)
        except Exception:  # noqa: BLE001 — ficheiro corrompido: apaga e segue
            try:
                os.remove(cam)
            except OSError:
                pass
            continue
        # quadrícula em graus: x = longitude, y = latitude
        z = amostrar(r, np.array([pontos[i][1] for i in idx]), np.array([pontos[i][0] for i in idx]))
        for i, v in zip(idx, z):
            out[i] = None if not np.isfinite(v) else round(float(v), 2)
    if all(v is None for v in out):
        return G._res(False, nota="Copernicus DEM indisponível")
    return G._res(True, {"z": out, "resolucao_m": 30, "tipo": "DSM"}, FONTE, BASE,
                  "Modelo de superfície de 30 m (inclui edifícios e vegetação): indicativo, não substitui o levantamento topográfico.")


async def verificar(pontos: List[Tuple[float, float]], z_ref: List[Optional[float]]) -> Optional[Dict[str, Any]]:
    """Verificação cruzada de cotas (normalmente do LiDAR da DGT) contra o Copernicus."""
    c = await cotas(pontos)
    if not c["ok"]:
        return None
    difs = [a - b for a, b in zip(z_ref, c["data"]["z"]) if a is not None and b is not None]
    if not difs:
        return None
    return {"fonte": FONTE, "pontos": len(difs), "dif_media_m": round(sum(difs) / len(difs), 2),
            "dif_max_abs_m": round(max(abs(d) for d in difs), 2)}
