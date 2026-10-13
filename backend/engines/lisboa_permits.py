"""Mapeamento de alvarás da Câmara Municipal de Lisboa (ArcGIS REST) para o modelo
`official_permit` consumido pelo Radar.

Fonte: `services.arcgis.com/1dSrzEWVQn5kHHyK/arcgis/rest/services/AlvarasObras/FeatureServer/0`
mirror oficial do dataset `dados.gov.pt` id `5ae9c60dc8d8c9146a44cc30`
("Alvarás para obras de edificação e demolição emitidos ao abrigo do RJUE").
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any

ARCGIS_FEATURE_URL = (
    "https://services.arcgis.com/1dSrzEWVQn5kHHyK/arcgis/rest/services/"
    "AlvarasObras/FeatureServer/0"
)
DATASET_PORTAL_URL = (
    "https://dados.gov.pt/pt/datasets/alvaras-para-obras-de-edificacao-e-"
    "demolicao-emitidos-ao-abrigo-do-rjue/"
)
SOURCE_NAME = "Câmara Municipal de Lisboa · Dados Abertos"

# Centróides aproximados das 24 freguesias de Lisboa (lat, lon · ETRS89/WGS84)
# Precisão ±200 m — usados em fallback quando o feature não traz geometria.
FREGUESIA_CENTROIDS: dict[str, tuple[float, float]] = {
    "Ajuda": (38.7066, -9.1973),
    "Alcântara": (38.7055, -9.1760),
    "Alvalade": (38.7558, -9.1437),
    "Areeiro": (38.7416, -9.1370),
    "Arroios": (38.7336, -9.1398),
    "Avenidas Novas": (38.7408, -9.1497),
    "Beato": (38.7349, -9.1134),
    "Belém": (38.6975, -9.2048),
    "Benfica": (38.7472, -9.2003),
    "Campo de Ourique": (38.7217, -9.1685),
    "Campolide": (38.7314, -9.1631),
    "Carnide": (38.7607, -9.1888),
    "Estrela": (38.7149, -9.1664),
    "Lumiar": (38.7707, -9.1601),
    "Marvila": (38.7461, -9.1050),
    "Misericórdia": (38.7118, -9.1465),
    "Olivais": (38.7679, -9.1137),
    "Parque das Nações": (38.7636, -9.0995),
    "Penha de França": (38.7312, -9.1264),
    "Santa Clara": (38.7756, -9.1253),
    "Santa Maria Maior": (38.7097, -9.1333),
    "Santo António": (38.7238, -9.1456),
    "São Domingos de Benfica": (38.7515, -9.1757),
    "São Vicente": (38.7227, -9.1286),
}

_FREG_NORMALIZE = {k.lower(): k for k in FREGUESIA_CENTROIDS}

# Mapeamento OP_URBANISTICA → nature (coerente com stackradar.filters)
_NATURE_MAP = {
    "construção nova": "neuf",
    "construcao nova": "neuf",
    "alteração": "renovation",
    "alteracao": "renovation",
    "ampliação": "extension",
    "ampliacao": "extension",
    "demolição": "demolicao",
    "demolicao": "demolicao",
    "reconstrução": "renovation",
    "reconstrucao": "renovation",
}


def _text(value: Any) -> str:
    return str(value).strip() if value not in (None, "") else ""


def _iso_date(value: Any) -> str | None:
    raw = _text(value)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw[:10]).isoformat()
    except ValueError:
        return None


def _window_start(today: date | None = None) -> str:
    today = today or datetime.now(timezone.utc).date()
    try:
        return today.replace(year=today.year - 1).isoformat()
    except ValueError:
        return today.replace(year=today.year - 1, day=28).isoformat()


def _normalize_freguesia(raw: str) -> str | None:
    """Case-insensitive match; devolve forma canónica ou ``None``."""
    if not raw:
        return None
    return _FREG_NORMALIZE.get(raw.lower())


def _polygon_centroid(coords: list) -> tuple[float, float] | None:
    """Média simples do primeiro anel (bom o suficiente para o Radar)."""
    if not coords:
        return None
    try:
        ring = coords[0]
        if not ring:
            return None
        lats = [pt[1] for pt in ring if len(pt) >= 2]
        lons = [pt[0] for pt in ring if len(pt) >= 2]
        if not lats or not lons:
            return None
        return sum(lats) / len(lats), sum(lons) / len(lons)
    except (IndexError, TypeError, ValueError):
        return None


def _nature(op: str) -> str:
    return _NATURE_MAP.get(op.lower(), "renovation")


def official_permit(feature: dict) -> dict | None:
    """Converte uma `feature` GeoJSON em registo compatível com o Radar.

    Devolve ``None`` se o alvará estiver fora da janela de 12 meses ou se os
    campos mínimos (número de processo + data de alvará) estiverem ausentes.
    """
    if not isinstance(feature, dict):
        return None
    attrs = feature.get("properties") or feature.get("attributes") or {}
    date_auth = _iso_date(attrs.get("DATA_ALVARA"))
    if not date_auth:
        return None
    if not (_window_start() <= date_auth <= datetime.now(timezone.utc).date().isoformat()):
        return None
    n_proc = _text(attrs.get("N_PROCESSO"))
    n_alvara = _text(attrs.get("N_ALVARA"))
    if not n_proc:
        return None
    freguesia = _normalize_freguesia(_text(attrs.get("FREGUESIA")))
    morada = _text(attrs.get("MORADA"))
    op = _text(attrs.get("OP_URBANISTICA"))
    procedimento = _text(attrs.get("PROCEDIMENTO"))
    tipologia = _text(attrs.get("TIPOLOGIA"))

    # Coordenadas: polígono do feature OU centróide da freguesia (fallback).
    lat = lon = None
    precision = "unknown"
    geom = feature.get("geometry") or {}
    if geom.get("type") == "Polygon":
        centroid = _polygon_centroid(geom.get("coordinates") or [])
        if centroid:
            lat, lon = centroid
            precision = "exact"
    if lat is None and freguesia and freguesia in FREGUESIA_CENTROIDS:
        lat, lon = FREGUESIA_CENTROIDS[freguesia]
        precision = "freguesia_centroid"

    nature = _nature(op)
    identifier = f"CML-{n_alvara}" if n_alvara and n_alvara.lower() != "sem informação" else f"CML-{n_proc.replace('/', '-')}"
    name = tipologia or "Edificação"
    if nature == "extension":
        name += " · ampliação"
    elif nature == "renovation":
        name += " · obras em edifício existente"
    elif nature == "demolicao":
        name += " · demolição"

    source = {
        "name": SOURCE_NAME,
        "kind": "cml_official",
        "verified": True,
        "dataset_id": "5ae9c60dc8d8c9146a44cc30",
        "feature_id": attrs.get("OBJECTID"),
        "n_processo": n_proc,
        "url": DATASET_PORTAL_URL,
    }

    classification = {
        "work_types": [nature] if nature in ("neuf", "renovation", "extension") else ["inconnu"],
        "building_types": ["autre"] if tipologia and tipologia.lower() != "edificação" else ["inconnu"],
        "client_type": "inconnu",
        "client_source": "unknown",
    }
    return {
        "id": identifier,
        "num": n_proc,
        "type": "Alvará de obras",
        "nature": nature,
        "commune": "Lisboa",
        "map_commune": freguesia or "Lisboa",
        "insee_commune": "1106",  # código DICOFRE do concelho de Lisboa
        "cp": "",
        "dep": "lisboa",
        "freguesia": freguesia,
        "address": morada,
        "adresse": morada,
        "lat": lat,
        "lon": lon,
        "geometry_precision": precision,
        "batiment": name,
        "surface_hab": 0,
        "surface_loc": 0,
        "surf_created": 0,
        "surface_basis": "Área não publicada no dataset de alvarás da CML",
        "logements": 0,
        "date_depot": _iso_date(attrs.get("DATA_ENTRADA")),
        "date_auth": date_auth,
        "statut": "Licenciado",
        "statut_code": 2,
        "mo": "DESCONHECIDO",
        "promoteur": None,  # NUNCA inventar requerentes
        "coordonnees_status": "absent",
        "source": source,
        "source_records": [source],
        "is_demo": False,
        "work_types": classification["work_types"],
        "building_types": classification["building_types"],
        "filter_evidence": {
            "OP_URBANISTICA": op,
            "PROCEDIMENTO": procedimento,
            "TIPOLOGIA": tipologia,
        },
        "filter_schema_version": 1,
        "classification": classification,
        "imported_at": datetime.now(timezone.utc).isoformat(),
    }


def window_start(today: date | None = None) -> str:
    """Exposto para alinhar com `sitadel_permits.window_start`."""
    return _window_start(today)
