"""Gera o vídeo demo institucional ConstruPilot (PT-PT · ~180s · 1920x1080).

Pipeline:
  1. Narração PT-PT com gTTS (voz sintetizada Google, TLD .pt para PT-PT).
  2. Captura de screencasts do preview autenticado com Playwright (record_video).
  3. Trilha ambient gerada com ffmpeg (sines suaves) — sem dependência de CDN.
  4. Compositing final: concat vídeo + mix narração+música → MP4 H.264 30fps.

Saída: /app/frontend/public/construpilot-demo.mp4
"""
from __future__ import annotations
import os
import asyncio
import subprocess
from pathlib import Path
from dotenv import load_dotenv
load_dotenv("/app/backend/.env")
from playwright.async_api import async_playwright

BASE = "https://construpilot-recon.preview.emergentagent.com"
EMAIL = "info@construpilot.pt"
PASSWORD = "uFuBb6Q5h1QUxCmc"

TMP = Path("/tmp/demo_video")
AUD = TMP / "audio"
CLIPS = TMP / "clips"
for d in (AUD, CLIPS):
    d.mkdir(parents=True, exist_ok=True)

OUT = Path("/app/frontend/public/construpilot-demo.mp4")
OUT.parent.mkdir(parents=True, exist_ok=True)

# --------------------------------------------------------------------------
# 1) Narração
# --------------------------------------------------------------------------
SEGMENTS = [
    ("intro", 5, "ConstruPilot. Da planta ao orçamento em minutos."),
    ("b1", 18,
     "Somos uma plataforma 100 por cento portuguesa para construção civil. "
     "Trezentos e vinte e dois trabalhos compostos, quarenta e três especialidades, "
     "sete mil linhas de composição — tudo com preços de mercado dois mil e vinte e seis."),
    ("b2", 20,
     "Descreva o seu projeto por voz, em português. A ConstruPilot transcreve "
     "a sua descrição e transforma-a num orçamento detalhado em segundos, "
     "com linhas orçamentadas pela biblioteca portuguesa."),
    ("b3", 18,
     "Fotografe uma divisão. A inteligência artificial identifica paredes, pavimento, "
     "teto, janelas e sanitários — e propõe automaticamente os trabalhos recomendados."),
    ("b4", 18,
     "A biblioteca partilhada inclui piscinas em betão, canalização, pladur, "
     "isolamento, cobertura, e muito mais. Filtro por especialidade, três gamas de "
     "preços e coeficientes regionais para Lisboa, Porto, Algarve e Interior."),
    ("b5", 18,
     "As calculadoras cobrem azulejos, pladur, betão e isolamento. Introduza a área, "
     "escolha o tipo de assentamento e receba resultados em português."),
    ("b6", 20,
     "Estude plantas em DWG, DXF ou PDF. A ConstruPilot mede paredes, vãos e "
     "sanitários automaticamente e aplica preços da biblioteca ao seu estudo."),
    ("b7", 20,
     "Crie um orçamento profissional em minutos: linhas com o seu preço, IVA seis, "
     "treze ou vinte e três por cento, assinatura eletrónica e envio por email."),
    ("b8", 18,
     "O painel apresenta o volume de negócio assinado, faturado e por especialidade. "
     "Um CRM completo — clientes, obras, propostas e portal do cliente."),
    ("b9", 18,
     "O Coach de obras responde em português, sempre. Dúvidas sobre licenças, IVA, "
     "materiais ou execução — resposta imediata, sem sair da aplicação."),
    ("outro", 7, "ConstruPilot ponto p t. Construção inteligente, em português."),
]


FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"


def _tts_bytes_sync(text: str) -> bytes:
    from gtts import gTTS
    import io
    buf = io.BytesIO()
    gTTS(text=text, lang="pt", tld="pt", slow=False).write_to_fp(buf)
    return buf.getvalue()


def _tts_bytes_elevenlabs(text: str) -> bytes:
    """ElevenLabs PT-PT nativo — voz 'João - Narrator'
    (serene and expressive male narrator voice).
    accent european · locale pt-PT · multilingual v2."""
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    stream = client.text_to_speech.convert(
        voice_id="ID3DiXGPB7uwug5tZ3FB",           # João - Narrator · PT-PT
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        text=text,
        voice_settings=VoiceSettings(
            stability=0.40, similarity_boost=0.80, style=0.40, use_speaker_boost=True,
        ),
    )
    return b"".join(chunk for chunk in stream if chunk)


async def _tts_bytes_openai(text: str) -> bytes:
    from emergentintegrations.llm.openai import OpenAITextToSpeech
    tts = OpenAITextToSpeech(api_key=os.environ["EMERGENT_LLM_KEY"])
    return await tts.generate_speech(
        text=text, model="tts-1-hd", voice="onyx",
        response_format="mp3", speed=1.05,
    )


