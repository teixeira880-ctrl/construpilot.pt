"""Dados climáticos medidos/reanalisados do local (opcionais: se um serviço não responder, a avaliação continua).

* PVGIS 5.3 (Comissão Europeia, JRC) — irradiação média mensal real no plano horizontal, com o horizonte do local;
* Copernicus ERA5 (ECMWF), servido pelo Open-Meteo — dois anos horários de vento → rosa dos ventos anual, de verão
  nas horas quentes (≥ 24 °C, ventilação natural) e de inverno (proteção);
* zona climática regulamentar do REH (Despacho n.º 15793-F/2013): NUTS III do concelho + correção pela altitude,
  com o motor já existente engines.calc_lots.reh.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import httpx

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/MRcalc"
ERA5_URL = "https://archive-api.open-meteo.com/v1/archive"
RUMOS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]


async def pvgis(lat: float, lon: float) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=20.0) as c:
        r = await c.get(PVGIS_URL, params={"lat": f"{lat:.5f}", "lon": f"{lon:.5f}", "horirrad": 1, "outputformat": "json",
                                           "usehorizon": 1, "startyear": 2016, "endyear": 2023})
    if r.status_code != 200:
        return {"ok": False, "nota": f"PVGIS HTTP {r.status_code}"}
    por_mes: Dict[int, List[float]] = {}
    for x in r.json()["outputs"]["monthly"]:
        por_mes.setdefault(int(x["month"]), []).append(float(x["H(h)_m"]))
    mens = [round(sum(v) / len(v), 1) for _, v in sorted(por_mes.items())]
    if len(mens) != 12:
        return {"ok": False, "nota": "PVGIS: resposta incompleta"}
    return {"ok": True, "mensal_kwh_m2": mens, "anual_kwh_m2": round(sum(mens), 0), "periodo": "2016–2023",
            "fonte": "PVGIS 5.3 — Comissão Europeia (JRC), com horizonte", "url": PVGIS_URL}


def rosa(tempos: Sequence[str], temp: Sequence[Optional[float]], vel: Sequence[Optional[float]],
         dirs: Sequence[Optional[float]]) -> Dict[str, Any]:
    def setores(sel):
        cont = [0] * 8
        soma = [0.0] * 8
        for i in sel:
            if dirs[i] is None or vel[i] is None or vel[i] < 0.5:
                continue
            k = int(((dirs[i] % 360) + 22.5) // 45) % 8
            cont[k] += 1
            soma[k] += vel[i]
        tot = sum(cont) or 1
        return [{"rumo": RUMOS[k], "freq_pct": round(100 * cont[k] / tot, 1),
                 "vel_media_ms": round(soma[k] / cont[k], 1) if cont[k] else 0.0} for k in range(8)]
    mes = [int(t[5:7]) for t in tempos]
    todos = range(len(tempos))
    ver = [i for i in todos if mes[i] in (6, 7, 8, 9) and temp[i] is not None and temp[i] >= 24]
    inv = [i for i in todos if mes[i] in (12, 1, 2)]
    a, v, w = setores(todos), setores(ver), setores(inv)

    def dom(s):
        return max(s, key=lambda x: x["freq_pct"])["rumo"]
    return {"anual": a, "verao_quente": v, "inverno": w, "dominante_anual": dom(a),
            "dominante_verao": dom(v) if ver else None, "dominante_inverno": dom(w), "horas_verao_quente": len(ver)}


async def ventos(lat: float, lon: float) -> Dict[str, Any]:
    fim = datetime.now(timezone.utc).year - 1
    async with httpx.AsyncClient(timeout=30.0) as c:
        r = await c.get(ERA5_URL, params={"latitude": f"{lat:.4f}", "longitude": f"{lon:.4f}",
                                          "start_date": f"{fim - 1}-01-01", "end_date": f"{fim}-12-31",
                                          "hourly": "temperature_2m,wind_speed_10m,wind_direction_10m",
                                          "models": "era5", "timezone": "UTC", "wind_speed_unit": "ms"})
    if r.status_code != 200:
        return {"ok": False, "nota": f"ERA5 HTTP {r.status_code}"}
    h = r.json()["hourly"]
    return {"ok": True, **rosa(h["time"], h["temperature_2m"], h["wind_speed_10m"], h["wind_direction_10m"]),
            "fonte": "Copernicus ERA5 (ECMWF), via Open-Meteo", "periodo": f"{fim - 1}–{fim}", "url": ERA5_URL}


def clima_reh(concelho: Optional[str], altitude: Optional[float]) -> Dict[str, Any]:
    if not concelho:
        return {"ok": False, "nota": "concelho não identificado (CAOP sem resposta)"}
    from engines.calc_lots import reh
    try:
        c = reh.clima(concelho=concelho, altitude_m=altitude)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "nota": str(e)[:160]}
    return {"ok": True, "nuts3": c["nuts"], "zona_inverno": c["zona_i"], "zona_verao": c["zona_v"],
            "graus_dia": round(c["GD"]), "theta_ext_verao": round(c["theta_v"], 1), "meses_aquecimento": round(c["M"], 1),
            "altitude_m": round(c["altitude_m"], 1), "aviso": c.get("aviso"),
            "fonte": "Despacho n.º 15793-F/2013 (REH) — NUTS III com correção de altitude"}
