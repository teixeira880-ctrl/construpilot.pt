"""Fonte única dos parâmetros nacionais portugueses (Anexos Nacionais).

Todos os valores aqui são **AN PT — a confirmar pelo projetista**. Esta tabela
cobre as necessidades correntes da nota de cálculo gerada pelo autopiloto BET:

- NP EN 1990 (bases de projeto): coeficientes de combinação ψ₀/ψ₁/ψ₂.
- NP EN 1991-1-1 (sobrecargas): categorias A..H para pavimentos e escadas.
- NP EN 1991-1-3 (neve): zonas Z1/Z2/Z3 e critério de altitude.
- NP EN 1991-1-4 (vento): zonas A/B e `vb,0`.
- NP EN 1992-1-1 (betão armado): γc/γs, αcc, materiais default, recobrimentos.
- NP EN 1998-1 (sismo): aviso explícito; parâmetros ainda não calculados.

As chaves string internas (ex.: ``"habitation"`` em contexto FR) mantêm-se para
compatibilidade com o resto do pipeline; o módulo `structuro_autopilot`
cuida da normalização de aliases PT (``"habitacao"`` → ``"habitation"``).
"""
from __future__ import annotations

from typing import Dict, Optional

# -------------------------------------------------------- NP EN 1991-1-1
# Sobrecargas de utilização em pavimentos (categorias EN 1991-1-1 Quadro 6.2).
# Valores em kN/m². AN PT — a confirmar pelo projetista.
IMPOSED_LOADS: Dict[str, Dict[str, object]] = {
    # habitação cat. A: zonas residenciais domésticas
    "habitation":  {"q": 2.0, "cat": "A"},   # AN PT — a confirmar pelo projetista
    # escritórios cat. B
    "bureau":      {"q": 3.0, "cat": "B"},   # AN PT — a confirmar pelo projetista
    # comércio cat. D1 (áreas de venda de proximidade)
    "commerce":    {"q": 4.0, "cat": "D1"},  # AN PT — a confirmar pelo projetista
    # estacionamento ligeiro cat. F
    "parking":     {"q": 2.5, "cat": "F"},   # AN PT — a confirmar pelo projetista
    # industrial cat. E
    "industriel":  {"q": 7.5, "cat": "E"},   # AN PT — a confirmar pelo projetista
    # espaços públicos de aglomeração cat. C3; usar 5.0 (C5) se "erp" grande
    "erp":         {"q": 4.0, "cat": "C3"},  # AN PT — a confirmar pelo projetista
    # cobertura não acessível, exceto para manutenção
    "cobertura_nao_acessivel": {"q": 0.4, "cat": "H"},  # AN PT — a confirmar pelo projetista
}

# Escadas em habitação (categoria A, Quadro 6.2 NA).
IMPOSED_STAIRS_HABITATION_KN_M2 = 3.0  # AN PT — a confirmar pelo projetista

# Carga uniforme equivalente para paredes divisórias móveis leves (6.3.1.2(8)).
PARTITIONS_UDL_KN_M2 = 1.0  # AN PT — a confirmar pelo projetista


# -------------------------------------------------------- NP EN 1990 (ψ)
# Coeficientes de combinação para sobrecargas (Quadro A1.1 do AN PT).
# Formato: cat → (ψ0, ψ1, ψ2). AN PT — a confirmar pelo projetista.
PSI_FACTORS: Dict[str, Dict[str, float]] = {
    "A":  {"psi0": 0.7, "psi1": 0.5, "psi2": 0.3},   # habitação
    "B":  {"psi0": 0.7, "psi1": 0.5, "psi2": 0.3},   # escritórios
    "C":  {"psi0": 0.7, "psi1": 0.7, "psi2": 0.6},   # públicos (média)
    "C3": {"psi0": 0.7, "psi1": 0.7, "psi2": 0.6},
    "D":  {"psi0": 0.7, "psi1": 0.7, "psi2": 0.6},   # comércio
    "D1": {"psi0": 0.7, "psi1": 0.7, "psi2": 0.6},
    "E":  {"psi0": 1.0, "psi1": 0.9, "psi2": 0.8},   # armazenamento/industrial
    "F":  {"psi0": 0.7, "psi1": 0.7, "psi2": 0.6},   # estacionamento ligeiro
    "H":  {"psi0": 0.0, "psi1": 0.0, "psi2": 0.0},   # cobertura
    # Ações climáticas:
    "neve": {"psi0": 0.5, "psi1": 0.2, "psi2": 0.0},  # H ≤ 1000 m
    "vento": {"psi0": 0.6, "psi1": 0.2, "psi2": 0.0},
}


