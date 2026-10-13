"""Guard de ativação do correio postal (Merci Facteur).

Quando `POSTAL_ENABLED` for `false` (default em Portugal, onde não existe
integração homologada), todas as rotas postais devolvem **410 Gone** com uma
mensagem em PT-PT e nenhum pedido HTTP externo é efetuado.
"""
from __future__ import annotations

from fastapi import HTTPException

from routes.public_config import postal_enabled

POSTAL_DISABLED_MESSAGE = "Funcionalidade indisponível em Portugal"


def ensure_postal_enabled() -> None:
    """Guard FastAPI — lança 410 se o correio postal estiver desligado."""
    if not postal_enabled():
        raise HTTPException(status_code=410, detail=POSTAL_DISABLED_MESSAGE)
