"""Rotas /api/stair-engine/* — calculador de escadas PT."""
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.ai_providers.router import ai_router
from engines.stair_engine import StairInputs, calculate_stair
from engines.stair_engine.pdf_dossier import build_pdf

logger = logging.getLogger("stair_engine.routes")
router = APIRouter(prefix="/stair-engine", tags=["stair-engine"])


USO_OPTIONS = {"habitacao", "comercio", "evacuacao", "publico"}
MAT_OPTIONS = {"betao", "madeira", "metal"}


class CalcIn(BaseModel):
    altura_total_m: float = Field(..., gt=0.3, le=12)
    pe_direito_m: float = Field(..., gt=1.8, le=6)
    largura_m: float = Field(1.0, gt=0.5, le=4)
    num_degraus: Optional[int] = Field(None, gt=2, le=40)
    uso: str = "habitacao"
    material: str = "betao"
    acessibilidade: bool = False
    capacidade: Optional[int] = Field(None, gt=0, le=10000)
    project_name: Optional[str] = Field(None, max_length=120)
    enable_ia: bool = True


def _plan_id() -> str:
    return f"str_{uuid.uuid4().hex[:14]}"


def _ia_prompt(result: dict, project_name: str) -> str:
    inp = result["inputs"]
    dim = result["dimensoes"]
    return (
        f"Projeto: {project_name}\n"
        f"Uso: {inp['uso']} · Material: {inp['material']} · "
        f"Acessibilidade: {inp.get('acessibilidade')}\n"
        f"Altura total: {inp['altura_total_m']} m · Pé-direito: {inp['pe_direito_m']} m\n\n"
        f"Dimensões calculadas:\n"
        f"- {dim['num_degraus']} degraus (h = {dim['altura_degrau_cm']} cm, "
        f"g = {dim['profundidade_cobertor_cm']} cm)\n"
        f"- Blondel: {dim['blondel']} cm · Inclinação: {dim['inclinacao_graus']}°\n"
        f"- Conforto: {result['conforto_score']}/10\n\n"
        f"Alertas: {' | '.join(result['alertas']) if result['alertas'] else 'nenhum'}\n"
        f"Verificações: {result['resumo_verificacoes']}\n\n"
        f"Em PT-PT, 3 parágrafos curtos: (1) avaliação subjetiva do conforto e "
        f"ergonomia desta escada; (2) sugestões de melhoria se aplicável; "
        f"(3) notas de conformidade com DL 163/2006 (acessibilidade) e eventuais "
        f"ajustes recomendados. Linguagem técnica mas acessível."
    )


IA_SYSTEM = (
    "És engenheiro civil português especialista em projeto de escadas. "
    "Analisas dimensões calculadas e produzes recomendações em PT-PT com "
    "referências normativas (RGEU, REH, RSCIE, Eurocódigos, DL 163/2006). "
    "Sê objetivo e prático. Máximo 3 parágrafos curtos."
)