# -------------------------------------------------------- NP EN 1991-1-3 (neve)
# Zonas em Portugal continental: Z1, Z2, Z3 (altitude). Para altitudes abaixo
# dos 200 m assume-se, por defeito, ação da neve desprezável.
SNOW_ZONES: Dict[str, Dict[str, object]] = {
    "Z1": {"Cz0": 0.00, "alpha": 2.2e-3},  # AN PT — a confirmar pelo projetista
    "Z2": {"Cz0": 0.20, "alpha": 2.2e-3},  # AN PT — a confirmar pelo projetista
    "Z3": {"Cz0": 0.45, "alpha": 2.2e-3},  # AN PT — a confirmar pelo projetista
}
SNOW_ALTITUDE_IGNORE_M = 200.0  # AN PT — a confirmar pelo projetista


# -------------------------------------------------------- NP EN 1991-1-4 (vento)
# Valores básicos de referência da velocidade do vento em m/s.
WIND_ZONES: Dict[str, Dict[str, float]] = {
    "A": {"vb0_m_s": 27.0},  # AN PT — a confirmar pelo projetista
    "B": {"vb0_m_s": 30.0},  # AN PT — a confirmar pelo projetista
}


# -------------------------------------------------------- NP EN 1992-1-1
# Materiais e coeficientes de segurança parciais.
GAMMA_C = 1.5    # AN PT — a confirmar pelo projetista
GAMMA_S = 1.15   # AN PT — a confirmar pelo projetista
ALPHA_CC = 0.85  # AN PT — a confirmar pelo projetista

DEFAULT_CONCRETE_CLASS = "C25/30"  # AN PT — a confirmar pelo projetista
DEFAULT_STEEL_GRADE = "A500 NR"    # AN PT — a confirmar pelo projetista

# Recobrimentos mínimos (mm) por classe de exposição — E 464 LNEC.
COVERS_MM: Dict[str, int] = {
    "XC1": 25,  # AN PT — a confirmar pelo projetista
    "XC2": 35,  # AN PT — a confirmar pelo projetista
    "XC3": 35,  # AN PT — a confirmar pelo projetista
    "XC4": 40,  # AN PT — a confirmar pelo projetista
    "fundacao": 50,  # face em contacto com terreno (NP EN 1997-1 + E 464)
}


# -------------------------------------------------------- NP EN 1998-1 (sismo)
SEISMIC_WARNING_TEXT = (
    "Ação sísmica NP EN 1998-1 não verificada — obrigatória em Portugal; "
    "dimensionamento sísmico a efetuar pelo projetista"
)

# Campos opcionais guardados em `inputs` para a Fase 3.
SEISMIC_INPUT_SCHEMA: Dict[str, Optional[str]] = {
    "zona_sismica_tipo1": None,  # "1.1"..."1.6" (ação sísmica afastada) — AN PT
    "zona_sismica_tipo2": None,  # "2.1"..."2.5" (ação sísmica próxima) — AN PT
    "classe_solo": None,         # "A".."E" — AN PT (NP EN 1998-1 Quadro 3.1)
}


# -------------------------------------------------------- UI / PDFs
# Rótulos PT-PT para as destinações (usar nos PDFs e UI).
DEST_LABEL_PT: Dict[str, str] = {
    "habitation": "Habitação",
    "bureau": "Escritórios",
    "commerce": "Comércio",
    "parking": "Estacionamento",
    "industriel": "Industrial",
    "erp": "Espaço público",
    "cobertura_nao_acessivel": "Cobertura não acessível",
}


# -------------------------------------------------------- aliases PT → chave interna
# Mapeamento bidirecional entre nomes em PT e as chaves internas FR que o
# pipeline usa há muito tempo. O autopiloto deve aceitar ambos no input.
DEST_ALIASES: Dict[str, str] = {
    "habitacao": "habitation",
    "habitação": "habitation",
    "escritorios": "bureau",
    "escritórios": "bureau",
    "comercio": "commerce",
    "comércio": "commerce",
    "estacionamento": "parking",
    "industrial": "industriel",
    "publico": "erp",
    "público": "erp",
    "espaco_publico": "erp",
    "espaço_publico": "erp",
}


def canonical_destination(name: str | None) -> str:
    """Devolve a chave canónica da destinação (nome interno PT ou alias FR→PT)."""
    if not name:
        return "habitation"
    key = str(name).strip().lower()
    if key in IMPOSED_LOADS:
        return key
    return DEST_ALIASES.get(key, key)
