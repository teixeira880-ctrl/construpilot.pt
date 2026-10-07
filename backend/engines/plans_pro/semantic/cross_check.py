"""Verificação cruzada entre fontes (Autodesk APS ↔ Vision LLM).

Objectivo: detectar divergências silenciosas (ex.: APS reporta 15 janelas,
LLM reporta 3). Antes da Fase 1, a pipeline produzia dois canais isolados
sem reconciliação — este módulo materializa o cruzamento.

Regras (determinísticas, zero LLM):
    1. Contagem de aberturas (janelas + portas):
        * diferença >20%  →  severidade='erro'
        * diferença >10%  →  severidade='aviso'
    2. Materiais declarados:
        * LLM detecta material ausente de APS  →  severidade='aviso'
    3. Área total:
        * diferença >15% entre APS bbox e áreas LLM  →  severidade='erro'

Side-effects do cross-check:
    * `confidence_global` é reduzida proporcionalmente ao número e
      severidade dos warnings (-0.05 por 'aviso', -0.15 por 'erro').
    * `requires_human_review=True` se ≥1 warning 'erro'.
"""
from __future__ import annotations

import logging
from typing import Any

from engines.plans_pro.semantic.schemas import (
    AnalisePlanta,
    CrossCheckWarning,
)

logger = logging.getLogger("plans_pro.cross_check")


# Palavras-chave para categorizar na metadata APS
_APS_JANELAS = ("windows", "janela", "janelas", "fenetre")
_APS_PORTAS = ("doors", "porta", "portas", "porte")


def _contar_aps_aberturas(aps_metadata: dict[str, Any]) -> tuple[int, int]:
    """Devolve `(janelas, portas)` lidas da estrutura `quantities` do APS."""
    janelas = 0
    portas = 0
    quantities = (aps_metadata or {}).get("quantities") or {}
    for cat, data in quantities.items():
        if not isinstance(data, dict):
            continue
        count = int(data.get("count") or 0)
        chave = cat.lower()
        if any(k in chave for k in _APS_JANELAS):
            janelas = max(janelas, count)
        elif any(k in chave for k in _APS_PORTAS):
            portas = max(portas, count)
    return janelas, portas


def _contar_vision_aberturas(vision: AnalisePlanta) -> tuple[int, int]:
    """Devolve `(janelas, portas)` lidas dos `elementos` da `AnalisePlanta`."""
    janelas = 0
    portas = 0
    for el in vision.elementos:
        if el.tipo != "abertura":
            continue
        sub = (el.sub_tipo or "").lower()
        if sub == "janela":
            janelas += 1
        elif sub == "porta":
            portas += 1
    return janelas, portas


def _diferenca_relativa(a: int, b: int) -> float:
    """Diferença relativa |a-b|/max(a,b). Retorna 0.0 se ambos forem 0."""
    pior = max(a, b)
    if pior == 0:
        return 0.0
    return abs(a - b) / pior


def _materiais_llm(vision: AnalisePlanta) -> set[str]:
    """Conjunto de nomes de materiais únicos detectados pelo LLM."""
    out: set[str] = set()
    for el in vision.elementos:
        if el.material is None:
            continue
        out.add(el.material.nome.upper())
    return out


def _materiais_aps(aps_metadata: dict[str, Any]) -> set[str]:
    """Conjunto de materiais lidos da metadata APS (campo opcional)."""
    materiais_declarados = (aps_metadata or {}).get("materiais") or []
    if not isinstance(materiais_declarados, list):
        return set()
    return {str(m).upper() for m in materiais_declarados if m}


def _area_aps(aps_metadata: dict[str, Any]) -> float | None:
    """Área total da bbox APS em m². `None` se indisponível."""
    bbox = (aps_metadata or {}).get("bbox") or {}
    try:
        a = float(bbox.get("area_m2"))
    except (TypeError, ValueError):
        return None
    return a if a > 0 else None


