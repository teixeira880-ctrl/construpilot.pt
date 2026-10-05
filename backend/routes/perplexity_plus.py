"""Rotas /api/perplexity-plus/* — 4 endpoints avançados com presets PT.

Endpoints:
  POST /api/perplexity-plus/chat              — SSE streaming
  POST /api/perplexity-plus/compare           — tabela comparativa estruturada
  POST /api/perplexity-plus/norms             — normas PT (DRE/LNEC/APA)
  POST /api/perplexity-plus/materials-watch   — preços + tendência
  GET  /api/perplexity-plus/presets           — lista presets
  GET  /api/perplexity-plus/cache-stats       — stats cache (admin ou utilizador)
"""
from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.db import db
from core.security import current_user
from engines.perplexity_plus import (
    PRESETS,
    get_preset,
    pplx_plus_client,
    preset_system,
)
from engines.perplexity_plus.pplx_cache import ensure_index

logger = logging.getLogger("pplx_plus.routes")
router = APIRouter(prefix="/perplexity-plus", tags=["perplexity-plus"])


@router.on_event("startup")
async def _startup():
    await ensure_index()


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------
@router.get("/presets")
async def list_presets(user=Depends(current_user)) -> dict:
    return {
        "presets": [
            {"code": code, **{k: v for k, v in cfg.items() if k != "system"}}
            for code, cfg in PRESETS.items()
        ],
        "configured": pplx_plus_client.is_configured(),
    }


# ---------------------------------------------------------------------------
# 1. Chat SSE
# ---------------------------------------------------------------------------
class ChatIn(BaseModel):
    message: str = Field(..., min_length=2, max_length=4000)
    conversation_id: str | None = None
    preset: str | None = None
    history: list[dict[str, Any]] | None = None


@router.post("/chat")
async def chat_sse(body: ChatIn, request: Request, user=Depends(current_user)):
    if not pplx_plus_client.is_configured():
        raise HTTPException(503, "Perplexity não configurado neste servidor.")
    system = preset_system(body.preset)

    async def gen():
        try:
            async for chunk in pplx_plus_client.stream_chat(
                message=body.message, system=system, history=body.history,
            ):
                yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e)[:200]})}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ---------------------------------------------------------------------------
# 2. Compare
# ---------------------------------------------------------------------------
class CompareIn(BaseModel):
    items: list[str] = Field(..., min_length=2, max_length=10)
    criteria: list[str] = Field(..., min_length=1, max_length=10)
    context: str | None = None
    preset: str | None = None


COMPARE_SYSTEM = (
    "És perito em comparação técnica para construção em Portugal. "
    "Produz tabela comparativa estruturada em JSON. Devolve APENAS JSON válido:\n"
    "{\n"
    '  "items": [string],\n'
    '  "criteria": [string],\n'
    '  "scores": [[number]],   // matriz items x criteria, 1-5\n'
    '  "pros_cons": [{"item": string, "pros": [string], "cons": [string]}],\n'
    '  "recomendado": {"item": string, "razao": string},\n'
    '  "observacoes": string\n'
    "}\n"
    "Referencia normas PT (RGEU, Eurocódigos, LNEC) quando relevante."
)


@router.post("/compare")
async def compare(body: CompareIn, user=Depends(current_user)):
    if not pplx_plus_client.is_configured():
        raise HTTPException(503, "Perplexity não configurado.")
    sys = preset_system(body.preset, COMPARE_SYSTEM) + "\n\n" + COMPARE_SYSTEM
    prompt = (
        f"Contexto: {body.context or 'N/A'}\n"
        f"Compara estes items:\n- " + "\n- ".join(body.items) +
        f"\n\nSegundo os critérios:\n- " + "\n- ".join(body.criteria) +
        "\n\nDevolve APENAS JSON com items, criteria, scores (matriz 1-5), "
        "pros_cons, recomendado, observacoes."
    )
    try:
        r = await pplx_plus_client.ask_structured(prompt=prompt, system=sys, max_tokens=2000)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Perplexity falhou: {type(e).__name__}") from None
    return r


