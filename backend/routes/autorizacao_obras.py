"""Rota pública do módulo «Autorização de obras» para particulares.

Diagnóstico guiado — não altera a base de dados, não consome créditos.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engines.autorizacao_obras_pt.rules import (
    LEI_RJUE,
    SCENARIOS,
    diagnosticar,
)

router = APIRouter(prefix="/particulares/autorizacao", tags=["autorizacao-obras"])


class DiagnosticoIn(BaseModel):
    tipo_obra: str = Field(..., description="anexo|muro|interiores|piscina|ampliacao|moradia_nova|outro")
    subtipo_muro: Optional[str] = Field(None, description="vedacao|suporte quando tipo_obra=muro")
    area_implantacao_m2: Optional[float] = 0.0
    area_construcao_total_m2: Optional[float] = 0.0
    area_construcao_criada_m2: Optional[float] = 0.0
    altura_m: Optional[float] = 0.0
    indice_implantacao: Optional[float] = None
    afastamento_min_m: Optional[float] = None
    concelho: Optional[str] = None
    freguesia: Optional[str] = None
    confina_via_publica: bool = False
    zona_protegida: bool = False
    imovel_classificado: bool = False
    tem_edificacao_principal: bool = True
    altera_fachada: bool = False
    altera_uso: bool = False
    altera_cobertura: bool = False
    tem_pdm_com_parametros: bool = False
    tem_loteamento_pip: bool = False
    zona_urbana_consolidada: bool = False
    pdm_altura_max_m: Optional[float] = None
    pdm_indice_implantacao: Optional[float] = None
    pdm_afastamento_min_m: Optional[float] = None


@router.get("/meta")
async def meta() -> dict:
    """Metadados para a UI: lista de cenários cobertos e referência à lei base."""
    return {"ok": True, "lei_base": LEI_RJUE, "scenarios": SCENARIOS}


@router.post("/diagnostico")
async def diagnostico(body: DiagnosticoIn) -> dict:
    resultado = diagnosticar(body.model_dump())
    return {"ok": True, **resultado}
