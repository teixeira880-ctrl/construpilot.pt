"""BUPi — Representações Gráficas Georreferenciadas (RGG) publicadas pela eBUPi em dados abertos.

Serviço oficial WMS (ArcGIS Server da eBUPi), atualizado diariamente:
  Continente: https://geo.bupi.gov.pt/gisbupi/services/opendata/RGG_DadosGovPT/MapServer/WMSServer
  Madeira:    https://geo.bupi.gov.pt/gisbupi/services/opendata/RGG_DadosGovPT_Madeira/MapServer/WMSServer
Camada «0», consultável (GetFeatureInfo em application/geo+json).

O mapa usa o mesmo serviço diretamente (imagem); aqui consultamos os atributos em pontos, para detetar
sobreposições entre o terreno que o utilizador desenha e RGG já existentes.
"""
from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from engines.urbanismo_pt.auto import geo as G

WMS_CONTINENTE = "https://geo.bupi.gov.pt/gisbupi/services/opendata/RGG_DadosGovPT/MapServer/WMSServer"
WMS_MADEIRA = "https://geo.bupi.gov.pt/gisbupi/services/opendata/RGG_DadosGovPT_Madeira/MapServer/WMSServer"
FONTE = "eBUPi — Dados Abertos, RGG (Representações Gráficas Georreferenciadas)"


def wms_para(lat: float, lon: float) -> Optional[str]:
    if lon < -15.5 and 32.0 <= lat <= 33.5:
        return WMS_MADEIRA
    if -9.6 <= lon <= -6.0 and 36.8 <= lat <= 42.3:
        return WMS_CONTINENTE
    return None            # Açores: sem RGG publicadas pela eBUPi


def _params(lat: float, lon: float, d: float = 0.00005) -> Dict[str, Any]:
    # WMS 1.3.0 com CRS:84 → eixo (lon, lat), sem a inversão do EPSG:4326
    return {"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetFeatureInfo", "LAYERS": "0", "QUERY_LAYERS": "0",
            "STYLES": "", "CRS": "CRS:84", "BBOX": f"{lon - d},{lat - d},{lon + d},{lat + d}",
            "WIDTH": "101", "HEIGHT": "101", "I": "50", "J": "50", "INFO_FORMAT": "application/geo+json",
            "FEATURE_COUNT": "10", "FORMAT": "image/png"}


def _limpar(p: dict) -> Dict[str, str]:
    out = {}
    for k, v in (p or {}).items():
        if v is None or isinstance(v, (dict, list)):
            continue
        s = str(v).strip()
        if s and s.lower() not in ("null", "<null>") and not k.lower().startswith(("shape", "objectid", "globalid")):
            out[str(k)] = s
    return out


def _chave(p: Dict[str, str]) -> str:
    for k, v in p.items():
        kl = k.lower()
        if "processo" in kl or kl in ("id_rgg", "rgg", "codigo", "cod_rgg", "id"):
            return v
    return "|".join(f"{k}={v}" for k, v in sorted(p.items()))[:200]


async def rgg_no_ponto(lat: float, lon: float) -> Dict[str, Any]:
    """RGG que contém o ponto (atributos públicos). ok=False só se o serviço não responder."""
    url = wms_para(lat, lon)
    if not url:
        return G._res(True, {"rgg": [], "cobertura": False}, FONTE, None, "a eBUPi não publica RGG para esta região")
    st, js = await G._get(url, _params(lat, lon), tries=2, conc=3)
    if js is None or not isinstance(js, dict):
        return G._res(False, nota="serviço de RGG do BUPi indisponível", url=url)
    feats = js.get("features") or []
    rgg = []
    for f in feats:
        p = _limpar(f.get("properties") or f.get("attributes") or {})
        if p:
            rgg.append({"id": _chave(p), "atributos": p, "geometry": f.get("geometry")})
    return G._res(True, {"rgg": rgg, "cobertura": True}, FONTE, url)


async def rgg_no_terreno(pontos: List[List[float]], prazo_s: float = 25.0) -> Dict[str, Any]:
    """Consulta as RGG em pontos de amostragem do terreno (interior + vértices) e agrega por RGG.

    Devolve as RGG encontradas e, para cada uma, a fração dos pontos de amostragem que caem nela —
    uma medida indicativa de sobreposição (o serviço não devolve a geometria completa).
    """
    if not pontos:
        return G._res(False, nota="sem pontos")
    url = wms_para(*pontos[0])
    if not url:
        return G._res(True, {"rgg": [], "cobertura": False, "amostras": 0}, FONTE, None,
                      "a eBUPi não publica RGG para esta região")
    sem = asyncio.Semaphore(4)

    async def um(p):
        async with sem:
            return await rgg_no_ponto(p[0], p[1])

    tarefas = [asyncio.ensure_future(um(p)) for p in pontos]
    feitas, pend = await asyncio.wait(tarefas, timeout=prazo_s)
    for t in pend:
        t.cancel()
    vistos: Dict[str, Dict[str, Any]] = {}
    ok_n = 0
    for t, p in zip(tarefas, pontos):
        if t not in feitas or t.exception():
            continue
        r = t.result()
        if not r["ok"]:
            continue
        ok_n += 1
        for g in r["data"]["rgg"]:
            e = vistos.setdefault(g["id"], {"id": g["id"], "atributos": g["atributos"], "pontos": 0})
            e["pontos"] += 1
    if ok_n == 0:
        return G._res(False, nota="serviço de RGG do BUPi indisponível", url=url)
    lista = sorted(vistos.values(), key=lambda e: -e["pontos"])
    for e in lista:
        e["fracao_amostras"] = round(e["pontos"] / ok_n, 3)
    return G._res(True, {"rgg": lista, "cobertura": True, "amostras": ok_n, "amostras_pedidas": len(pontos),
                         "incompleta": ok_n < len(pontos)}, FONTE, url)
