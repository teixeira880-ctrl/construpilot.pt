"""Chatbot d'aide public ConstruPilot (Claude Opus 4.8 via clé LLM universelle)."""
import uuid

from fastapi import APIRouter
from pydantic import BaseModel, Field

from engines import ai

router = APIRouter(prefix="/help", tags=["help"])


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    session_id: str | None = None
    history: list[dict] = Field(default_factory=list)
    page: str | None = None


@router.post("/chat")
async def chat(body: ChatIn) -> dict:
    sid = body.session_id or ("help_" + uuid.uuid4().hex[:12])
    reply = await ai.help_assistant(body.history, body.message, sid, body.page)
    return {"reply": reply, "session_id": sid}
