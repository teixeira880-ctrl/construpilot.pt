"""Météo chantier — Open-Meteo (gratuit, sans clé) : géocodage + prévisions 16 jours."""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


async def get_forecast(city: str) -> dict:
    """Prévisions quotidiennes pour une ville (tmin/tmax/précipitations/code météo)."""
    try:
        async with httpx.AsyncClient(timeout=12) as cl:
            g = await cl.get("https://geocoding-api.open-meteo.com/v1/search",
                             params={"name": city, "count": 1, "language": "fr"})
            results = (g.json() or {}).get("results") or []
            if not results:
                return {"error": f'Localidade « {city} » não encontrada'}
            loc = results[0]
            f = await cl.get("https://api.open-meteo.com/v1/forecast", params={
                "latitude": loc["latitude"], "longitude": loc["longitude"],
                "daily": "weather_code,temperature_2m_min,temperature_2m_max,"
                         "precipitation_sum",
                "forecast_days": 16, "timezone": "auto"})
            d = (f.json() or {}).get("daily") or {}
            times = d.get("time") or []
            days = [{"date": times[i],
                     "code": (d.get("weather_code") or [None] * len(times))[i],
                     "tmin": (d.get("temperature_2m_min") or [None] * len(times))[i],
                     "tmax": (d.get("temperature_2m_max") or [None] * len(times))[i],
                     "precip": (d.get("precipitation_sum") or [0] * len(times))[i]}
                    for i in range(len(times))]
            label = loc["name"]
            if loc.get("admin1"):
                label += f" ({loc['admin1']})"
            return {"city": label, "days": days}
    except Exception as e:
        logger.warning(f"weather fetch failed for '{city}': {e}")
        return {"error": "Serviço de meteorologia indisponível — tente novamente mais tarde"}
