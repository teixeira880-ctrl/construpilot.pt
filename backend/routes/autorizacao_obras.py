"""Rota pública do módulo «Autorização de obras» para particulares.

Diagnóstico guiado — não altera a base de dados, não consome créditos.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engines.autorizacao_obras_pt.rules import (
    LEI_RJUE,
    SCENARIOS,
    diagnosticar,
)
from engines.autorizacao_obras_pt.dossier import (
    gerar_dossier,
    gerar_memoria_descritiva,
    estimativa_e_calendario,
    checklist_pecas,
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


class RequerenteIn(BaseModel):
    nome: Optional[str] = ""
    nif: Optional[str] = ""
    morada: Optional[str] = ""
    telefone: Optional[str] = ""
    email: Optional[str] = ""


class PecaIn(BaseModel):
    nome: str
    bytes_b64: Optional[str] = None  # conteúdo opcional (base64) de peça já carregada


class MemoriaPreviewIn(BaseModel):
    respostas: Dict[str, Any] = Field(default_factory=dict)
    diagnostico: Dict[str, Any] = Field(default_factory=dict)


class DossierIn(BaseModel):
    respostas: Dict[str, Any] = Field(default_factory=dict)
    diagnostico: Dict[str, Any] = Field(default_factory=dict)
    requerente: Optional[RequerenteIn] = None
    pecas: List[PecaIn] = Field(default_factory=list)
    memoria_override: Optional[str] = None


@router.post("/memoria/preview")
async def memoria_preview(body: MemoriaPreviewIn) -> dict:
    """Pré-gera a memória descritiva para o utilizador rever antes do PDF final."""
    texto = await gerar_memoria_descritiva(body.respostas or {}, body.diagnostico or {})
    return {"ok": True, "memoria_texto": texto}


@router.post("/checklist")
async def checklist(body: MemoriaPreviewIn) -> dict:
    cl = checklist_pecas(body.diagnostico or {}, [])
    return {"ok": True, **cl}


@router.post("/dossier/gerar")
async def dossier_gerar(body: DossierIn) -> dict:
    """Gera o dossier (PDF único + ZIP). Devolve conteúdo em base64 na resposta.

    Nota: a venda do processo está desativada por flag — este endpoint apenas gera.
    A ativação da monetização é feita no Lote N4.
    """
    pecas = []
    for p in body.pecas:
        if p.bytes_b64:
            try:
                pecas.append({"nome": p.nome, "bytes": base64.b64decode(p.bytes_b64)})
            except Exception:  # noqa: BLE001
                pecas.append({"nome": p.nome, "bytes": b""})
        else:
            pecas.append({"nome": p.nome, "bytes": b""})
    requerente = body.requerente.model_dump() if body.requerente else None
    out = await gerar_dossier(body.respostas or {}, body.diagnostico or {},
                              pecas_carregadas=pecas, requerente=requerente,
                              memoria_override=body.memoria_override)
    return {
        "ok": True,
        "version": out["version"],
        "pdf_unico_b64": base64.b64encode(out["pdf_unico"]).decode("ascii"),
        "zip_b64": base64.b64encode(out["zip"]).decode("ascii"),
        "memoria_texto": out["memoria_texto"],
        "checklist": out["checklist"],
        "estimativa": out["estimativa"],
        "ficheiros": out["ficheiros"],
    }
