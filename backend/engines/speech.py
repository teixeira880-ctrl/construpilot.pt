"""Voix : dictée (STT) et lecture (TTS) via la clé Emergent (OpenAI Whisper / TTS managés)."""
import io
import os

from emergentintegrations.llm.openai.speech_to_text import OpenAISpeechToText
from emergentintegrations.llm.openai.text_to_speech import OpenAITextToSpeech

STT_MODEL = "whisper-1"
TTS_MODEL = "tts-1"
TTS_VOICE = "alloy"
MAX_TTS_CHARS = 4000


def _key() -> str:
    return os.environ["EMERGENT_LLM_KEY"]


async def transcribe(data: bytes, filename: str = "audio.webm", language: str = "fr") -> str:
    buf = io.BytesIO(data)
    buf.name = filename if "." in filename else "audio.webm"
    r = await OpenAISpeechToText(api_key=_key()).transcribe(buf, model=STT_MODEL, language=language, response_format="json")
    return (getattr(r, "text", None) or (r.get("text") if isinstance(r, dict) else "") or "").strip()


async def synthesize(text: str, voice: str = TTS_VOICE, speed: float = 1.0) -> bytes:
    clean = " ".join(text.split())[:MAX_TTS_CHARS]
    if not clean:
        raise ValueError("Texte vide")
    return await OpenAITextToSpeech(api_key=_key()).generate_speech(clean, model=TTS_MODEL, voice=voice, speed=speed, response_format="mp3")