async def build_narration() -> tuple[list[Path], str]:
    files: list[Path] = []
    provider = "elevenlabs_joao_narrator_pt_pt"
    for name, dur, text in SEGMENTS:
        mp3 = AUD / f"{name}.mp3"
        data: bytes | None = None
        if provider == "elevenlabs_joao_narrator_pt_pt":
            try:
                data = _tts_bytes_elevenlabs(text)
            except Exception as e:
                print(f"  [tts] ElevenLabs falhou ({type(e).__name__}) — fallback OpenAI onyx. {str(e)[:100]}")
                provider = "openai_onyx (fallback)"
        if data is None and "openai" in provider:
            try:
                data = await _tts_bytes_openai(text)
            except Exception as e:
                print(f"  [tts] OpenAI falhou ({type(e).__name__}) — fallback gTTS. {str(e)[:80]}")
                provider = "gtts_pt (fallback)"
        if data is None:
            data = _tts_bytes_sync(text)
        mp3.write_bytes(data)
        padded = AUD / f"{name}_pad.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp3),
            "-af", f"apad=whole_dur={dur}",
            "-t", str(dur), "-ar", "44100", "-ac", "2",
            str(padded)
        ], check=True, capture_output=True)
        files.append(padded)
    return files, provider


# --------------------------------------------------------------------------
# 2) Screencasts (uma sessão Playwright, navegando pelos 9 flows)
# --------------------------------------------------------------------------
FLOWS = [
    # (path, dwell_seconds)
    ("/",             23),
    ("/login",        20),
    ("/photo",        18),
    ("/biblioteca",   18),
    ("/calculadoras", 18),
    ("/planta",       20),   # antes: /plan-takeoff (404) → corrigido
    ("/orcamentos",   20),
    ("/dashboard",    18),
    ("/coach",        18),
]


async def capture_screencasts() -> list[Path]:
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path="/usr/bin/google-chrome", args=["--no-sandbox"],
        )
        ctx = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            record_video_dir=str(CLIPS),
            record_video_size={"width": 1920, "height": 1080},
        )
        page = await ctx.new_page()

        # setup — flag skip do tour + cookies
        await page.goto(BASE + "/login", wait_until="networkidle", timeout=25000)
        await page.evaluate(
            "localStorage.setItem('onboarding_skipped','1');"
            "localStorage.setItem('cookies_accepted','1');"
        )
        # login
        try:
            await page.fill('[data-testid="login-email-input"]', EMAIL)
            await page.fill('[data-testid="login-password-input"]', PASSWORD)
            await page.click('button[type="submit"]')
            await page.wait_for_timeout(4500)
        except Exception:
            pass

        # navegar pelos flows (na MESMA página → gera 1 único vídeo do context)
        for path, dwell in FLOWS:
            try:
                await page.goto(BASE + path, wait_until="networkidle", timeout=20000)
            except Exception:
                pass
            await page.wait_for_timeout(dwell * 1000)

        # scroll leve na landing final para dar movimento
        try:
            await page.goto(BASE + "/", wait_until="networkidle", timeout=15000)
            for _ in range(4):
                await page.mouse.wheel(0, 300)
                await page.wait_for_timeout(1500)
        except Exception:
            pass

        await ctx.close()
        await browser.close()

    return sorted(CLIPS.glob("*.webm"))


# --------------------------------------------------------------------------
# 3) Trilha ambient (ffmpeg sines)
# --------------------------------------------------------------------------
def build_bg_music(total_seconds: int) -> Path:
    bg = TMP / "bg_music.mp3"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=196:duration={total_seconds}",  # sol
        "-f", "lavfi", "-i", f"sine=frequency=294:duration={total_seconds}",  # ré
        "-f", "lavfi", "-i", f"sine=frequency=392:duration={total_seconds}",  # sol oitava
        "-filter_complex",
        "[0]volume=0.025[a];[1]volume=0.018[b];[2]volume=0.012[c];"
        "[a][b][c]amix=inputs=3:normalize=0[m];[m]afade=t=in:st=0:d=2,"
        f"afade=t=out:st={total_seconds-2}:d=2[out]",
        "-map", "[out]", "-ar", "44100", "-ac", "2", "-b:a", "128k",
        str(bg)
    ], check=True, capture_output=True)
    return bg


