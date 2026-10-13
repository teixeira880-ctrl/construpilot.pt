from typing import Literal

from core.db import db
from engines.presentation_assets import cached_asset, video_response
from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter(prefix="/presentation", tags=["Presentation videos"])
Variant = Literal["long-horizontal", "long-vertical", "short-horizontal", "short-vertical"]


class VideoInfo(BaseModel):
    variant: Variant
    title: str
    duration: float
    width: int
    height: int
    byte_size: int
    audio_language: str
    voice_disclosure: str
    file_url: str


@router.get("/videos", response_model=list[VideoInfo])
async def index():
    rows = await db.presentation_assets.find({"published": True}, {"_id": 0, "parts": 0}).sort("variant", 1).to_list(4)
    return [VideoInfo(**{**r, "file_url": f'/api/presentation/videos/{r["variant"]}.mp4'}) for r in rows]


@router.api_route("/videos/{variant}.mp4", methods=["GET", "HEAD"])
async def video(variant: Variant, request: Request):
    record, file = await cached_asset(variant)
    return video_response(request, record, file)