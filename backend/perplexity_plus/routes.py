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
    "Tu es l'Assistant BTP, l'assistant d'œuvres IA de ConstruPilot. Tu réponds en français à des "
    "professionnels du bâtiment (artisans, chefs de chantier, maîtres d'œuvre). "
    "Cite systématiquement tes sources (URL) quand tu t'appuies sur du web. "
    "Sois concis, structuré, orienté action. Rappelle systématiquement que "
    "les informations réglementaires doivent être vérifiées auprès des textes "
    "officiels avant application."
)


def _sse(event: dict) -> bytes:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n".encode("utf-8")


@router.post("/chat")
@limiter.limit("20/minute")
async def chat_stream(body: ChatIn, request: Request, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY non configuré")

    async def gen() -> AsyncIterator[bytes]:
        instructions = CHAT_SYSTEM
        if body.context:
            instructions += f"\n\nContexte transmis par l'utilisateur :\n{body.context}"
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
    "Tu es expert en réglementation française du bâtiment (Code de la "
    "construction, DTU, NF, RE2020, PMR, sécurité incendie). Réponds "
    "précisément à la question posée en citant les articles / normes /"
    " DTU applicables. Sois structuré : "
    "1) Réponse synthétique · "
    "2) Textes applicables (référence exacte + URL) · "
    "3) Points de vigilance · "
    "4) Disclaimer : « À vérifier auprès des textes officiels ». "
    "Refuse de répondre si l'information n'est pas sourcée."
)


@router.post("/reglementation")
@limiter.limit("15/hour")
async def reglementation(body: ReglIn, request: Request, response: Response, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY non configuré")
    q = body.question
    if body.project_type:
        q = f"[Type de projet : {body.project_type}] {q}"
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
    "Tu es expert en chiffrage BTP en France. À partir de la description "
    "d'un chantier, tu proposes une trame de devis structurée. Utilise les "
    "prix du marché récents que tu trouves via recherche web. "
    "Réponds STRICTEMENT en JSON valide, sans commentaire, avec ce schéma :\n"
    "{\n"
    '  "titre": str,\n'
    '  "lignes": [ { "poste": str, "description": str, "unite": str,\n'
    '                "quantite": float, "prix_unitaire_ht": float,\n'
    '                "total_ht": float, "source": str|null } ],\n'
    '  "total_ht": float,\n'
    '  "tva_taux": 20 | 10 | 5.5,\n'
    '  "total_ttc": float,\n'
    '  "hypotheses": [ str ],\n'
    '  "sources_prix": [ { "url": str, "titre": str } ]\n'
    "}\n"
    "Ne réponds RIEN d'autre que ce JSON."
)


@router.post("/documents/devis")
@limiter.limit("10/hour")
async def draft_devis(body: DevisIn, request: Request, response: Response, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY non configuré")
    q_parts = [f"Chantier : {body.description}"]
    if body.surface_m2:
        q_parts.append(f"Surface : {body.surface_m2} m²")
    if body.region:
        q_parts.append(f"Région : {body.region}")
    if body.prestations_incluses:
        q_parts.append(
            "Prestations à inclure : " + ", ".join(body.prestations_incluses)
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
    "Tu es rédacteur CCTP (Cahier des Clauses Techniques Particulières) "
    "spécialisé en marchés privés BTP en France. Rédige un article CCTP "
    "précis, en français, structuré ainsi :\n"
    "1. Généralités\n"
    "2. Description des ouvrages\n"
    "3. Prescriptions techniques (matériaux, mise en œuvre) — cite les "
    "DTU / NF / EN applicables (référence complète)\n"
    "4. Contrôles et essais\n"
    "5. Tolérances\n"
    "Ne cite que des références vérifiables. Ajoute en fin de réponse la "
    "liste des sources consultées."
)


@router.post("/documents/cctp")
@limiter.limit("10/hour")
async def draft_cctp(body: CctpIn, request: Request, response: Response, user=Depends(current_user)):
    if not pplx.configured():
        raise HTTPException(503, "PERPLEXITY_API_KEY non configuré")
    ratio = {"court": 1000, "standard": 2000, "detaille": 3500}[body.niveau_detail]
    q = f"Lot : {body.lot}\nOuvrage à décrire : {body.description}\nNiveau : {body.niveau_detail}"
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