# ---------------------------------------------------------------------------
# 3. Norms
# ---------------------------------------------------------------------------
class NormsIn(BaseModel):
    query: str = Field(..., min_length=3, max_length=600)
    preset: str = "LNEC"
    context: str | None = None


NORMS_SYSTEM = (
    "És perito em normalização portuguesa de construção. Devolve APENAS JSON:\n"
    "{\n"
    '  "normas": [{"referencia": string, "titulo": string, "artigo": string|null, "resumo": string, "url": string|null, "fonte": string}],\n'
    '  "aplicacao": string,\n'
    '  "pontos_atencao": [string],\n'
    '  "resposta_textual": string\n'
    "}\n"
    "Prefere Diário da República (dre.pt) ou LNEC (lnec.pt). Cita o DL/Lei/NP exatos. PT-PT."
)


@router.post("/norms")
async def norms(body: NormsIn, user=Depends(current_user)):
    if not pplx_plus_client.is_configured():
        raise HTTPException(503, "Perplexity não configurado.")
    preset = get_preset(body.preset) or PRESETS["LNEC"]
    sys = preset["system"] + "\n\n" + NORMS_SYSTEM
    prompt = (
        f"Pergunta: {body.query}\n"
        f"Contexto: {body.context or 'N/A'}\n\n"
        f"Fontes preferenciais: {', '.join(preset['domains'])}. "
        "Devolve o JSON com normas aplicáveis, resposta textual e pontos de atenção."
    )
    try:
        r = await pplx_plus_client.ask_structured(prompt=prompt, system=sys, max_tokens=1800)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Perplexity falhou: {type(e).__name__}") from None
    return r


# ---------------------------------------------------------------------------
# 4. Materials Watch
# ---------------------------------------------------------------------------
class MaterialsIn(BaseModel):
    materials: list[str] = Field(..., min_length=1, max_length=15)
    region: str | None = "Portugal continental"


MATERIALS_SYSTEM = (
    "És analista de mercado de materiais de construção em Portugal. "
    "Devolve APENAS JSON:\n"
    "{\n"
    '  "materiais": [{"nome": string, "unidade": string, "preco_estimado_eur": number|null, "variacao_trimestral_pct": number|null, "fonte": string, "data_fonte": string|null, "tendencia": "subida"|"estavel"|"descida", "observacao": string}],\n'
    '  "regiao": string,\n'
    '  "data_consulta": string,\n'
    '  "aviso": string\n'
    "}\n"
    "Prefere fontes como Cimpor, Secil, Megavidro, Weber, CP Siderurgia, etc. PT-PT."
)


@router.post("/materials-watch")
async def materials_watch(body: MaterialsIn, user=Depends(current_user)):
    if not pplx_plus_client.is_configured():
        raise HTTPException(503, "Perplexity não configurado.")
    prompt = (
        f"Região: {body.region or 'Portugal continental'}\n"
        f"Materiais a monitorizar:\n- " + "\n- ".join(body.materials) +
        "\n\nIndica preço atual estimado por unidade (m³, ton, kg, saco…), "
        "variação trimestral %, tendência próxima (subida/estável/descida), "
        "fonte e data da fonte. Devolve APENAS o JSON pedido."
    )
    try:
        r = await pplx_plus_client.ask_structured(
            prompt=prompt, system=MATERIALS_SYSTEM, max_tokens=1800,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Perplexity falhou: {type(e).__name__}") from None
    return r


# ---------------------------------------------------------------------------
# Cache stats
# ---------------------------------------------------------------------------
@router.get("/cache-stats")
async def cache_stats(user=Depends(current_user)) -> dict:
    try:
        count = await db.pplx_cache.count_documents({})
    except Exception:
        count = 0
    return {"items": count, "ttl_hours": 24}
