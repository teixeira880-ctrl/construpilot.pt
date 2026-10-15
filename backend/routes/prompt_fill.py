"""Rota /api/prompt-fill/{app_key} — barra de prompt IA transversal (PT-PT).

Mantém o funcionamento manual das calculadoras: só preenche campos a partir
de um prompt livre em português europeu. O endpoint devolve um envelope JSON
que o frontend aplica ao estado local (nunca força submissão).

NOTA: `from __future__ import annotations` foi REMOVIDO porque interfere com
a inspecção de signature feita por slowapi + FastAPI/Pydantic v2 — levava
o FastAPI a resolver o body como query param (HTTP 422).
"""
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from core.rate_limit import limiter
from core.security import current_user

# importa primeiro a base e depois força o registo de cada extractor
from engines.prompt_fill.base import REGISTRY, run_extractor
from engines.prompt_fill import stairs as _stairs_registered  # noqa: F401
from engines.prompt_fill import medicoes as _medicoes_registered  # noqa: F401
from engines.prompt_fill import orcamentos as _orcamentos_registered  # noqa: F401
from engines.prompt_fill import plantas as _plantas_registered  # noqa: F401
from engines.prompt_fill import autorizacao as _autorizacao_registered  # noqa: F401
from engines.prompt_fill import moradia as _moradia_registered  # noqa: F401
from engines.prompt_fill import calculadoras as _calculadoras_registered  # noqa: F401

router = APIRouter(prefix="/prompt-fill", tags=["prompt-fill"])


class PromptIn(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=2000)
    contexto: Optional[dict] = None


@router.get("/apps")
async def listar_apps(user=Depends(current_user)):
    return {
        "apps": [
            {"key": k, "required": ext.required_fields()}
            for k, ext in REGISTRY.items()
        ]
    }


@router.post("/{app_key}")
@limiter.limit("20/hour")
async def preencher(
    request: Request,                    # obrigatório como PRIMEIRO parâmetro p/ slowapi
    response: Response,                  # obrigatório p/ slowapi injectar headers rate-limit
    app_key: str,
    body: PromptIn = Body(...),          # força body JSON (evita regressão para query)
    user=Depends(current_user),
):
    ext = REGISTRY.get(app_key)
    if ext is None:
        raise HTTPException(404, f"App '{app_key}' sem extrator registado.")
    return await run_extractor(ext, body.prompt, body.contexto)
