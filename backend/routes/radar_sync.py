from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import current_user
from engines.radar_zones import normalize_departments
from engines.sitadel_sync import ensure_sync, sync_status

router = APIRouter(prefix="/radar", tags=["radar-official-source"])


class SyncIn(BaseModel):
    departments: list[str] = Field(min_length=1, max_length=101)


class DepartmentStatus(BaseModel):
    department: str
    status: str
    count: int = 0
    sources: list[dict] = Field(default_factory=list)
    last_success_at: str | None = None
    stage: str | None = None
    error: str | None = None


class SyncOut(BaseModel):
    departments: list[DepartmentStatus]
    source_name: str
    source_url: str
    window_start: str
    window_end: str


@router.post("/sync", response_model=SyncOut)
async def refresh_official(body: SyncIn, user=Depends(current_user)):
    if user.get("account_type") != "pro" and user.get("role") != "admin":
        raise HTTPException(403, "Radar reservado a profissionais.")
    departments = normalize_departments(body.departments)
    await ensure_sync(departments, force=True)
    return await sync_status(departments)