"""Testes de `engines.lisboa_permits` — parsing determinístico a partir de
duas linhas reais obtidas do FeatureServer da CML (sem rede).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from engines.lisboa_permits import (
    FREGUESIA_CENTROIDS,
    _normalize_freguesia,
    _polygon_centroid,
    official_permit,
    window_start,
)

# ---------------------------------------------------------------------------
# Dois exemplares reais do dataset (resposta GeoJSON do FeatureServer).
# Datas de alvará ajustadas para a janela corrente de 12 meses.
# ---------------------------------------------------------------------------
_HOJE = datetime.now(timezone.utc).date()
_RECENTE = (_HOJE - timedelta(days=30)).isoformat()
_MAIS_RECENTE = (_HOJE - timedelta(days=5)).isoformat()


def _feature_poligono(data_alvara: str, freguesia: str, op: str, n_proc: str) -> dict:
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[
                [-9.1690, 38.7210],
                [-9.1689, 38.7211],
                [-9.1688, 38.7210],
                [-9.1689, 38.7209],
                [-9.1690, 38.7210],
            ]],
        },
        "properties": {
            "OBJECTID": 30123,
            "COD_SIG": "3500501059001",
            "N_PROCESSO": n_proc,
            "DATA_ENTRADA": "2023-03-13",
            "MORADA": "Rua do Arco do Carvalhão, 181",
            "FREGUESIA": freguesia,
            "OP_URBANISTICA": op,
            "ASSUNTO": "Sem Informação",
            "PROCEDIMENTO": "EDI - Licença de obras de edificação",
            "TIPO_ALVARA": "Sem Informação",
            "N_ALVARA": "Sem Informação",
            "DATA_ALVARA": data_alvara,
            "TIPOLOGIA": "Edificação",
            "FONTE": "EURBAN",
        },
    }


def _feature_sem_geom(data_alvara: str, freguesia: str) -> dict:
    return {
        "type": "Feature",
        "geometry": None,
        "properties": {
            "OBJECTID": 29999,
            "N_PROCESSO": "e-EDI/2025/987",
            "FREGUESIA": freguesia,
            "DATA_ALVARA": data_alvara,
            "OP_URBANISTICA": "Construção Nova",
            "TIPOLOGIA": "Edificação",
            "MORADA": "Alameda das Missões",
        },
    }


class TestOfficialPermit:
    def test_feature_com_poligono_normaliza_para_lisboa(self):
        feat = _feature_poligono(_RECENTE, "Campo de Ourique", "Alteração", "e-EDI/2023/301")
        permit = official_permit(feat)
        assert permit is not None
        assert permit["source"]["kind"] == "cml_official"
        assert permit["source"]["verified"] is True
        assert permit["commune"] == "Lisboa"
        assert permit["dep"] == "lisboa"
        assert permit["freguesia"] == "Campo de Ourique"
        assert permit["nature"] == "renovation"
        assert permit["geometry_precision"] == "exact"
        assert permit["lat"] and permit["lon"]
        assert permit["date_auth"] == _RECENTE
        assert permit["promoteur"] is None  # nunca inventa requerente
        assert permit["id"].startswith("CML-")

    def test_feature_sem_geometria_usa_centroide_da_freguesia(self):
        feat = _feature_sem_geom(_MAIS_RECENTE, "Parque das Nações")
        permit = official_permit(feat)
        assert permit is not None
        lat_c, lon_c = FREGUESIA_CENTROIDS["Parque das Nações"]
        assert permit["lat"] == lat_c
        assert permit["lon"] == lon_c
        assert permit["geometry_precision"] == "freguesia_centroid"
        assert permit["nature"] == "neuf"

    def test_fora_janela_12_meses_e_descartado(self):
        old = (_HOJE - timedelta(days=400)).isoformat()
        feat = _feature_poligono(old, "Estrela", "Alteração", "e-EDI/2020/001")
        assert official_permit(feat) is None

    def test_sem_data_alvara_e_descartado(self):
        feat = _feature_poligono("", "Estrela", "Alteração", "e-EDI/2024/999")
        assert official_permit(feat) is None

    def test_sem_num_processo_e_descartado(self):
        feat = _feature_poligono(_RECENTE, "Estrela", "Alteração", "")
        assert official_permit(feat) is None


class TestFreguesiaNormalization:
    def test_match_case_insensitive(self):
        assert _normalize_freguesia("campo de ourique") == "Campo de Ourique"
        assert _normalize_freguesia("Alvalade") == "Alvalade"
        assert _normalize_freguesia("SÃO VICENTE") == "São Vicente"

    def test_desconhecido_devolve_none(self):
        assert _normalize_freguesia("Oeiras") is None
        assert _normalize_freguesia("") is None

    def test_cobertura_24_freguesias(self):
        assert len(FREGUESIA_CENTROIDS) == 24


class TestPolygonCentroid:
    def test_centroid_simples(self):
        coords = [[[-9.17, 38.72], [-9.16, 38.72], [-9.16, 38.73], [-9.17, 38.73], [-9.17, 38.72]]]
        lat, lon = _polygon_centroid(coords)
        assert round(lat, 4) == 38.7240
        assert round(lon, 4) == -9.1660

    def test_coords_vazias(self):
        assert _polygon_centroid([]) is None
        assert _polygon_centroid([[]]) is None


class TestWindow:
    def test_window_start_e_12_meses(self):
        hoje = date(2026, 10, 13)
        assert window_start(hoje) == "2025-10-13"
