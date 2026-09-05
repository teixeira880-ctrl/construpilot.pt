"""Chatbot d'aide public ConstruPilot (modèle actif configurable) + actions suggérées."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from core.db import db
from engines import ai
from engines.evolution import EVO_AI_MODELS

router = APIRouter(prefix="/help", tags=["help"])

# Règles d'actions : mot-clé → bouton pré-rempli (label + route)
ACTION_RULES = [
    (("plan", "dwg", "dxf", "métré", "metre"), {"label": "Analyser un plan", "to": "/plan"}),
    (("étanch", "etanch", "toiture", "vrd", "réseau", "reseau", "ferraill", "acier", "approvision", "commande", "fournisseur"),
     {"label": "Ouvrir l'Approvisionnement", "to": "/appro"}),
    (("devis", "estim", "chiffr", "budget", "prix", "coût", "cout"),
     {"label": "Démarrer mon estimation", "to": "/estimation"}),
    (("calcul", "surface", "volume", "quantit"), {"label": "Ouvrir les calculateurs", "to": "/calculateurs"}),
    (("tarif", "offre", "abonn", "pro"), {"label": "Voir les tarifs", "to": "/tarifs"}),
]
DEFAULT_ACTIONS = [{"label": "Démarrer mon estimation", "to": "/estimation"},
                   {"label": "Analyser un plan", "to": "/plan"}]


def _suggest_actions(text: str, page: str | None) -> list:
    t = (text or "").lower()
    out, seen = [], set()
    for keys, action in ACTION_RULES:
        if any(k in t for k in keys) and action["to"] not in seen and action["to"] != (page or ""):
            out.append(action); seen.add(action["to"])
    if not out:
        out = [a for a in DEFAULT_ACTIONS if a["to"] != (page or "")]
    return out[:2]


async def _active_model():
    doc = await db.app_settings.find_one({"_id": "evolution"}) or {}
    key = doc.get("active_ai_model", "opus")
    return EVO_AI_MODELS.get(key, EVO_AI_MODELS["opus"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    history: list[dict] = Field(default_factory=list)
    page: str | None = None


@router.post("/chat")
async def chat(body: ChatIn) -> dict:
    sid = body.session_id or ("help_" + uuid.uuid4().hex[:12])
    prov, mdl = await _active_model()
    reply = await ai.help_assistant(body.history, body.message, sid, body.page, prov, mdl)
    actions = _suggest_actions(body.message + " " + reply, body.page)
    return {"reply": reply, "session_id": sid, "actions": actions}
