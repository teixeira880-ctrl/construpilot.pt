"""MDT Portugal — modelo digital do terreno de Portugal continental (DGT LiDAR 50 cm / 2 m).

GET  /mdt/estado                 fontes ativas (LiDAR DGT configurado ou só altimetria de recurso)
GET  /mdt/morada?q=…             geocodificação de uma morada (mesmo motor do licenciamento)
POST /mdt/analise                terreno (polígono) ou ponto + raio → cotas, declives, curvas, escorrência, volumes, camadas
POST /mdt/perfil                 perfil longitudinal ao longo de uma linha
POST /mdt/3d                     malha de alturas + textura para o visualizador 3D
POST /mdt/exportar/{fmt}         tif (MDT GeoTIFF PT-TM06) · dxf (curvas de nível 3D) · geojson · pdf (cartas)
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.security import current_user
from engines.mdt_pt import cdd, servico as SV
from engines.mdt_pt.grelha import MdtErro
from engines.nom_fichier import content_disposition

log = logging.getLogger(__name__)
router = APIRouter(prefix="/mdt", tags=["mdt"])


class ZonaIn(BaseModel):
    poligono: Optional[List[List[float]]] = Field(default=None, max_length=300)
    centro: Optional[List[float]] = Field(default=None, min_length=2, max_length=2)
    raio_m: Optional[float] = Field(default=None, gt=5, le=1500)
    resolucao: Optional[float] = Field(default=None, ge=0.5, le=50)
    equidistancia: Optional[float] = Field(default=None, ge=0.1, le=100)
    cota_plataforma: Optional[float] = Field(default=None, ge=-100, le=3000)
    local: Optional[str] = Field(default=None, max_length=300)


class PerfilIn(BaseModel):
    linha: List[List[float]] = Field(min_length=2, max_length=100)


def _p(b: ZonaIn) -> dict:
    d = b.model_dump()
    if d.get("poligono"):
        d["poligono"] = [[round(float(a), 7), round(float(c), 7)] for a, c in d["poligono"]]
    return d


def _erro(e: Exception):
    if isinstance(e, (MdtErro, cdd.CddErro, ValueError)):
        raise HTTPException(422, str(e))
    log.exception("MDT: erro inesperado")
    raise HTTPException(500, "Falha no cálculo do MDT. Tente novamente.")


@router.get("/estado")
async def estado(user=Depends(current_user)):
    return {
        "lidar_dgt": cdd.configurado(),
        "fonte_principal": cdd.FONTE if cdd.configurado() else None,
        "fonte_recurso": "Google Elevation / EU-DEM 25 m (Copernicus) — indicativa",
        "cobertura": "Portugal continental",
        "resolucoes": ["0,5 m (zonas até ~600 m)", "2 m (até 3 km)"],
        "licenca": "Dados LiDAR DGT: CC-BY-4.0",
    }


_RELEVO: dict = {}
HIPSOMETRIA_WMS = "https://geo2.dgterritorio.gov.pt/wms/hipsometria"


@router.get("/relevo-nacional")
async def relevo_nacional(user=Depends(current_user)):
    """Camada WMS oficial da DGT para ver o relevo de Portugal continental inteiro (hipsometria, MDT 50 m).
    O nome da camada é lido do GetCapabilities do serviço (guardado em memória 24 h)."""
    import re
    import time
    import httpx
    if _RELEVO.get("ts", 0) > time.time() - 86400:
        return _RELEVO["v"]
    v = {"ok": False}
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
            r = await c.get(HIPSOMETRIA_WMS, params={"service": "WMS", "request": "GetCapabilities", "version": "1.3.0"})
        nomes = re.findall(r"<Layer[^>]*queryable=[^>]*>\s*<Name>([^<]+)</Name>", r.text) or re.findall(r"<Name>([^<]+)</Name>", r.text)[1:]
        if r.status_code == 200 and nomes:
            v = {"ok": True, "url": HIPSOMETRIA_WMS, "camada": nomes[0], "versao": "1.3.0",
                 "fonte": "DGT — Hipsometria de Portugal Continental (MDT 50 m)"}
    except Exception as e:  # noqa: BLE001
        log.info("WMS hipsometria DGT: %s", e)
    _RELEVO.update({"ts": time.time() if v["ok"] else time.time() - 86400 + 600, "v": v})
    return v


@router.get("/morada")
async def morada(q: str, user=Depends(current_user)):
    from engines.urbanismo_pt.auto import geo
    if not q or len(q) > 300:
        raise HTTPException(422, "morada inválida")
    r = await geo.geocode(q)
    if not r.get("ok"):
        raise HTTPException(404, "Morada não encontrada")
    d = r["data"]
    return {"lat": d["lat"], "lon": d["lon"], "nome": d.get("morada_formatada") or q, "precisao": d.get("precisao"), "fonte": r.get("fonte")}


@router.post("/analise")
async def analise(body: ZonaIn, user=Depends(current_user)):
    try:
        return await SV.analisar(_p(body))
    except Exception as e:  # noqa: BLE001
        _erro(e)


@router.post("/perfil")
async def perfil(body: PerfilIn, user=Depends(current_user)):
    try:
        return await SV.perfil({}, [(float(a), float(b)) for a, b in body.linha])
    except Exception as e:  # noqa: BLE001
        _erro(e)


@router.post("/3d")
async def modelo3d(body: ZonaIn, user=Depends(current_user)):
    try:
        return await SV.malha3d(_p(body))
    except Exception as e:  # noqa: BLE001
        _erro(e)


@router.post("/exportar/{fmt}")
async def exportar(fmt: str, body: ZonaIn, user=Depends(current_user)):
    if fmt not in ("tif", "dxf", "geojson", "pdf"):
        raise HTTPException(404, "formato desconhecido")
    emp = None
    if fmt == "pdf":
        try:
            from routes.plans_common import _resolve_branding
            b = await _resolve_branding(user["user_id"]) or {}
            emp = {"nome": b.get("company_name") or "ConstruPilot", "logo_b64": b.get("logo_b64"),
                   "cor": b.get("accent_color")}
        except Exception:  # noqa: BLE001
            emp = None
    try:
        dados, mime, nome = await SV.exportar(_p(body), fmt, body.local or "", emp)
    except Exception as e:  # noqa: BLE001
        _erro(e)
    return Response(content=dados, media_type=mime, headers={"Content-Disposition": content_disposition(nome)})
