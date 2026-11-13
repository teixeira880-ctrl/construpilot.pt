"""Limite de um prédio a partir das RGG do BUPi (eBUPi, dados abertos, CC BY 4.0).

O WMS público só dá a imagem e alguns atributos; o desenho das RGG publicado pela eBUPi está no GeoPackage do
dados.gov.pt («Representação Gráfica Georreferenciada», ~2,26 milhões de polígonos em PT-TM06, atualização quinzenal,
sem atributos além da área — os restantes foram retirados por RGPD). Por isso o limite vem, por esta ordem:

1. GeoPackage local (BUPI_RGG_GPKG ou backend/data/bupi/rgg.gpkg), descarregado com scripts/bupi_rgg_descarregar.py:
   índice espacial R-tree do próprio GeoPackage, leitura direta em SQLite, sem dependências novas;
2. geometria devolvida pelo WMS (GetFeatureInfo), se o serviço a incluir.

Qualidade conhecida dos dados (análise pública do QGIS-PT): há polígonos duplicados e sobreposições entre RGG. Quando
o ponto cai em mais de uma RGG diferente, o resultado diz isso e não escolhe às cegas: devolve a mais pequena e avisa.
"""
from __future__ import annotations

import asyncio
import os
import sqlite3
import struct
from typing import Any, Dict, List, Optional, Tuple

from engines.urbanismo_pt.auto import geo as G

from . import bupi as B
from . import geometria as GM

FONTE_GPKG = "eBUPi — Representação Gráfica Georreferenciada (dados.gov.pt, GeoPackage, CC BY 4.0)"


def caminho_gpkg() -> Optional[str]:
    p = os.environ.get("BUPI_RGG_GPKG") or os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "data", "bupi", "rgg.gpkg"))
    return p if os.path.isfile(p) else None


def _wkb_de_gpkg(blob: bytes) -> Optional[bytes]:
    """Retira o cabeçalho GeoPackage (GP + versão + flags + envelope) e devolve o WKB."""
    if not blob or len(blob) < 8 or blob[:2] != b"GP":
        return None
    flags = blob[3]
    env = {0: 0, 1: 32, 2: 48, 3: 48, 4: 64}.get((flags >> 1) & 0x07)
    if env is None:
        return None
    return bytes(blob[8 + env:])


def _tabela(con: sqlite3.Connection) -> Optional[Tuple[str, str]]:
    r = con.execute("SELECT table_name, column_name FROM gpkg_geometry_columns LIMIT 1").fetchone()
    return (r[0], r[1]) if r else None


def candidatos_gpkg(caminho: str, x: float, y: float, raio_m: float = 0.0) -> List[Dict[str, Any]]:
    """RGG do GeoPackage que contêm (ou ficam a raio_m de) um ponto PT-TM06. Síncrono: correr em thread."""
    from shapely import wkb
    from shapely.geometry import Point
    con = sqlite3.connect(f"file:{caminho}?mode=ro", uri=True)
    try:
        t = _tabela(con)
        if not t:
            return []
        tab, col = t
        if not all(c.isalnum() or c in "_-" for c in tab + col):
            return []
        rt = f"rtree_{tab}_{col}"
        pk = con.execute(f'PRAGMA table_info("{tab}")').fetchall()
        fid = next((c[1] for c in pk if c[5] == 1), "fid")
        rows = con.execute(
            f'SELECT t."{fid}", t."{col}" FROM "{tab}" t JOIN "{rt}" r ON r.id = t."{fid}" '
            "WHERE r.minx <= ? AND r.maxx >= ? AND r.miny <= ? AND r.maxy >= ? LIMIT 200",
            (x + raio_m, x - raio_m, y + raio_m, y - raio_m)).fetchall()
    finally:
        con.close()
    p = Point(x, y)
    out, vistos = [], set()
    for f, blob in rows:
        w = _wkb_de_gpkg(blob)
        if not w:
            continue
        try:
            g = wkb.loads(w)
        except Exception:  # noqa: BLE001
            continue
        if g.is_empty or (raio_m <= 0 and not g.contains(p)) or (raio_m > 0 and g.distance(p) > raio_m):
            continue
        chave = (round(g.area, 1), round(g.centroid.x, 1), round(g.centroid.y, 1))
        if chave in vistos:            # duplicados conhecidos do conjunto de dados
            continue
        vistos.add(chave)
        out.append({"fid": f, "geom": g, "area_m2": round(g.area, 1)})
    out.sort(key=lambda e: e["area_m2"])
    return out


def _anel_latlon(g) -> List[List[float]]:
    if g.geom_type == "MultiPolygon":
        g = max(g.geoms, key=lambda q: q.area)
    return [[round(a, 8), round(b, 8)] for a, b in (GM.tm06_inv(x, y) for x, y in list(g.exterior.coords)[:-1])]


async def limite_no_ponto(lat: float, lon: float) -> Dict[str, Any]:
    """Limite (anel lat/lon) da RGG do BUPi que contém o ponto. ok=False se não houver fonte com geometria."""
    gp = caminho_gpkg()
    if gp:
        x, y = GM.tm06(lat, lon)
        try:
            cand = await asyncio.to_thread(candidatos_gpkg, gp, x, y)
        except Exception as e:  # noqa: BLE001
            cand, erro = [], type(e).__name__
        else:
            erro = None
        if cand:
            m = cand[0]
            nota = None
            if len(cand) > 1:
                nota = (f"O ponto cai em {len(cand)} RGG diferentes (sobreposição no BUPi): usada a mais pequena "
                        f"({m['area_m2']:.0f} m²). Confirme qual é o seu prédio.")
            return G._res(True, {"anel_latlon": _anel_latlon(m["geom"]), "area_m2": m["area_m2"], "fid": m["fid"],
                                 "sobreposicoes": len(cand) - 1, "origem": "gpkg"},
                          FONTE_GPKG, "https://dados.gov.pt/pt/datasets/representacao-grafica-georreferenciada/", nota)
        if erro:
            return G._res(False, nota=f"GeoPackage das RGG ilegível ({erro})")
    # recurso: geometria no GetFeatureInfo do WMS, se o serviço a devolver
    r = await B.rgg_no_ponto(lat, lon)
    if r.get("ok"):
        for f in (r.get("data") or {}).get("rgg", []):
            anel = GM.anel_de_geojson(f.get("geometry"))
            if anel and len(anel) >= 3:
                try:
                    m = GM.medir(anel)
                except GM.GeometriaInvalida:
                    continue
                return G._res(True, {"anel_latlon": m["anel_latlon"], "area_m2": m["area_m2"], "id": f["id"],
                                     "sobreposicoes": 0, "origem": "wms"}, B.FONTE, r.get("url"))
        return G._res(False, nota="sem RGG com geometria neste ponto" if gp else
                      "sem RGG neste ponto, ou o desenho das RGG ainda não está instalado no servidor")
    return G._res(False, nota=r.get("nota") or "BUPi indisponível")
