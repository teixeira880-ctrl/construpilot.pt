from typing import Annotated

from core.security import current_user
from engines.assistant_jobs import active_jobs, cancel_job, enqueue, owned_job, public_job
from engines.access import require_level
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from routes.assistant import MsgIn

router = APIRouter(prefix="/assistant/jobs", tags=["assistant-jobs"])


class JobOut(BaseModel):
    job_id: str
    conversation_id: str
    request_id: str
    sequence: int
    status: str
    created_at: str
    updated_at: str
    live: dict | None = None
    error: str | None = None
    cancel_requested: bool = False


@router.get("")
async def list_active_jobs(user: Annotated[dict, Depends(current_user)]):
    return {"jobs": await active_jobs(user["user_id"])}


@router.post("", response_model=JobOut, status_code=202, dependencies=[Depends(require_level("particulier_payant"))])
async def submit_job(body: MsgIn, user: Annotated[dict, Depends(current_user)]):
    return await enqueue(body, user)


@router.get("/{job_id}", response_model=JobOut)
async def get_job(job_id: str, user: Annotated[dict, Depends(current_user)]):
    return public_job(await owned_job(job_id, user["user_id"]))


@router.post("/{job_id}/cancel", response_model=JobOut)
async def stop_job(job_id: str, user: Annotated[dict, Depends(current_user)]):
    return await cancel_job(job_id, user["user_id"])
