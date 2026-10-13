"""Dispatcher da fonte oficial de licenças do Radar.

Expoem `ensure_sync`, `sync_status`, `INITIAL_DEPARTMENTS`, `source_kind`,
`window_start` conforme a flag `RADAR_SOURCES`:

* `cml` (default em Portugal): Câmara Municipal de Lisboa (RJUE).
* `sitadel`: France (legacy, mantém compatibilidade com código antigo).
"""
from __future__ import annotations

import os
from typing import Any

RADAR_SOURCE = os.environ.get("RADAR_SOURCES", "cml").strip().lower()


if RADAR_SOURCE == "sitadel":
    from engines.sitadel_permits import window_start  # noqa: F401
    from engines.sitadel_sync import (  # noqa: F401
        INITIAL_DEPARTMENTS,
        ensure_sync,
        sync_status,
    )
    SOURCE_KIND = "sitadel_official"

    async def refresh_classifications(permits: list[dict]) -> None:
        from engines.radar_filters import classification
        from engines.sitadel_text import repair_cached_address
        for permit in permits:
            repair_cached_address(permit)
            permit["classification"] = classification(permit)

else:
    from engines.lisboa_permits import window_start  # noqa: F401
    from engines.lisboa_sync import (  # noqa: F401
        INITIAL_ZONES as INITIAL_DEPARTMENTS,
        ensure_sync,
        sync_status,
    )
    SOURCE_KIND = "cml_official"

    async def refresh_classifications(permits: list[dict]) -> None:
        # A classificação CML é determinada no `official_permit` e já persiste
        # na coleção; nada a reconstruir.
        for permit in permits:
            permit.setdefault("classification", {
                "work_types": permit.get("work_types") or ["inconnu"],
                "building_types": permit.get("building_types") or ["inconnu"],
                "client_type": "inconnu",
                "client_source": "unknown",
            })


def normalize_zones(values: Any) -> list[str]:
    """Normalização permissiva: aceita qualquer código válido para a fonte activa."""
    if RADAR_SOURCE == "sitadel":
        from engines.radar_zones import normalize_departments
        return normalize_departments(values)
    # CML: apenas "lisboa" por enquanto.
    codes = [str(v).strip().lower() for v in values if str(v).strip()]
    return [c for c in codes if c in ("lisboa",)] or ["lisboa"]
