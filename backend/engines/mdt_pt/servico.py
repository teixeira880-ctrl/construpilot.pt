"""Orquestração do MDT: pedido (terreno desenhado, ponto + raio, linha de perfil) → análise completa + saídas."""
from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import analise as AN, grelha as GR, saidas as SA, pttm06 as TM
from .geotiff import Raster

_CACHE: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
_MAX = 24


def _chave(p: Dict[str, Any]) -> str:
    base = {k: p.get(k) for k in ("poligono", "centro", "raio_m", "resolucao")}
    return hashlib.sha1(json.dumps(base, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _circulo(lat: float, lon: float, raio: float, n: int = 48) -> List[Tuple[float, float]]:
    x, y = TM.ponto_tm(lat, lon)
    a = np.linspace(0, 2 * math.pi, n, endpoint=False)
    la, lo = TM.para_ll(x + raio * np.cos(a), y + raio * np.sin(a))
    return list(zip(la.tolist(), lo.tolist()))


def _zona(p: Dict[str, Any]) -> Tuple[List[Tuple[float, float]], Optional[List[Tuple[float, float]]]]:
    pol = p.get("poligono")
    if pol and len(pol) >= 3:
        pol = [(float(a), float(b)) for a, b in pol]
        return pol, pol
    c = p.get("centro")
    if not c:
        raise GR.MdtErro("indique o terreno (polígono) ou um ponto")
    raio = float(p.get("raio_m") or 60)
    pts = _circulo(float(c[0]), float(c[1]), raio)
    return pts, None


async def _mdt(p: Dict[str, Any]) -> Dict[str, Any]:
    k = _chave(p)
    if k in _CACHE:
        _CACHE.move_to_end(k)
        return _CACHE[k]
    pts, pol = _zona(p)
    r, meta = await GR.obter(pts, p.get("resolucao"))
    ent = {"r": r, "meta": meta, "pts": pts, "pol": pol, "ts": time.time()}
    _CACHE[k] = ent
    while len(_CACHE) > _MAX:
        _CACHE.popitem(last=False)
    return ent


def _calcular(ent: Dict[str, Any], p: Dict[str, Any]) -> Dict[str, Any]:
    if "calc" in ent and ent["calc"]["equid_pedida"] == p.get("equidistancia") and ent["calc"]["cota"] == p.get("cota_plataforma"):
        return ent["calc"]
    r: Raster = ent["r"]
    mascara = AN.mascara_poligono(r, ent["pol"] or ent["pts"])
    decl, expo = AN.declive_exposicao(r)
    hs = AN.sombreado(r)
    est = AN.estatisticas(r, decl, expo, mascara)
    if not est.get("ok"):
        raise GR.MdtErro("sem cotas válidas na zona")
    classes = AN.classes_declive(decl, mascara, r.px * r.py)
    equid = float(p.get("equidistancia") or 0) or AN.equidistancia_auto(float(np.nanmax(r.z) - np.nanmin(r.z)))
    curvas = AN.curvas_nivel(r, equid)
    esc = AN.escorrencia(r)
    terras = AN.movimento_terras(r, mascara, p.get("cota_plataforma"))
    calc = {"mascara": mascara, "decl": decl, "expo": expo, "hs": hs, "est": est, "classes": classes, "equid": equid,
            "curvas": curvas, "esc": esc, "terras": terras, "equid_pedida": p.get("equidistancia"),
            "cota": p.get("cota_plataforma")}
    ent["calc"] = calc
    return calc


def _camada(r: Raster, rgba: np.ndarray) -> Dict[str, Any]:
    img, bounds = SA.para_latlon(r, rgba)
    return {"png": "data:image/png;base64," + base64.b64encode(SA.png(img)).decode(), "bounds": bounds}


async def analisar(p: Dict[str, Any]) -> Dict[str, Any]:
    ent = await _mdt(p)
    c = await asyncio.to_thread(_calcular, ent, p)
    r, meta = ent["r"], dict(ent["meta"])
    meta["equidistancia"] = c["equid"]

    def camadas():
        return {
            "hipsometria": _camada(r, SA.rgba_hipsometria(r.z, c["hs"])),
            "declives": _camada(r, SA.rgba_declives(c["decl"])),
            "sombreado": _camada(r, np.dstack([c["hs"] * 255] * 3 + [np.where(np.isnan(r.z), 0, 200)]).astype(np.uint8)),
        }

    cams = await asyncio.to_thread(camadas)
    curvas_ll = [{"cota": cv["cota"], "mestra": cv["mestra"], "ll": AN.tm_para_ll_lista(cv["xy"])} for cv in c["curvas"]]
    linhas_ll = [{"bacia_m2": l["bacia_m2"], "ll": AN.tm_para_ll_lista(l["xy"])} for l in c["esc"]["linhas"]]
    recomend = []
    est = c["est"]
    if est["tem_desnivel"]:
        recomend.append("Terreno com desnível: juntar a carta de declives e a carta de recursos hídricos (linhas de água) ao processo.")
    if est.get("declive_max_pct") and est["declive_max_pct"] > 25:
        recomend.append("Há zonas com declive > 25 %: prever muros de suporte / estudo geotécnico e verificar a REN.")
    if linhas_ll:
        recomend.append("Existem talvegues potenciais no terreno: confirmar linhas de água e domínio hídrico (APA / carta da REN).")
    return {
        "ok": True, "meta": meta, "estatisticas": est, "classes_declive": c["classes"], "camadas": cams,
        "curvas": curvas_ll, "linhas_agua": linhas_ll, "limiar_bacia_m2": c["esc"]["limiar_m2"],
        "movimento_terras": c["terras"], "recomendacoes": recomend,
        "zona": [[round(a, 7), round(b, 7)] for a, b in ent["pts"]], "chave": _chave(p),
    }


async def perfil(p: Dict[str, Any], linha: Sequence[Tuple[float, float]]) -> Dict[str, Any]:
    if len(linha) < 2:
        raise GR.MdtErro("a linha do perfil precisa de dois pontos")
    q = dict(p)
    if not (q.get("poligono") or q.get("centro")):
        q["poligono"] = None
    pts = list(linha)
    r, meta = await GR.obter(pts, None, margem_m=10.0)
    pf = AN.perfil(r, pts)
    if not pf:
        raise GR.MdtErro("perfil sem cotas")
    zs = [x["z"] for x in pf]
    L = pf[-1]["d"]
    return {"ok": True, "pontos": pf, "comprimento_m": L, "z_min": min(zs), "z_max": max(zs),
            "declive_medio_pct": round(abs(zs[-1] - zs[0]) / L * 100, 1) if L else 0, "meta": meta}


async def malha3d(p: Dict[str, Any]) -> Dict[str, Any]:
    ent = await _mdt(p)
    c = await asyncio.to_thread(_calcular, ent, p)
    r = ent["r"]

    def f():
        m = AN.malha3d(r)
        tex = SA.rgba_hipsometria(r.z, c["hs"])
        m["textura"] = "data:image/png;base64," + base64.b64encode(SA.png(tex)).decode()
        if ent["pol"]:
            x, y = TM.para_tm(np.array([a for a, _ in ent["pol"]]), np.array([b for _, b in ent["pol"]]))
            m["terreno"] = [[round(float(a - r.x0), 2), round(float(r.y0 - b), 2)] for a, b in zip(x, y)]
        return m

    return await asyncio.to_thread(f)


async def exportar(p: Dict[str, Any], fmt: str, local: str = "", empresa: Optional[Dict[str, str]] = None) -> Tuple[bytes, str, str]:
    ent = await _mdt(p)
    c = await asyncio.to_thread(_calcular, ent, p)
    r, meta = ent["r"], dict(ent["meta"])
    meta["equidistancia"] = c["equid"]
    if fmt == "tif":
        from .geotiff import escrever
        return await asyncio.to_thread(escrever, r), "image/tiff", "MDT.tif"
    if fmt == "dxf":
        b = await asyncio.to_thread(SA.dxf, c["curvas"], c["esc"]["linhas"], ent["pol"], r)
        return b, "application/dxf", "Curvas_de_nivel.dxf"
    if fmt == "geojson":
        curvas_ll = [{"cota": cv["cota"], "mestra": cv["mestra"], "ll": AN.tm_para_ll_lista(cv["xy"])} for cv in c["curvas"]]
        linhas_ll = [{"bacia_m2": l["bacia_m2"], "ll": AN.tm_para_ll_lista(l["xy"])} for l in c["esc"]["linhas"]]
        gj = SA.geojson(curvas_ll, linhas_ll, ent["pol"], meta)
        return json.dumps(gj, ensure_ascii=False).encode(), "application/geo+json", "Terreno_MDT.geojson"
    if fmt == "pdf":
        emp = empresa or {}
        b = await asyncio.to_thread(SA.pdf_carta, r, meta, c["est"], c["classes"], c["hs"], c["decl"], c["curvas"], c["esc"],
                                    ent["pol"] or ent["pts"], local, c["terras"], emp.get("cor"), emp.get("nome") or "ConstruPilot",
                                    emp.get("logo_b64"))
        return b, "application/pdf", "Carta_declives_e_recursos_hidricos.pdf"
    raise GR.MdtErro("formato desconhecido")
