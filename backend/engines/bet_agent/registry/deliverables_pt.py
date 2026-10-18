"""Registo central dos entregáveis obrigatórios do BET-PT.

Fonte das decisões: `decisões firmes do fundador` (L1), itens 4 (entregáveis).
Qualquer alteração passa primeiro por aprovação do fundador.
"""
from __future__ import annotations

from enum import Enum


class DeliverableKind(str, Enum):
    """Enum centralizado dos entregáveis que o pipeline sabe produzir ou marcar como `não produzido`."""

    MEMORIA_DESCRITIVA = "memoria_descritiva"
    """Memória descritiva + justificativa + cálculos."""

    PLANTA_FUNDACOES = "planta_fundacoes"
    """Planta de fundações."""

    PLANTAS_ESTRUTURA_PISO = "plantas_estrutura_piso"
    """Plantas de estrutura por piso (pilares, vigas, lajes) com armaduras referenciadas."""

    QUADRO_PILARES = "quadro_pilares"
    """Quadro de pilares."""

    MAPA_ARMADURAS = "mapa_armaduras"
    """Mapa de armaduras = mapa de quantidades (tolerância ±5%)."""

    CORTES_PORMENORES = "cortes_pormenores"
    """Cortes construtivos e pormenores: sapata, viga fundação, parede cave, ligação laje-viga."""

    COBERTURA = "cobertura"
    """Cobertura."""

    REDE_AGUAS = "rede_aguas"
    """Rede de águas (separada nos desenhos e no mapa)."""

    REDE_ESGOTOS_DOMESTICOS = "rede_esgotos_domesticos"
    """Esgotos domésticos (separados)."""

    REDE_AGUAS_PLUVIAIS = "rede_aguas_pluviais"
    """Águas pluviais (separadas)."""

    ITED_SIMPLIFICADO = "ited_simplificado"
    """ITED simplificado."""

    VERIFICACAO_SISMICA_NP_EN_1998_1 = "verificacao_sismica_np_en_1998_1"
    """Verificação sísmica NP EN 1998-1 NA PT — obrigatória."""

    ORCAMENTO_LIGADO_MAPA = "orcamento_ligado_mapa"
    """Orçamento ligado ao mapa de quantidades."""

    MINUTA_TERMO_RESPONSABILIDADE = "minuta_termo_responsabilidade"
    """Minuta de termo de responsabilidade (NÃO assinada)."""


# Entregáveis críticos — se qualquer um estiver "pedido mas não produzido",
# o global_status não pode ser verde.
CRITICAL_DELIVERABLES: frozenset[DeliverableKind] = frozenset({
    DeliverableKind.PLANTA_FUNDACOES,
    DeliverableKind.PLANTAS_ESTRUTURA_PISO,
    DeliverableKind.VERIFICACAO_SISMICA_NP_EN_1998_1,
})


# Entregáveis **fora de âmbito** do BET-PT Agent — sempre marcados como
# "não produzido" com motivo "fora de âmbito do módulo estrutural".
OUT_OF_SCOPE: frozenset[str] = frozenset({
    "termica_reh",
    "acustica",
    "gas",
    "scie",
})


# Conjunto completo que o pipeline deve pelo menos considerar.
ALL_DELIVERABLES: frozenset[DeliverableKind] = frozenset(DeliverableKind)
