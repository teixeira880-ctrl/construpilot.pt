"""Construção tradicional — alvenaria assente unidade a unidade (engines/tradicional), a partir de um projeto em JSON
ou do modelo BIM de uma planta lida (o mesmo modelo que o editor do /bim altera)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from engines.access import require_level
from engines.tradicional import engine as T
from engines.tradicional import modelo as TM

router = APIRouter(prefix="/tradicional", tags=["tradicional"], dependencies=[Depends(require_level("pro"))])

from routes.auth import current_user  # noqa: E402


class ProjetoIn(BaseModel):
    projeto: dict = Field(description="Projeto de alvenaria: pisos, paredes (eixo, tipo, altura, vãos) e tipos de parede")


def _calc(projeto: dict) -> dict:
    try:
        return T.calcular(projeto)
    except (ValueError, KeyError, TypeError) as e:
        raise HTTPException(422, f"Projeto inválido: {e}") from e


@router.get("/exemplo")
async def exemplo() -> dict:
    """Projeto de exemplo (moradia de um piso em tijolo) e os catálogos de unidades e tipos de parede."""
    return {"projeto": T.exemplo(), "unidades": {k: {"nome": v[0], "comprimento_mm": v[1], "altura_mm": v[2], "espessura_mm": v[3]} for k, v in T.UNIDADES.items()},
            "tipos_parede": T.TIPOS_PAREDE}


@router.post("/calcular")
async def calcular(body: ProjetoIn, user=Depends(current_user)) -> dict:
    """Resumo do cálculo: unidades a comprar, cortes, argamassa, reboco, lintéis e avisos (sem a lista unidade a unidade)."""
    res = await run_in_threadpool(_calc, body.projeto)
    return {k: v for k, v in res.items() if k != "unidades"}


@router.post("/modelo")
async def modelo(body: ProjetoIn, user=Depends(current_user)) -> dict:
    """Modelo de estudo comum aos motores (3D, alçados, quantidades, lista de corte) para o visualizador partilhado."""
    res = await run_in_threadpool(_calc, body.projeto)
    return TM.modelo(res, projeto=body.projeto)


@router.get("/da-planta/{plan_id}/{page_index}")
async def da_planta(plan_id: str, page_index: int, bloco: bool = False, user=Depends(current_user)) -> dict:
    """Projeto de alvenaria a partir do modelo BIM da planta lida (com as edições feitas no /bim). As paredes resistentes
    ficam com o tipo exterior e as divisórias com o interior: é uma hipótese, a rever parede a parede."""
    from routes.bim import _load_model, _params

    _, model, _ = await _load_model(plan_id, page_index, user, _params(None, None, None, None, None, None))
    sufixo = "_BLOCO" if bloco else ""
    paredes = []
    for w in model.walls:
        vaos = [{"id": o.source_id, "offset_m": round(o.offset, 4), "largura_m": round(o.width, 4), "peitoril_m": round(o.sill, 4), "altura_m": round(o.height, 4)}
                for o in model.openings if o.wall_id == w.source_id]
        paredes.append({"id": w.source_id, "x1": round(w.x1, 4), "y1": round(w.y1, 4), "x2": round(w.x2, 4), "y2": round(w.y2, 4),
                        "tipo": ("EXT" if w.load_bearing else "INT") + sufixo, "altura_m": round(w.height, 4), "vaos": vaos})
    if not paredes:
        raise HTTPException(422, "O modelo desta planta não tem paredes.")
    return {"projeto": {"nome": f"Alvenaria · planta p.{page_index + 1}", "pisos": [{"nome": model.storey_name, "cota_m": 0.0, "paredes": paredes}]},
            "hipoteses": ["Paredes resistentes → tipo exterior; divisórias → tipo interior. Reveja o tipo de cada parede no projeto."]}
