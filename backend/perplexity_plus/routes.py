"""4 endpoints Perplexity supplémentaires pour ConstruPilot.

- ``/api/pplx/chat`` : assistant conversationnel avec streaming SSE + citations
- ``/api/pplx/reglementation`` : recherche filtrée Legifrance / AFNOR / CSTB / RE2020
- ``/api/pplx/documents/devis`` : rédaction assistée d'un devis (JSON structuré)
- ``/api/pplx/documents/cctp`` : article CCTP référencé DTU / normes

Chacun est rate-limité et exige un utilisateur connecté.
"""

import json
from typing import AsyncIterator

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.rate_limit import limiter
from core.security import current_user
from perplexity_plus import client as pplx

router = APIRouter(prefix="/pplx", tags=["perplexity+"])


# ─────────────────────────────────────────────────────────────────────────────
# 1) Chat streamé
# ─────────────────────────────────────────────────────────────────────────────
class ChatIn(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    context: str | None = Field(None, max_length=4000)
    preset: str = Field("medium", pattern="^(fast|medium|high)$")


CHAT_SYSTEM = (
    "És o Assistente de Construção, o assistente de obras IA do ConstruPilot. Respondes em português europeu a profissionais da construção (empreiteiros, encarregados, diretores de obra, projetistas). Cita sistematicamente as tuas fontes (URL) quando te apoias na web. Sê conciso, estruturado, orientado para a ação. Lembra sistematicamente que as informações regulamentares devem ser verificadas nos textos oficiais (Diário da República) antes de serem aplicadas."
)


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


@router.post("/chat")
@limiter.limit("20/minute")
async def chat_stream(body: ChatIn, request: Request, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY não configurada")

    async def gen() -> AsyncIterator[bytes]:
        instructions = CHAT_SYSTEM
        if body.context:
            instructions += f'\n\nContexto transmitido pelo utilizador:\n{body.context}'
        try:
            async for evt in pplx.stream(
                question=body.message,
                instructions=instructions,
                preset=body.preset,
                search_context_size="medium",
                max_results=8,
                max_output_tokens=1200,
            ):
                yield _sse(evt)
        except Exception as e:
            yield _sse({"type": "error", "message": str(e)})

    return StreamingResponse(gen(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2) Réglementation ciblée (Legifrance / AFNOR / CSTB / RE2020)
# ─────────────────────────────────────────────────────────────────────────────
_REGL_DOMAINS = [
    "legifrance.gouv.fr",
    "cstb.fr",
    "afnor.org",
    "boutique.afnor.org",
    "rt-batiment.fr",
    "rt-re-batiment.developpement-durable.gouv.fr",
    "ecologie.gouv.fr",
    "service-public.fr",
    "ademe.fr",
    "qualibat.com",
]


class ReglIn(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    project_type: str | None = Field(None, max_length=100)
    preset: str = Field("high", pattern="^(fast|medium|high)$")


REGL_SYSTEM = (
    "És especialista em regulamentação portuguesa da construção (RJUE, RGEU, Eurocódigos NP EN e Anexos Nacionais, REH/RECS (SCE), acessibilidades DL 163/2006, SCIE – DL 220/2008 e RT-SCIE, especificações LNEC). Responde com precisão à pergunta feita citando os artigos / normas / diplomas aplicáveis. Sê estruturado: 1) Resposta sintética · 2) Textos aplicáveis (referência exata + URL) · 3) Pontos de atenção · 4) Aviso: «A verificar nos textos oficiais (Diário da República)». Recusa responder se a informação não tiver fonte."
)


@router.post("/reglementation")
@limiter.limit("15/hour")
async def reglementation(body: ReglIn, request: Request, response: Response, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY não configurada")
    q = body.question
    if body.project_type:
        q = f'[Tipo de projeto: {body.project_type}] {q}'
    res = await pplx.ask(
        question=q,
        instructions=REGL_SYSTEM,
        preset=body.preset,
        domain_filter=_REGL_DOMAINS,
        search_context_size="high",
        max_results=10,
        max_output_tokens=1800,
    )
    return res


# ─────────────────────────────────────────────────────────────────────────────
# 3) Rédaction assistée de devis (JSON structuré)
# ─────────────────────────────────────────────────────────────────────────────
class DevisIn(BaseModel):
    description: str = Field(..., min_length=10, max_length=3000)
    surface_m2: float | None = Field(None, gt=0, lt=100000)
    region: str | None = Field(None, max_length=100)
    prestations_incluses: list[str] | None = None


DEVIS_SYSTEM = (
    "És especialista em orçamentação de construção em Portugal. A partir da descrição de uma obra, propões uma estrutura de orçamento organizada. Utiliza os preços de mercado recentes em Portugal que encontres através de pesquisa web. Responde ESTRITAMENTE em JSON válido, sem comentários, com este esquema:\n{\n  \"titre\": str,\n  \"lignes\": [ { \"poste\": str, \"description\": str, \"unite\": str,\n                \"quantite\": float, \"prix_unitaire_ht\": float,\n                \"total_ht\": float, \"source\": str|null } ],\n  \"total_ht\": float,\n  \"tva_taux\": 23 | 13 | 6,\n  \"total_ttc\": float,\n  \"hypotheses\": [ str ],\n  \"sources_prix\": [ { \"url\": str, \"titre\": str } ]\n}\nOs textos (titre, poste, description, hypotheses) em português europeu. Não respondas NADA além deste JSON."
)


@router.post("/documents/devis")
@limiter.limit("10/hour")
async def draft_devis(body: DevisIn, request: Request, response: Response, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY não configurada")
    q_parts = [f'Obra: {body.description}']
    if body.surface_m2:
        q_parts.append(f'Área: {body.surface_m2} m²')
    if body.region:
        q_parts.append(f'Região: {body.region}')
    if body.prestations_incluses:
        q_parts.append(
            "Serviços a incluir: " + ", ".join(body.prestations_incluses)
        )
    q = "\n".join(q_parts)
    res = await pplx.ask(
        question=q,
        instructions=DEVIS_SYSTEM,
        preset="high",
        search_context_size="medium",
        max_results=8,
        max_output_tokens=2500,
    )
    # Tenter de parser le JSON renvoyé
    try:
        parsed = json.loads(res["text"])
    except Exception:
        # Fallback : extraire la première accolade jusqu'à la dernière
        txt = res["text"]
        start = txt.find("{")
        end = txt.rfind("}")
        try:
            parsed = json.loads(txt[start:end + 1])
        except Exception:
            parsed = None

    return {
        "devis": parsed,
        "raw_text": res["text"] if parsed is None else None,
        "citations": res.get("citations", []),
        "cost_usd": res.get("cost_usd"),
        "cached": res.get("cached", False),
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4) Article CCTP référencé DTU / normes
# ─────────────────────────────────────────────────────────────────────────────
class CctpIn(BaseModel):
    lot: str = Field(..., min_length=2, max_length=100)
    description: str = Field(..., min_length=10, max_length=2000)
    niveau_detail: str = Field("standard", pattern="^(court|standard|detaille)$")


CCTP_SYSTEM = (
    "És redator de Cadernos de Encargos (cláusulas técnicas) especializado em obras particulares de construção em Portugal. Redige um artigo de caderno de encargos preciso, em português europeu, estruturado assim:\n1. Generalidades\n2. Descrição dos trabalhos\n3. Prescrições técnicas (materiais, execução) — cita as normas NP / NP EN / EN e especificações LNEC aplicáveis (referência completa)\n4. Controlos e ensaios\n5. Tolerâncias\nCita apenas referências verificáveis. Acrescenta no fim da resposta a lista das fontes consultadas."
)


@router.post("/documents/cctp")
@limiter.limit("10/hour")
async def draft_cctp(body: CctpIn, request: Request, response: Response, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY não configurada")
    ratio = {"court": 1000, "standard": 2000, "detaille": 3500}[body.niveau_detail]
    q = f'Lot : {body.lot}\nTrabalho a descrever: {body.description}\nPiso: {body.niveau_detail}'
    res = await pplx.ask(
        question=q,
        instructions=CCTP_SYSTEM,
        preset="high",
        domain_filter=_REGL_DOMAINS + ["batichoix.com", "editions-eyrolles.com"],
        search_context_size="high",
        max_results=10,
        max_output_tokens=ratio,
    )
    return res


# ─────────────────────────────────────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────────────────────────────────────
@router.get("/status")
async def status(user=Depends(current_user)):
    return {
        "configured": pplx.configured(),
        "endpoints": [
            "/api/pplx/chat (SSE)",
            "/api/pplx/reglementation",
            "/api/pplx/documents/devis",
            "/api/pplx/documents/cctp",
        ],
    }
