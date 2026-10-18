"""Parse e validação do briefing do utilizador.

Regra dura: hipóteses do utilizador têm **sempre** prioridade sobre defaults.
Esta função só valida a estrutura e devolve o `UserBrief` normalizado.
A resolução de zona sísmica a partir de município/código postal é delegada ao
`registry/zonas_sismicas_pt.py` (criado em sub-passo L1.2b).
"""
from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from engines.bet_agent.models.brief import (
    DEFAULT_HYPOTHESES,
    UserBrief,
)
from engines.bet_agent.models.summary import HypothesisUsed


class BriefError(ValueError):
    """Erro de parsing/validação do brief do utilizador."""


def parse_user_brief(raw_input: dict[str, Any] | None) -> UserBrief:
    """Valida JSON do utilizador e devolve `UserBrief` imutável para o pipeline.

    - Qualquer campo omitido fica a `None` no `UserBrief`.
    - Defaults só são aplicados mais tarde ao recolher `hypotheses_used()`
      (NÃO sobrescrevem o `UserBrief` para preservar transparência).
    - Levanta `BriefError` em caso de JSON inválido.
    """
    if raw_input is None:
        raw_input = {}
    if not isinstance(raw_input, dict):
        raise BriefError("raw_input deve ser um dict JSON.")
    try:
        return UserBrief.model_validate(raw_input)
    except ValidationError as exc:
        raise BriefError(f"brief inválido: {exc.errors()}") from exc


def hypotheses_used(brief: UserBrief) -> list[HypothesisUsed]:
    """Devolve as hipóteses efectivamente usadas (user_imposed vs default_used).

    Esta função é chamada pelo `summary.build_summary` para produzir a secção
    `hypotheses_used` do `Summary`. Permite ao fundador ver, sem ambiguidade,
    onde o utilizador fixou algo e onde o pipeline recorreu a defaults.
    """
    used: list[HypothesisUsed] = []
    mapping = {
        "slab_type": brief.materials.slab_type,
        "masonry_type": brief.materials.masonry_type,
        "concrete_class": brief.materials.concrete_class,
        "steel_class": brief.materials.steel_class,
        "roof_type": brief.materials.roof_type,
    }
    for key, user_value in mapping.items():
        if user_value is not None:
            used.append(HypothesisUsed(
                key=key,
                value=str(user_value.value if hasattr(user_value, "value") else user_value),
                user_imposed=True,
                default_used=False,
                source_note="imposto pelo utilizador no brief",
            ))
        else:
            default_v = DEFAULT_HYPOTHESES.get(key)
            used.append(HypothesisUsed(
                key=key,
                value=str(default_v.value if hasattr(default_v, "value") else default_v),
                user_imposed=False,
                default_used=True,
                source_note="default do bet_agent (ver DEFAULT_HYPOTHESES)",
            ))
    # Zona sísmica — se utilizador deu explicitamente, user_imposed=True.
    if brief.seismic.zone:
        used.append(HypothesisUsed(
            key="seismic.zone",
            value=brief.seismic.zone,
            user_imposed=True,
            default_used=False,
            source_note="imposto pelo utilizador no brief (zona sísmica)",
        ))
    if brief.seismic.soil_class:
        used.append(HypothesisUsed(
            key="seismic.soil_class",
            value=brief.seismic.soil_class,
            user_imposed=True,
            default_used=False,
            source_note="imposto pelo utilizador no brief (classe de solo)",
        ))
    return used
