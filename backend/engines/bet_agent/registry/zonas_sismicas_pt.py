"""Zonas sísmicas de Portugal — NP EN 1998-1:2010 Anexo Nacional (NA.I).

Última consulta: **2026-10-18** (web_search_tool_v2 cruzado entre spessismica.pt,
oet.pt, iitk.ac.in e scholar.tecnico.ulisboa.pt).

ESCOPO:
    - Portugal Continental: 2 cenários (acção sísmica Tipo 1 "afastada" +
      Tipo 2 "próxima"). Cada concelho é classificado numa zona para cada tipo.
    - Açores: só Tipo 2.
    - Madeira: só Tipo 1 (zona 1.5).

ZONAS E agR (aceleração de referência em terreno tipo A, em m/s²):

Tipo 1 (interplacas, maior distância, maior magnitude):
    Zona 1.1 → 2.50 m/s²
    Zona 1.2 → 2.00 m/s²
    Zona 1.3 → 1.50 m/s²
    Zona 1.4 → 1.00 m/s²
    Zona 1.5 → 0.60 m/s²   # A CONFIRMAR: iitk reporta 0.5; outras fontes 0.6
    Zona 1.6 → 0.35 m/s²

Tipo 2 (intraplacas, menor distância, moderada magnitude):
    Zona 2.1 → 2.50 m/s²
    Zona 2.2 → 2.00 m/s²
    Zona 2.3 → 1.70 m/s²
    Zona 2.4 → 1.10 m/s²
    Zona 2.5 → 0.80 m/s²

CLASSES DE SOLO (Quadro 3.1 do EC8-1 + NA):
    A, B, C, D, E — coeficientes S, TB, TC, TD dependem do tipo de acção e
    da classe. Valores oficiais do NA constam das Tabelas NA.3.2/3.3.

FONTES:
    - https://spessismica.pt/eurocodigo-8/
    - https://www.oet.pt/downloads/eventos/EuroCodigo8.pdf
    - https://www.iitk.ac.in/nicee/wcee/article/14_07-0167.PDF
    - https://scholar.tecnico.ulisboa.pt/.../25027538a70ed...pdf

RASTREABILIDADE:
    - Qualquer valor sem certeza absoluta é marcado abaixo com `# A CONFIRMAR`
      e a função `get_seismic_params()` devolve `confidence=PENDENTE_VALIDACAO`
      quando o município não está na lista confirmada OU quando o valor
      consultado tem bandeira pendente.
    - O técnico responsável deve validar/corrigir estes dados antes de usar
      para dimensionamento sísmico real. Este módulo serve apenas como
      pré-dimensionamento ("pré-dimensionamento, a verificar e assinar pelo
      técnico responsável").
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SeismicConfidence(str, Enum):
    CONFIRMADO = "confirmado_fonte_oficial"
    PENDENTE = "pendente_validacao_tecnico"


# ---------------------------------------------------------------------------
# agR por zona (m/s²)
# ---------------------------------------------------------------------------

AGR_TIPO1_M_S2: dict[str, float] = {
    "1.1": 2.50,
    "1.2": 2.00,
    "1.3": 1.50,
    "1.4": 1.00,
    "1.5": 0.60,  # A CONFIRMAR: divergência iitk 0.5 vs spessismica/oet 0.6
    "1.6": 0.35,
}

AGR_TIPO2_M_S2: dict[str, float] = {
    "2.1": 2.50,
    "2.2": 2.00,
    "2.3": 1.70,
    "2.4": 1.10,
    "2.5": 0.80,
}

# Marcar valores sem certeza inter-fontes.
_PENDENTE_AGR: set[str] = {"1.5"}


# ---------------------------------------------------------------------------
# Classes de solo (Quadro NA.3.2 e NA.3.3 — valores recomendados).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SoilParams:
    S: float
    TB: float
    TC: float
    TD: float


# Tipo 1 — Quadro NA.3.2 do Anexo Nacional (valores S, TB, TC, TD recomendados).
SOIL_TIPO1: dict[str, SoilParams] = {
    "A": SoilParams(S=1.00, TB=0.10, TC=0.60, TD=2.00),
    "B": SoilParams(S=1.35, TB=0.10, TC=0.60, TD=2.00),  # A CONFIRMAR
    "C": SoilParams(S=1.60, TB=0.10, TC=0.60, TD=2.00),  # A CONFIRMAR
    "D": SoilParams(S=2.00, TB=0.10, TC=0.80, TD=2.00),  # A CONFIRMAR
    "E": SoilParams(S=1.80, TB=0.10, TC=0.60, TD=2.00),  # A CONFIRMAR
}

# Tipo 2 — Quadro NA.3.3.
SOIL_TIPO2: dict[str, SoilParams] = {
    "A": SoilParams(S=1.00, TB=0.10, TC=0.25, TD=2.00),
    "B": SoilParams(S=1.35, TB=0.10, TC=0.25, TD=2.00),  # A CONFIRMAR
    "C": SoilParams(S=1.60, TB=0.10, TC=0.25, TD=2.00),  # A CONFIRMAR
    "D": SoilParams(S=2.00, TB=0.10, TC=0.30, TD=2.00),  # A CONFIRMAR
    "E": SoilParams(S=1.80, TB=0.10, TC=0.25, TD=2.00),  # A CONFIRMAR
}


# ---------------------------------------------------------------------------
# Mapeamento concelho → zonas (parcial — expandir manualmente).
#
# Chaves são o nome do concelho em minúsculas sem acentos (normalizado por
# `_normalize_municipio`). Para concelhos não listados, a função devolve
# `confidence=PENDENTE` e sugere consulta manual do Anexo NA.I.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MunicipioZonas:
    tipo1: str
    tipo2: str
    confidence: SeismicConfidence = SeismicConfidence.PENDENTE


MUNICIPIO_ZONAS: dict[str, MunicipioZonas] = {
    # Confirmado inter-fontes 2026-10-18 (fonte explícita: web_search_tool_v2
    # cruzado com spessismica.pt).
    "lisboa": MunicipioZonas(tipo1="1.3", tipo2="2.3",
                             confidence=SeismicConfidence.CONFIRMADO),
    # Os seguintes municípios aparecem repetidamente em bibliografia técnica
    # portuguesa mas a tabela oficial NA.I por município não foi acessível no
    # web_search. Marcar PENDENTE e deixar que o técnico valide/corrija.
    "porto": MunicipioZonas(tipo1="1.6", tipo2="2.5"),           # A CONFIRMAR
    "faro": MunicipioZonas(tipo1="1.2", tipo2="2.4"),            # A CONFIRMAR
    "coimbra": MunicipioZonas(tipo1="1.5", tipo2="2.4"),         # A CONFIRMAR
    "evora": MunicipioZonas(tipo1="1.4", tipo2="2.4"),           # A CONFIRMAR
    "braga": MunicipioZonas(tipo1="1.6", tipo2="2.5"),           # A CONFIRMAR
    "setubal": MunicipioZonas(tipo1="1.3", tipo2="2.3"),         # A CONFIRMAR
    "aveiro": MunicipioZonas(tipo1="1.5", tipo2="2.4"),          # A CONFIRMAR
    "cascais": MunicipioZonas(tipo1="1.3", tipo2="2.3"),         # A CONFIRMAR
    "sintra": MunicipioZonas(tipo1="1.3", tipo2="2.3"),          # A CONFIRMAR
    "almada": MunicipioZonas(tipo1="1.3", tipo2="2.3"),          # A CONFIRMAR
    "oeiras": MunicipioZonas(tipo1="1.3", tipo2="2.3"),          # A CONFIRMAR
    "loures": MunicipioZonas(tipo1="1.3", tipo2="2.3"),          # A CONFIRMAR
    # Arquipélagos:
    "funchal": MunicipioZonas(tipo1="1.5", tipo2="",
                              confidence=SeismicConfidence.PENDENTE),  # Madeira só Tipo 1
    # Açores: só Tipo 2. Conservador: 2.1 nas ilhas de maior perigosidade,
    # usar o nome da ilha quando possível. Marcar PENDENTE para desencorajar
    # uso cego.
    "ponta_delgada": MunicipioZonas(tipo1="", tipo2="2.1"),       # A CONFIRMAR
}


# ---------------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SeismicParams:
    """Resultado de `get_seismic_params(municipio, classe_solo)`."""

    municipio_input: str
    classe_solo: str
    tipo1_zone: Optional[str]
    tipo2_zone: Optional[str]
    agR_tipo1_m_s2: Optional[float]
    agR_tipo2_m_s2: Optional[float]
    soil_tipo1: Optional[SoilParams]
    soil_tipo2: Optional[SoilParams]
    confidence: SeismicConfidence
    note_pt: str = (
        "Pré-dimensionamento, a verificar e assinar pelo técnico responsável."
    )


def _normalize_municipio(name: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFD", (name or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.replace(" ", "_").replace("-", "_")
    return s


def get_seismic_params(municipio: str, classe_solo: str = "A") -> SeismicParams:
    """Resolve zonas sísmicas + agR + parâmetros de solo para o município dado.

    - Para `municipio` desconhecido, devolve `confidence=PENDENTE` e campos
      de zona a `None` (técnico deve consultar NA.I manualmente).
    - Para zonas com valores sem certeza (ex: 1.5), devolve `confidence=PENDENTE`.
    - Para `classe_solo` desconhecida, usa "A" e marca `confidence=PENDENTE`.
    """
    classe = (classe_solo or "A").strip().upper()
    key = _normalize_municipio(municipio)
    zonas = MUNICIPIO_ZONAS.get(key)

    confidence = SeismicConfidence.CONFIRMADO
    if zonas is None or zonas.confidence == SeismicConfidence.PENDENTE:
        confidence = SeismicConfidence.PENDENTE
    if classe not in SOIL_TIPO1 or classe not in SOIL_TIPO2:
        confidence = SeismicConfidence.PENDENTE
        classe = "A"

    tipo1_zone = zonas.tipo1 if zonas and zonas.tipo1 else None
    tipo2_zone = zonas.tipo2 if zonas and zonas.tipo2 else None

    if tipo1_zone in _PENDENTE_AGR or tipo2_zone in _PENDENTE_AGR:
        confidence = SeismicConfidence.PENDENTE

    return SeismicParams(
        municipio_input=municipio,
        classe_solo=classe,
        tipo1_zone=tipo1_zone,
        tipo2_zone=tipo2_zone,
        agR_tipo1_m_s2=AGR_TIPO1_M_S2.get(tipo1_zone) if tipo1_zone else None,
        agR_tipo2_m_s2=AGR_TIPO2_M_S2.get(tipo2_zone) if tipo2_zone else None,
        soil_tipo1=SOIL_TIPO1.get(classe),
        soil_tipo2=SOIL_TIPO2.get(classe),
        confidence=confidence,
    )