def _area_vision(vision: AnalisePlanta) -> float | None:
    """Soma das áreas (comprimento × largura em m) dos elementos. `None` se nada."""
    total = 0.0
    tem = False
    for el in vision.elementos:
        comp = None
        larg = None
        for d in el.dimensoes:
            # Converter para metros
            fator = {"mm": 0.001, "cm": 0.01, "m": 1.0}[d.unidade]
            val_m = d.valor * fator
            if d.eixo == "comprimento":
                comp = val_m
            elif d.eixo == "largura":
                larg = val_m
        if comp and larg and comp > 0 and larg > 0:
            total += comp * larg
            tem = True
    return total if tem else None


def cross_check(
    aps_metadata: dict[str, Any],
    vision_result: AnalisePlanta,
) -> list[CrossCheckWarning]:
    """Compara APS metadata com `AnalisePlanta` e devolve lista de warnings.

    NÃO altera `vision_result` in-place — devolve só os warnings. O caller
    (`plan_vision.full_analysis`) é responsável por fundir no resultado.
    """
    warnings: list[CrossCheckWarning] = []

    # Regra 1 — contagem de aberturas
    aps_j, aps_p = _contar_aps_aberturas(aps_metadata)
    vis_j, vis_p = _contar_vision_aberturas(vision_result)
    for campo, va, vb in (
        ("contagem.janelas", aps_j, vis_j),
        ("contagem.portas", aps_p, vis_p),
    ):
        if va == 0 and vb == 0:
            continue
        diff = _diferenca_relativa(va, vb)
        if diff > 0.20:
            sev = "erro"
        elif diff > 0.10:
            sev = "aviso"
        else:
            continue
        warnings.append(
            CrossCheckWarning(
                fonte_a="aps_metadata",
                fonte_b="vision_llm",
                campo=campo,
                valor_a=va,
                valor_b=vb,
                severidade=sev,  # type: ignore[arg-type]
            )
        )

    # Regra 2 — materiais declarados APS vs LLM
    aps_mat = _materiais_aps(aps_metadata)
    llm_mat = _materiais_llm(vision_result)
    if aps_mat:
        extras_llm = llm_mat - aps_mat
        for m in sorted(extras_llm):
            warnings.append(
                CrossCheckWarning(
                    fonte_a="aps_metadata",
                    fonte_b="vision_llm",
                    campo="materiais.ausente_em_aps",
                    valor_a=None,
                    valor_b=m,
                    severidade="aviso",
                )
            )

    # Regra 3 — área total
    a_aps = _area_aps(aps_metadata)
    a_vis = _area_vision(vision_result)
    if a_aps is not None and a_vis is not None:
        diff = abs(a_aps - a_vis) / max(a_aps, a_vis)
        if diff > 0.15:
            warnings.append(
                CrossCheckWarning(
                    fonte_a="aps_metadata",
                    fonte_b="vision_llm",
                    campo="area.total_m2",
                    valor_a=round(a_aps, 2),
                    valor_b=round(a_vis, 2),
                    severidade="erro",
                )
            )

    logger.info(
        "cross_check: %d warnings (erros=%d avisos=%d info=%d)",
        len(warnings),
        sum(1 for w in warnings if w.severidade == "erro"),
        sum(1 for w in warnings if w.severidade == "aviso"),
        sum(1 for w in warnings if w.severidade == "info"),
    )
    return warnings


def aplicar_warnings(
    analise: AnalisePlanta,
    warnings: list[CrossCheckWarning],
) -> AnalisePlanta:
    """Funde `warnings` em `analise`, ajustando `confidence_global`
    e `requires_human_review`. Devolve um novo `AnalisePlanta`
    (não muta o input)."""
    delta = 0.0
    tem_erro = False
    for w in warnings:
        if w.severidade == "aviso":
            delta -= 0.05
        elif w.severidade == "erro":
            delta -= 0.15
            tem_erro = True
    nova_conf = max(0.0, min(1.0, analise.confidence_global + delta))
    requires = analise.requires_human_review or tem_erro or any(
        md.criticidade == "bloqueante" for md in analise.missing_data
    )
    return analise.model_copy(
        update={
            "warnings": [*analise.warnings, *warnings],
            "confidence_global": nova_conf,
            "requires_human_review": requires,
        }
    )


__all__ = ["cross_check", "aplicar_warnings"]
