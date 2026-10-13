"""ElevenLabs native FR voice, character alignment, content-addressed cached audio."""
import base64
import hashlib
import json
import os
import subprocess

from config import MODEL, VOICE, WORK
from story import SCENES, SHORT


def generate(scenes):
    from elevenlabs import ElevenLabs, VoiceSettings
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"], timeout=120)
    voice = client.voices.get(VOICE)
    if (voice.labels or {}).get("gender") != "male" or (voice.labels or {}).get("language") != "fr":
        raise RuntimeError("Configured voice is not labelled French male; stop for review")
    out = WORK / "voice"
    out.mkdir(exist_ok=True)
    print("Voice verified:", voice.name, voice.labels, flush=True)
    for scene in scenes:
        key = hashlib.sha256(json.dumps([scene["text"], VOICE, MODEL, "mp3_44100_128", 0.35, 0.38]).encode()).hexdigest()[:20]
        meta = out / f"{scene['id']}.json"
        audio = out / f"{scene['id']}.mp3"
        if meta.exists() and audio.exists() and json.loads(meta.read_text()).get("hash") == key:
            print("CACHED", scene["id"], flush=True)
            continue
        # No retries: a failed paid generation must be inspected before rerunning.
        result = client.text_to_speech.convert_with_timestamps(
            voice_id=VOICE, text=scene["text"], model_id=MODEL, language_code="fr",
            output_format="mp3_44100_128",
            request_options={"max_retries": 0},
            voice_settings=VoiceSettings(stability=0.35, similarity_boost=0.8, style=0.38, use_speaker_boost=True),
        )
        (out / f"{scene['id']}_raw.json").write_text(json.dumps(result.model_dump(by_alias=True), ensure_ascii=False))
        audio.write_bytes(base64.b64decode(result.audio_base_64))
        alignment = result.normalized_alignment or result.alignment
        duration = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio)]))
        meta.write_text(json.dumps({"hash": key, "duration": duration, "text": scene["text"],
                                   "alignment": alignment.model_dump() if alignment else None}, ensure_ascii=False, indent=2))
        print("GENERATED", scene["id"], round(duration, 2), "seconds", flush=True)


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser(); p.add_argument("--sample", action="store_true")
    args = p.parse_args()
    generate(SCENES[:1] if args.sample else SCENES + SHORT)