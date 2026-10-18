"""Reader — placeholder L1.0/L1.3.

Em L1.3, este módulo irá implementar o loop ReAct com Claude Opus 5.5 e
tool-use (`report_floor`, `report_wall`, `request_zoom_crop`, `ask_user`, ...).

Em L1.0, o pipeline permanece inacessível porque a feature flag
`BET_AGENT_ENABLED` está `false` por omissão (ver `engines.bet_agent.is_enabled`).

TODO L1.3:
    - Receber PDFs (arquitectura + geotécnico).
    - Extracção texto vectorial via pymupdf.
    - Render de página em alta resolução.
    - Chamada Claude via `anthropic_native` com tool-use definido em
      `engines.bet_agent.agent.tools`.
    - Loop até BuildingModel populado + anomalies em zonas abertas.
    - Metering obrigatório (DossierMeter em cost.py).
    - Nunca gerar valores estruturais, só rastrear o que leu.
"""
from __future__ import annotations

from engines.bet_agent.cost import DossierMeter
from engines.bet_agent.models.brief import UserBrief
from engines.bet_agent.models.building import BuildingModel


class ReaderNotImplementedError(NotImplementedError):
    """Explicit guard — chamar reader em L1.0 é erro de programação."""


async def read_building(
    project_id: str,
    pdf_paths: list[str],
    brief: UserBrief,
    meter: DossierMeter,
) -> BuildingModel:
    """Reader principal — IMPLEMENTAÇÃO em L1.3."""
    raise ReaderNotImplementedError(
        "reader.read_building ainda não implementado — ver L1.3 do plano."
    )
