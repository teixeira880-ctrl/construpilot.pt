"""Recover the already billed sample from ElevenLabs history; never generate speech."""
import json
import os

from config import VOICE, WORK
from elevenlabs import ElevenLabs
from story import SCENES

client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
history = client.history.list(voice_id=VOICE, page_size=10, sort_direction="desc")
item = next((h for h in history.history if h.text == SCENES[0]["text"] and h.voice_id == VOICE), None)
if item is None:
    raise RuntimeError("Sample not found; no regeneration attempted")
audio = client.history.get_audio(item.history_item_id)
data = audio if isinstance(audio, bytes) else b"".join(audio)
(WORK / "sample_original.mp3").write_bytes(data)
(WORK / "sample_original.json").write_text(json.dumps({"text": item.text, "voice_id": item.voice_id, "recovered_from_history": True}, ensure_ascii=False))
print("Recovered original sample without another TTS call:", len(data), "bytes")