"""Modelos Pydantic + utilitários do CRM lite (`customer_activity`)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field


COLLECTION = "customer_activity"

Kind = Literal[
    "contact", "quote", "ai_chat", "permit", "download", "calculation",
]
State = Literal["novo", "em_curso", "respondido", "fechado"]


class AttachmentRef(BaseModel):
    model_config = ConfigDict(extra="ignore")
    kind: str = "file"           # file | url | mongo_id
    ref: str                     # path storage / url / id
    name: str = ""
    content_type: str | None = None
    size_bytes: int | None = None


class Note(BaseModel):
    model_config = ConfigDict(extra="ignore")
    author: str                  # email do admin autor
    created_at: str              # ISO 8601 UTC
    text: str


class StateChange(BaseModel):
    model_config = ConfigDict(extra="ignore")
    from_state: State | None = Field(default=None, alias="from")
    to_state: State = Field(alias="to")
    author: str
    created_at: str
    note: str | None = None


class ActivityCreate(BaseModel):
    """Entrada para inserção programática (via helper, não exposto directamente)."""
    model_config = ConfigDict(extra="ignore")
    kind: Kind
    user_email: EmailStr
    user_name: str = ""
    user_phone: str | None = None
    summary: str = Field(..., min_length=1, max_length=400)
    payload: dict[str, Any] = Field(default_factory=dict)
    source_url: str | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)
    is_fr_project: bool = False


class ActivityOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str                      # Mongo _id serialized
    created_at: str
    updated_at: str
    kind: Kind
    user_email: str              # já mascarado nos list endpoints quando aplicável
    user_name: str = ""
    user_phone: str | None = None
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    source_url: str | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)
    state: State = "novo"
    assigned_to: str | None = None
    internal_notes: list[Note] = Field(default_factory=list)
    state_history: list[StateChange] = Field(default_factory=list)
    is_fr_project: bool = False
    no_email: bool = False
    last_email_at: str | None = None


class ActivityPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")
    state: State | None = None
    assigned_to: str | None = None
    note: str | None = None
    send_email: bool | None = None    # força/skip email por mudança de estado


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    text: str = Field(..., min_length=1, max_length=4000)


def mask_email(email: str) -> str:
    """Mascara email para logs/strings auditáveis: `e***@dominio.com`."""
    if not email or "@" not in email:
        return "***"
    local, _, domain = email.partition("@")
    first = local[:1] if local else "*"
    return f"{first}***@{domain}"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