# --------------------------------------------------------------------------
# 4) Compositing final
# --------------------------------------------------------------------------
def compose(narration_files: list[Path], video_files: list[Path], bg_music: Path,
            total_dur: int) -> None:
    # concat narração
    audios_txt = TMP / "audios.txt"
    audios_txt.write_text("\n".join(f"file '{p}'" for p in narration_files))
    narration = TMP / "narration.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audios_txt),
        "-c:a", "libmp3lame", "-ar", "44100", "-ac", "2", str(narration)
    ], check=True, capture_output=True)

    # mix narração + música (-20dB música)
    mixed = TMP / "mixed_audio.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(narration), "-i", str(bg_music),
        "-filter_complex",
        "[1:a]volume=0.1[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0",
        "-c:a", "libmp3lame", "-b:a", "192k", str(mixed)
    ], check=True, capture_output=True)

    # concat vídeos webm (transcode para mp4 30fps 1920x1080) + intro/outro
    norm_dir = TMP / "norm"
    norm_dir.mkdir(exist_ok=True)
    norm_files = []
    # ---- INTRO 2s ----
    intro = TMP / "intro.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x0f172a:s=1920x1080:d=2:r=30",
        "-vf",
        f"drawtext=text='ConstruPilot':fontcolor=0x10b981:fontsize=140:"
        f"x=(w-text_w)/2:y=(h-text_h)/2:fontfile={FONT_BOLD}:"
        f"alpha='if(lt(t,0.5),t*2,1)'",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-t", "2", "-an", str(intro),
    ], check=True, capture_output=True)
    norm_files.append(intro)

    # ---- Screencasts normalizados ----
    for i, v in enumerate(video_files):
        out = norm_dir / f"clip_{i:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(v),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,fps=30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-pix_fmt", "yuv420p", "-an", str(out)
        ], check=True, capture_output=True)
        norm_files.append(out)

    # ---- OUTRO 3s ----
    outro = TMP / "outro.mp4"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=0x0f172a:s=1920x1080:d=3:r=30",
        "-vf",
        (f"drawtext=text='ConstruPilot':fontcolor=0x10b981:fontsize=120:"
         f"x=(w-text_w)/2:y=(h-text_h)/2-140:fontfile={FONT_BOLD}:"
         f"alpha='if(lt(t,0.5),t*2,1)',"
         f"drawtext=text='Da planta ao orcamento em minutos':fontcolor=white:fontsize=48:"
         f"x=(w-text_w)/2:y=(h-text_h)/2+20:fontfile={FONT_REG}:"
         f"alpha='if(lt(t,1),0,if(lt(t,1.5),(t-1)*2,1))',"
         f"drawtext=text='construpilot.pt':fontcolor=0x10b981:fontsize=42:"
         f"x=(w-text_w)/2:y=(h-text_h)/2+110:fontfile={FONT_BOLD}:"
         f"alpha='if(lt(t,1.5),0,if(lt(t,2),(t-1.5)*2,1))'"),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-t", "3", "-an", str(outro),
    ], check=True, capture_output=True)
    norm_files.append(outro)

    clips_txt = TMP / "clips.txt"
    clips_txt.write_text("\n".join(f"file '{p}'" for p in norm_files))
    silent = TMP / "silent.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clips_txt),
        "-c", "copy", str(silent)
    ], check=True, capture_output=True)

    # combinar vídeo + áudio final (intro 2s antes → shift áudio; outro 3s no fim → audio termina antes)
    # estratégia simples: prepend 2s de silêncio à mixed antes de merge
    mixed_shift = TMP / "mixed_shift.mp3"
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-t", "2", "-i", "anullsrc=r=44100:cl=stereo",
        "-i", str(mixed),
        "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
        "-map", "[out]", "-c:a", "libmp3lame", "-b:a", "192k",
        str(mixed_shift)
    ], check=True, capture_output=True)

    final_dur = 2 + total_dur + 3
    subprocess.run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(mixed_shift),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(final_dur),
        "-movflags", "+faststart",
        str(OUT)
    ], check=True, capture_output=True)


# --------------------------------------------------------------------------
async def main() -> None:
    total = sum(dur for _, dur, _ in SEGMENTS)
    print(f"→ Duração alvo: {total}s")
    print("→ Narração PT-PT…")
    nar_files, tts_used = await build_narration()
    print(f"  {len(nar_files)} segmentos gerados · TTS: {tts_used}")
    print("→ Trilha ambient (ffmpeg sines)…")
    bg = build_bg_music(total)
    print("→ Screencasts Playwright…")
    vids = await capture_screencasts()
    print(f"  {len(vids)} clips capturados")
    if not vids:
        raise RuntimeError("Nenhum clip capturado — abortar.")
    print("→ Compositing final ffmpeg…")
    compose(nar_files, vids, bg, total)
    size = OUT.stat().st_size
    print(f"✓ OK: {OUT} ({size/1024/1024:.2f} MB) · TTS={tts_used}")


if __name__ == "__main__":
    asyncio.run(main())
