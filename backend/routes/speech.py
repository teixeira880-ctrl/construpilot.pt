"""Routes voix : dictée (pros connectés + invités du portail) et lecture à voix haute."""
import io

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.rate_limit import limiter
from core.security import current_user
from engines import speech
from routes.portal import current_participant

router = APIRouter(prefix="/speech", tags=["speech"])
MAX_AUDIO = 15 * 1024 * 1024


class TtsIn(BaseModel):
    text: str = Field(..., min_length=1, max_length=speech.MAX_TTS_CHARS)
    voice: str = Field(speech.TTS_VOICE, pattern="^(alloy|ash|coral|echo|fable|nova|onyx|sage|shimmer)$")
    speed: float = Field(1.0, ge=0.5, le=2.0)


async def _read(file: UploadFile) -> bytes:
    data = await file.read(MAX_AUDIO + 1)
    if len(data) > MAX_AUDIO:
        raise HTTPException(413, "Audio trop volumineux (15 Mo max)")
    if not data:
        raise HTTPException(422, "Audio vide")
    return data


async def _transcribe(file: UploadFile) -> dict:
    data = await _read(file)
    try:
        text = await speech.transcribe(data, file.filename or "audio.webm")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Transcription impossible — {type(e).__name__}")
    return {"text": text, "engine": "emergent-whisper"}


def _mp3(audio: bytes) -> StreamingResponse:
    return StreamingResponse(io.BytesIO(audio), media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.post("/transcribe")
@limiter.limit("60/hour")
async def transcribe(request: Request, response: Response, file: UploadFile = File(...), user=Depends(current_user)) -> dict:
    return await _transcribe(file)


@router.post("/tts")
@limiter.limit("120/hour")
async def tts(body: TtsIn, request: Request, response: Response, user=Depends(current_user)):
    try:
        return _mp3(await speech.synthesize(body.text, body.voice, body.speed))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synthèse vocale impossible — {type(e).__name__}")


@router.post("/portal/transcribe")
@limiter.limit("40/hour")
async def portal_transcribe(request: Request, response: Response, file: UploadFile = File(...), p=Depends(current_participant)) -> dict:
    """Dictée pour les invités (messages, signalement de problème)."""
    return await _transcribe(file)


@router.post("/portal/tts")
@limiter.limit("60/hour")
async def portal_tts(body: TtsIn, request: Request, response: Response, p=Depends(current_participant)):
    """Lecture à voix haute pour les invités (comptes rendus, diagnostics publiés)."""
    try:
        return _mp3(await speech.synthesize(body.text, body.voice, body.speed))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Synthèse vocale impossible — {type(e).__name__}")
