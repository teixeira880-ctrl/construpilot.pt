"""STAIRPILOT — Calcul d'escaliers béton (moteur déterministe, DTU 36.3 / DTU 21).

Portage du moteur `stair_engine` dans ConstruPilot. Réservé aux comptes Pro.
Toutes les cotes en millimètres. Aucune IA pour les calculs (déterministe),
l'assistant IA se contente d'appeler ce moteur et de commenter les résultats.
"""
from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from core.db import db
from core.security import current_user, pro_required

from stair_engine import (
    ConcreteAnalysisInput,
    ConcreteAnalysisResult,
    DTU_36_3_FR,
    HalfTurnInput,
    HelicoidalInput,
    OptimizeInput,
    OptimizeResult,
    QuarterTurnBottomInput,
    QuarterTurnTopInput,
    StairInput,
    StairResult,
    compute_concrete_analysis,
    compute_half_turn,
    compute_helicoidal,
    compute_optimize,
    compute_quarter_turn_bottom,
    compute_quarter_turn_top,
    compute_straight,
)
from stair_engine.pdf_dossier import generate_dossier_pdf
from stair_engine.assistant import chat_with_assistant

router = APIRouter(prefix="/stairs", tags=["stairs"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# MOTEUR DE CALCUL (déterministe) — un endpoint par type d'escalier
# ---------------------------------------------------------------------------
@router.post("/calculate/straight", response_model=StairResult)
async def calculate_straight(payload: StairInput, user=Depends(pro_required)) -> StairResult:
    """Escalier droit béton (moteur déterministe, DTU 36.3)."""
    return compute_straight(payload)


@router.post("/calculate/quarter-turn-bottom", response_model=StairResult)
async def calculate_quarter_turn_bottom(payload: QuarterTurnBottomInput, user=Depends(pro_required)) -> StairResult:
    """Escalier quart tournant bas (mode 'balanced' ou 'straight')."""
    return compute_quarter_turn_bottom(payload)


@router.post("/calculate/quarter-turn-top", response_model=StairResult)
async def calculate_quarter_turn_top(payload: QuarterTurnTopInput, user=Depends(pro_required)) -> StairResult:
    """Escalier quart tournant haut (mode 'balanced' ou 'straight')."""
    return compute_quarter_turn_top(payload)


@router.post("/calculate/half-turn", response_model=StairResult)
async def calculate_half_turn(payload: HalfTurnInput, user=Depends(pro_required)) -> StairResult:
    """Escalier demi-tournant (mode 'balanced' ou 'straight')."""
    return compute_half_turn(payload)


@router.post("/calculate/helicoidal", response_model=StairResult)
async def calculate_helicoidal(payload: HelicoidalInput, user=Depends(pro_required)) -> StairResult:
    """Escalier hélicoïdal (colimaçon)."""
    return compute_helicoidal(payload)


@router.post("/optimize", response_model=OptimizeResult)
async def optimize_stair(payload: OptimizeInput, user=Depends(pro_required)) -> OptimizeResult:
    """Propose N solutions d'escalier triées par pertinence (optimiseur)."""
    result = compute_optimize(payload)
    # AK.2 — regista cálculo no CRM lite (fail-soft)
    try:
        from engines.activity_crm.record import record_activity
        n_solutions = len(getattr(result, "solutions", []) or [])
        await record_activity(
            kind="calculation",
            user_email=user.get("email") or "",
            user_name=user.get("name") or "",
            summary=f"Otimizador escadas — {n_solutions} soluções"[:160],
            source_url="/api/stairs/optimize",
            payload={"calc_type": "stair_optimize", "n_solutions": n_solutions},
        )
    except Exception:
        pass
    return result


@router.post("/concrete/analyze", response_model=ConcreteAnalysisResult)
async def concrete_analyze(payload: ConcreteAnalysisInput, user=Depends(pro_required)) -> ConcreteAnalysisResult:
    """Analyse béton armé : métré + pré-dimensionnement paillasse + ferraillage indicatif (DTU 21)."""
    return compute_concrete_analysis(payload)


@router.get("/norms/fr")
async def get_norms_fr(user=Depends(current_user)):
    """Seuils DTU 36.3 utilisés par le moteur."""
    return DTU_36_3_FR.as_dict()


# ---------------------------------------------------------------------------
# DOSSIER PDF — le nom du projet devient le nom du fichier PDF
# ---------------------------------------------------------------------------
class DossierRequest(BaseModel):
    project_name: str
    stair_input: dict
    stair_result: dict
    concrete_analysis: dict | None = None
    author: str | None = None


@router.post("/dossier/generate")
async def dossier_generate(payload: DossierRequest, user=Depends(pro_required)):
    pdf_bytes = generate_dossier_pdf(
        project_name=payload.project_name,
        stair_input=payload.stair_input,
        stair_result=payload.stair_result,
        concrete_analysis=payload.concrete_analysis,
        author=payload.author or user.get("company") or user.get("name"),
    )
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in (payload.project_name or "escalier")).strip("_")[:60] or "escalier"
    fname = f"{safe}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------------------
# ASSISTANT IA (commente les résultats du moteur, ne calcule jamais lui-même)
# ---------------------------------------------------------------------------
class AssistantChatRequest(BaseModel):
    message: str
    conversation_id: str | None = None


@router.post("/assistant/chat")
async def assistant_chat(payload: AssistantChatRequest, user=Depends(pro_required)):
    conv_id = payload.conversation_id or f"stair_{secrets.token_hex(8)}"
    existing = await db.stair_conversations.find_one({"_id": conv_id, "user_id": user["user_id"]}, {"_id": 0})
    history = (existing or {}).get("messages", []) if existing else []
    history_prompt = [{"role": m["role"], "content": m["content"]} for m in history if m.get("role") in ("user", "assistant")]

    reply = await chat_with_assistant(conv_id, payload.message, history_prompt)

    now_iso = _now()
    new_messages = history + [
        {"role": "user", "content": payload.message, "timestamp": now_iso},
        {"role": "assistant", "content": reply.reply_text, "timestamp": now_iso},
    ]
    await db.stair_conversations.update_one(
        {"_id": conv_id},
        {"$set": {"user_id": user["user_id"], "messages": new_messages, "updated_at": now_iso},
         "$setOnInsert": {"created_at": now_iso}},
        upsert=True,
    )
    return {
        "conversation_id": reply.conversation_id,
        "reply_text": reply.reply_text,
        "referenced_engine_calls": reply.referenced_engine_calls,
        "computed_solutions": reply.computed_solutions,
        "metadata": reply.metadata,
    }


@router.get("/assistant/conversations/{conversation_id}")
async def get_assistant_conversation(conversation_id: str, user=Depends(pro_required)):
    doc = await db.stair_conversations.find_one(
        {"_id": conversation_id, "user_id": user["user_id"]}, {"_id": 0})
    if not doc:
        return {"conversation_id": conversation_id, "messages": []}
    return {"conversation_id": conversation_id, **doc}


# ---------------------------------------------------------------------------
# ESCALIER → DEVIS : 3 lignes (béton m³, coffrage m², ferraillage kg)
# ---------------------------------------------------------------------------
class StairToQuoteIn(BaseModel):
    project_name: str = "Escada"
    stair_result: dict
    concrete_analysis: dict | None = None
    client_id: str | None = None
    chantier_id: str | None = None
    detailed_steel: bool = False


@router.post("/to-quote")
async def stair_to_quote(body: StairToQuoteIn, user=Depends(pro_required)):
    """Crée un devis brouillon avec les lignes déterministes de l'escalier
    (béton, coffrage, ferraillage). Prix unitaires laissés éditables (à compléter).
    Si detailed_steel=true, le ferraillage est éclaté en une ligne par repère de la nomenclature."""
    from routes.documents import DocIn, DocLine, create_document

    ca = body.concrete_analysis
    if not ca:
        res = compute_concrete_analysis(ConcreteAnalysisInput(
            stair_result=body.stair_result, stair_type=body.stair_result.get("stair_type", "straight")))
        ca = res.model_dump()
    q = ca.get("quantities", {})
    steel = (ca.get("reinforcement", {}) or {}).get("total_steel_kg") or q.get("total_steel_kg") or 0
    cls = "C25/30"
    lines = []
    if float(q.get("concrete_volume_m3", 0)) > 0:
        lines.append(DocLine(kind="line", line_kind="ouvrage", designation=f'Betão {cls} para escada',
                             description="Laje da escada + degraus (medição determinística)", unit="m3",
                             qty=round(float(q.get("concrete_volume_m3", 0)), 3), unit_price_ht=0,
                             category="Escada betão armado", price_missing=True, price_estimated=True))
    if float(q.get("formwork_area_m2", 0)) > 0:
        lines.append(DocLine(kind="line", line_kind="ouvrage", designation="Cofragem da escada",
                             description="Laje + faces laterais + degraus", unit="m2",
                             qty=round(float(q.get("formwork_area_m2", 0)), 2), unit_price_ht=0,
                             category="Escada betão armado", price_missing=True, price_estimated=True))
    nomen = ca.get("nomenclature") or []
    if body.detailed_steel and nomen:
        for r in nomen:
            if not float(r.get("weight_kg", 0) or 0) > 0:
                continue
            desc = f"Ø {r.get('diameter', '')} · L={r.get('length_m', 0)} m × {r.get('count', 0)} = {r.get('total_length_m', 0)} ml"
            lines.append(DocLine(kind="line", line_kind="ouvrage",
                                 designation=f"Armadura ref.{r.get('repere', '')} — {r.get('designation', 'Armature')}",
                                 description=desc, unit="kg", qty=round(float(r.get("weight_kg", 0)), 2),
                                 unit_price_ht=0, category="Armaduras da escada", price_missing=True, price_estimated=True))
    elif float(steel) > 0:
        lines.append(DocLine(kind="line", line_kind="ouvrage", designation="Armaduras (aço A500)",
                             description="Nomenclatura indicativa de armaduras", unit="kg",
                             qty=round(float(steel), 2), unit_price_ht=0,
                             category="Escada betão armado", price_missing=True, price_estimated=True))
    if not lines:
        raise HTTPException(422, "Quantidades nulas — calcule primeiro uma escada exequível")
    doc = DocIn(doc_type="quote", title=f"Escada — {body.project_name}"[:160],
                client_id=body.client_id, chantier_id=body.chantier_id, lines=lines, status="draft")
    return await create_document(doc, user)
# ---------------------------------------------------------------------------
class StairProjectIn(BaseModel):
    name: str
    stair_type: str = "straight"
    input: dict | None = None
    result: dict | None = None
    concrete_analysis: dict | None = None


def _clean_project(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in ("_id", "user_id")}


@router.get("/projects")
async def list_projects(user=Depends(pro_required)):
    rows = await db.stair_projects.find(
        {"user_id": user["user_id"]}, {"_id": 0, "user_id": 0}).sort("updated_at", -1).to_list(500)
    return {"projects": rows}


@router.post("/projects")
async def create_project(body: StairProjectIn, user=Depends(pro_required)):
    now = _now()
    doc = {
        "project_id": f"stp_{secrets.token_hex(8)}",
        "user_id": user["user_id"],
        "name": (body.name or "Escada sem nome").strip()[:120],
        "stair_type": body.stair_type,
        "input": body.input or {},
        "result": body.result,
        "concrete_analysis": body.concrete_analysis,
        "created_at": now,
        "updated_at": now,
    }
    await db.stair_projects.insert_one(dict(doc))
    return {"ok": True, "project": _clean_project(doc)}


@router.get("/projects/{project_id}")
async def get_project(project_id: str, user=Depends(pro_required)):
    doc = await db.stair_projects.find_one(
        {"project_id": project_id, "user_id": user["user_id"]}, {"_id": 0, "user_id": 0})
    if not doc:
        raise HTTPException(404, "Projeto não encontrado")
    return doc


@router.put("/projects/{project_id}")
async def update_project(project_id: str, body: StairProjectIn, user=Depends(pro_required)):
    upd = {"name": (body.name or "Escada sem nome").strip()[:120],
           "stair_type": body.stair_type, "updated_at": _now()}
    if body.input is not None:
        upd["input"] = body.input
    if body.result is not None:
        upd["result"] = body.result
    if body.concrete_analysis is not None:
        upd["concrete_analysis"] = body.concrete_analysis
    res = await db.stair_projects.update_one(
        {"project_id": project_id, "user_id": user["user_id"]}, {"$set": upd})
    if not res.matched_count:
        raise HTTPException(404, "Projeto não encontrado")
    return {"ok": True}


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, user=Depends(pro_required)):
    await db.stair_projects.delete_one({"project_id": project_id, "user_id": user["user_id"]})
    return {"ok": True}