@router.post("/calculate")
async def calculate(body: CalcIn, user=Depends(current_user)):
    if body.uso not in USO_OPTIONS:
        raise HTTPException(400, f"'uso' inválido. Aceites: {sorted(USO_OPTIONS)}")
    if body.material not in MAT_OPTIONS:
        raise HTTPException(400, f"'material' inválido. Aceites: {sorted(MAT_OPTIONS)}")
    if body.uso == "evacuacao" and not body.capacidade:
        raise HTTPException(400, "Para 'evacuacao', `capacidade` (nº pessoas) é obrigatória.")

    inp = StairInputs(
        altura_total_m=body.altura_total_m,
        pe_direito_m=body.pe_direito_m,
        largura_m=body.largura_m,
        num_degraus=body.num_degraus,
        uso=body.uso, material=body.material,
        acessibilidade=body.acessibilidade,
        capacidade=body.capacidade,
    )
    try:
        result = calculate_stair(inp)
    except Exception as e:  # noqa: BLE001
        logger.exception("calculate falhou")
        raise HTTPException(500, f"Cálculo falhou: {type(e).__name__}") from None

    # IA opcional (opus 5.5)
    ia_text = None
    model_used = None
    if body.enable_ia and ai_router.claude:
        try:
            r = await ai_router.claude.ask(
                prompt=_ia_prompt(result, body.project_name or "Escada"),
                system=IA_SYSTEM, max_tokens=800, temperature=0.3,
            )
            ia_text = r.text
            model_used = r.model
        except Exception as e:  # noqa: BLE001
            logger.info("IA stair falhou: %s", type(e).__name__)

    plan_id = _plan_id()
    doc = {
        "plan_id": plan_id,
        "user_id": user["user_id"],
        "project_name": body.project_name or "Escada",
        "inputs": result["inputs"],
        "dimensoes": result["dimensoes"],
        "conforto_score": result["conforto_score"],
        "verificacoes": result["verificacoes"],
        "resumo_verificacoes": result["resumo_verificacoes"],
        "alertas": result["alertas"],
        "patamares": result["patamares"],
        "ia_text": ia_text,
        "model_used": model_used,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.stair_analyses.insert_one(doc)
    doc.pop("_id", None)
    return {**doc, "svgs": result["svgs"]}


@router.get("/history")
async def history(limit: int = 20, user=Depends(current_user)):
    limit = max(1, min(int(limit or 20), 100))
    items = await db.stair_analyses.find(
        {"user_id": user["user_id"]},
        {"_id": 0, "verificacoes": 0, "ia_text": 0},
    ).sort("created_at", -1).to_list(limit)
    return {"items": items}


@router.get("/{plan_id}")
async def get_one(plan_id: str, user=Depends(current_user)):
    doc = await db.stair_analyses.find_one(
        {"plan_id": plan_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Análise não encontrada.")
    # Re-gerar SVGs on-demand
    from engines.stair_engine.drawings import build_svgs
    dim = doc["dimensoes"]
    doc["svgs"] = build_svgs(dim["num_degraus"], dim["altura_degrau_cm"],
                              dim["profundidade_cobertor_cm"], dim["largura_cm"] / 100)
    return doc


class PdfIn(BaseModel):
    plan_id: str


@router.post("/generate-pdf")
async def generate_pdf(body: PdfIn, user=Depends(current_user)):
    doc = await db.stair_analyses.find_one(
        {"plan_id": body.plan_id, "user_id": user["user_id"]},
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Análise não encontrada.")
    # Fetch branding
    branding = await db.users.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0, "brand_company_name": 1, "brand_nif": 1},
    ) or {}
    data = {
        "inputs": doc["inputs"],
        "dimensoes": doc["dimensoes"],
        "conforto_score": doc["conforto_score"],
        "verificacoes": doc["verificacoes"],
        "resumo_verificacoes": doc["resumo_verificacoes"],
        "alertas": doc["alertas"],
        "patamares": doc["patamares"],
    }
    try:
        pdf_bytes = build_pdf(
            data, project_name=doc.get("project_name") or "Escada",
            ia_text=doc.get("ia_text"), branding=branding,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("PDF falhou")
        raise HTTPException(500, f"PDF falhou: {type(e).__name__}") from None

    stem = (doc.get("project_name") or "escada").replace(" ", "_")[:40]
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="dossier_escada_{stem}_{body.plan_id[-6:]}.pdf"',
            "Cache-Control": "private, no-store",
            "X-Stair-Score": str(doc.get("conforto_score")),
        },
    )


@router.get("/{analysis_id}/pdf")
async def pdf_por_analysis_id(analysis_id: str, user=Depends(current_user)):
    """Fase D — PDF do dossier pelo `analysis_id` (ou `plan_id` legacy)."""
    doc = await db.stair_analyses.find_one(
        {
            "user_id": user["user_id"],
            "$or": [{"analysis_id": analysis_id}, {"plan_id": analysis_id}],
        },
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Análise não encontrada.")
    branding = await db.users.find_one(
        {"user_id": user["user_id"]},
        {"_id": 0, "brand_company_name": 1, "brand_nif": 1},
    ) or {}
    # Suporta documentos criados pela tool `calcular_escada` (campo `result`)
    # e documentos criados pela rota legacy (campos achatados).
    if "result" in doc:
        r = doc["result"] or {}
        data = {
            "inputs": doc.get("inputs", {}),
            "dimensoes": r.get("dimensoes", {}),
            "conforto_score": r.get("conforto_score") or 0,
            "verificacoes": r.get("verificacoes") or [],
            "resumo_verificacoes": r.get("resumo_verificacoes") or {},
            "alertas": r.get("alertas") or [],
            "patamares": r.get("patamares") or [],
        }
    else:
        data = {
            "inputs": doc.get("inputs", {}),
            "dimensoes": doc.get("dimensoes", {}),
            "conforto_score": doc.get("conforto_score", 0),
            "verificacoes": doc.get("verificacoes", []),
            "resumo_verificacoes": doc.get("resumo_verificacoes", {}),
            "alertas": doc.get("alertas", []),
            "patamares": doc.get("patamares", []),
        }
    try:
        pdf_bytes = build_pdf(
            data, project_name=doc.get("project_name") or "Escada",
            ia_text=doc.get("ia_text"), branding=branding,
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("PDF falhou")
        raise HTTPException(500, f"PDF falhou: {type(e).__name__}") from None
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="escada_{analysis_id[-8:]}.pdf"',
            "Cache-Control": "private, no-store",
        },
    )
