"""Gera o vídeo demo institucional ConstruPilot (PT-PT · 1920x1080 · sincronia frame-perfect).

Pipeline:
  1. Gera TODO o áudio (ElevenLabs 'João - Narrator' PT-PT) e mede a duração real de cada segmento.
  2. Grava CADA cena Playwright separadamente, com duração = duração real do áudio correspondente.
  3. Constrói intro/outro slates ffmpeg com duração = duração do áudio de intro/outro.
  4. Compositing final: concat vídeo alinhado + concat áudio + mix música ambiente.

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
NORM = TMP / "norm"
for d in (AUD, CLIPS, NORM):
    d.mkdir(parents=True, exist_ok=True)

OUT = Path("/app/frontend/public/construpilot-demo.mp4")
OUT.parent.mkdir(parents=True, exist_ok=True)

FONT_BOLD = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
FONT_REG  = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"

# --------------------------------------------------------------------------
# SEGMENTOS — (nome, tipo, path_ou_None, texto)
#   tipo "slate"      → visual gerado com ffmpeg (intro/outro)
#   tipo "playwright" → visual capturado com Playwright em `path`
# --------------------------------------------------------------------------
SEGMENTS = [
    ("intro", "slate", None,
     "ConstruPilot. A plataforma portuguesa para orçamentar, medir e gerir obras. "
     "Da planta ao orçamento em minutos, com preços reais do mercado dois mil e vinte e seis."),

    ("b1", "playwright", "/",
     "Bem-vindo ao ConstruPilot. Uma biblioteca com trezentos e vinte e dois trabalhos "
     "compostos organizados em quarenta e três especialidades, com preços de mercado "
     "atualizados para dois mil e vinte e seis. Coeficientes regionais para Lisboa, Porto, "
     "Algarve e Interior. IVA seis, treze e vinte e três por cento. "
     "Tudo pensado para a construção civil em Portugal — de arquitetos a construtores, "
     "de particulares a empresas."),

    ("b2", "playwright", "/login",
     "Aceda à sua conta e comece de imediato. Cada utilizador nasce com uma biblioteca "
     "completa de trezentos e vinte e dois trabalhos preenchidos, prontos a usar. "
     "Sem necessidade de inserir preços manualmente. Do primeiro dia ao último, "
     "todos os dados sincronizados na nuvem."),

    ("b3", "playwright", "/photo",
     "Análise fotográfica com inteligência artificial. Envie uma foto da divisão "
     "e receba imediatamente a identificação de paredes, pavimento, teto, janelas e portas. "
     "Estado de conservação avaliado em segundos. Trabalhos recomendados listados por "
     "prioridade, com estimativa de custos incluída. "
     "Da fotografia ao orçamento, tudo em português europeu."),

    ("b4", "playwright", "/biblioteca",
     "Biblioteca partilhada ConstruPilot. Trezentos e vinte e dois trabalhos compostos "
     "com decomposição em materiais, mão de obra e equipamento. Três gamas de preços por "
     "trabalho: Económico, Standard e Premium. Fontes: Santander, CYPE, Multigam. "
     "Categoria especial para piscinas com sessenta e dois trabalhos exclusivos. "
     "Filtragem por especialidade, procura instantânea."),

    ("b5", "playwright", "/calculadoras",
     "Calculadoras profissionais integradas. Azulejos, betão, isolamento, "
     "divisórias em pladur. Insira as dimensões e receba resultados imediatos: "
     "número de peças, quantidades de materiais, custo estimado. Compare formatos, "
     "escolha o mais económico. Exporte para PDF ou adicione diretamente ao orçamento."),

    ("b6", "playwright", "/planta",
     "Estudo de plantas. Carregue plantas em DWG, DXF ou PDF. Meça áreas, comprimentos "
     "e volumes com precisão. Compare versões, identifique diferenças. Estimativas por "
     "divisão geradas automaticamente com base na biblioteca de preços. "
     "Ideal para arquitetos e gabinetes de engenharia."),

    ("b7", "playwright", "/orcamentos",
     "Crie orçamentos profissionais em minutos. Adicione trabalhos da biblioteca, "
     "ajuste quantidades, aplique coeficientes regionais. Assinatura eletrónica pelo "
     "cliente, envio automático por email, recibo em PDF gerado no ato. "
     "Estatísticas em tempo real do seu volume de negócio assinado."),

    ("b8", "playwright", "/dashboard",
     "Dashboard executivo. Painel único com todos os indicadores: orçamentos em curso, "
     "faturas emitidas, volume de negócio assinado, notificações e alertas. "
     "CRM integrado, gestão de clientes e projetos. "
     "Tudo à distância de um clique, no seu computador ou telemóvel."),

    ("b9", "playwright", "/coach",
     "Coach de obras com inteligência artificial. Um assistente virtual em português, "
     "disponível vinte e quatro horas por dia, sete dias por semana. "
     "Tire dúvidas técnicas, receba conselhos sobre materiais, cumprimento de normas "
     "e boas práticas. Como ter um engenheiro consigo em cada obra."),

    ("outro", "slate", None,
     "ConstruPilot. Da planta ao orçamento em minutos. "
     "Descubra em construpilot ponto p t. A construção inteligente começa aqui."),
]

# Buffer visual/áudio (segundos) por cena para respiração natural + evitar clipping
VIDEO_TAIL = 0.35  # cauda visual extra a gravar (freeze/scroll) antes do corte exato


# ==========================================================================
# TTS · ElevenLabs (João - Narrator PT-PT europeu)
# ==========================================================================
def _tts_bytes_elevenlabs(text: str) -> bytes:
    """ElevenLabs PT-PT nativo — voz 'João - Narrator'."""
    from elevenlabs.client import ElevenLabs
    from elevenlabs import VoiceSettings
    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    stream = client.text_to_speech.convert(
        voice_id="ID3DiXGPB7uwug5tZ3FB",
        model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128",
        text=text,
        voice_settings=VoiceSettings(
            stability=0.40, similarity_boost=0.80, style=0.40, use_speaker_boost=True,
        ),
    )
    return b"".join(chunk for chunk in stream if chunk)


def _probe_duration(path: Path) -> float:
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(r.stdout.strip())


def build_narration() -> tuple[list[Path], list[float]]:
    """Gera cada segmento como WAV (sem encoder delay do LAME), adiciona 250ms de
    silêncio no fim para respiração natural, e mede a duração real.
    Devolve (paths_wav, durations)."""
    files: list[Path] = []
    durs: list[float] = []
    for name, _kind, _path, text in SEGMENTS:
        raw_mp3 = AUD / f"{name}_raw.mp3"
        wav = AUD / f"{name}.wav"
        raw_mp3.write_bytes(_tts_bytes_elevenlabs(text))
        # decode mp3 → WAV 44.1kHz stereo + 250ms de silêncio no fim
        subprocess.run([
            "ffmpeg", "-y", "-i", str(raw_mp3),
            "-af", "apad=pad_dur=0.25",
            "-ar", "44100", "-ac", "2",
            "-c:a", "pcm_s16le",
            str(wav),
        ], check=True, capture_output=True)
        d = _probe_duration(wav)
        files.append(wav)
        durs.append(d)
        print(f"  · {name:>5s} · {d:6.2f}s · '{text[:60]}...'")
    return files, durs


# ==========================================================================
# Playwright · uma cena por segmento web · duração = duração do áudio
# ==========================================================================
async def capture_scenes(target: dict[str, float]) -> dict[str, Path]:
    """`target` = {seg_name: dur_seconds} para cenas 'playwright' apenas.
    Devolve {seg_name: Path(webm)}."""
    results: dict[str, Path] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox"],
        )

        # -- 1) Auth setup (uma vez) ------------------------------------
        ctx0 = await browser.new_context(viewport={"width": 1920, "height": 1080})
        page0 = await ctx0.new_page()
        try:
            await page0.goto(BASE + "/login", wait_until="networkidle", timeout=25000)
            await page0.evaluate(
                "localStorage.setItem('onboarding_skipped','1');"
                "localStorage.setItem('cookies_accepted','1');"
            )
            await page0.fill('[data-testid="login-email-input"]', EMAIL)
            await page0.fill('[data-testid="login-password-input"]', PASSWORD)
            await page0.click('button[type="submit"]')
            await page0.wait_for_timeout(4500)
        except Exception as e:
            print(f"  [auth] warning: {type(e).__name__}: {str(e)[:120]}")
        storage = await ctx0.storage_state()
        await ctx0.close()

        # -- 2) Grava cada cena -----------------------------------------
        for name, kind, path, _text in SEGMENTS:
            if kind != "playwright":
                continue
            dur = target[name] + VIDEO_TAIL
            scene_dir = CLIPS / name
            for f in scene_dir.glob("*.webm"):
                f.unlink()
            scene_dir.mkdir(parents=True, exist_ok=True)
            # b2 (página de login) sem sessão para mostrar o form; restante autenticada
            state = None if name == "b2" else storage
            ctx = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                record_video_dir=str(scene_dir),
                record_video_size={"width": 1920, "height": 1080},
                storage_state=state,
            )
            page = await ctx.new_page()
            try:
                await page.evaluate(
                    "localStorage.setItem('onboarding_skipped','1');"
                    "localStorage.setItem('cookies_accepted','1');"
                )
            except Exception:
                pass
            try:
                await page.goto(BASE + path, wait_until="networkidle", timeout=20000)
            except Exception:
                pass

            # scroll suave para adicionar movimento durante toda a cena
            target_ms = int(dur * 1000)
            step_ms = 1400
            elapsed = 0
            while elapsed + step_ms < target_ms:
                try:
                    await page.mouse.wheel(0, 220)
                except Exception:
                    pass
                await page.wait_for_timeout(step_ms)
                elapsed += step_ms
            if target_ms - elapsed > 0:
                await page.wait_for_timeout(target_ms - elapsed)

            await ctx.close()  # finaliza o webm
            webms = sorted(scene_dir.glob("*.webm"))
            if not webms:
                raise RuntimeError(f"Cena {name}: webm não gerado.")
            results[name] = webms[0]
            probed = _probe_duration(webms[0])
            print(f"  · {name} · {path:15s} · pedido {dur:5.2f}s · gravado {probed:5.2f}s")

        await browser.close()
    return results


# ==========================================================================
# Trilha ambient (ffmpeg sines)
# ==========================================================================
def build_bg_music(total_seconds: float) -> Path:
    bg = TMP / "bg_music.mp3"
    t = max(1.0, total_seconds)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"sine=frequency=196:duration={t:.3f}",
        "-f", "lavfi", "-i", f"sine=frequency=294:duration={t:.3f}",
        "-f", "lavfi", "-i", f"sine=frequency=392:duration={t:.3f}",
        "-filter_complex",
        "[0]volume=0.025[a];[1]volume=0.018[b];[2]volume=0.012[c];"
        "[a][b][c]amix=inputs=3:normalize=0[m];[m]afade=t=in:st=0:d=2,"
        f"afade=t=out:st={max(0.0,t-2):.3f}:d=2[out]",
        "-map", "[out]", "-ar", "44100", "-ac", "2", "-b:a", "128k",
        str(bg),
    ], check=True, capture_output=True)
    return bg


# ==========================================================================
# Compositing final · vídeo (11 clips normalizados) + áudio (11 segmentos)
# ==========================================================================
def make_slate(name: str, dur: float, primary_text: str,
               secondary_text: str = "", tertiary_text: str = "") -> Path:
    """Slate para intro/outro. Dur EXATA em segundos."""
    out = NORM / f"clip_{name}.mp4"
    filters = [
        (f"drawtext=text='{primary_text}':fontcolor=0x10b981:fontsize=140:"
         f"x=(w-text_w)/2:y=(h-text_h)/2-{60 if secondary_text else 0}:"
         f"fontfile={FONT_BOLD}:alpha='if(lt(t,0.5),t*2,1)'"),
    ]
    if secondary_text:
        filters.append(
            f"drawtext=text='{secondary_text}':fontcolor=white:fontsize=48:"
            f"x=(w-text_w)/2:y=(h-text_h)/2+70:fontfile={FONT_REG}:"
            f"alpha='if(lt(t,0.8),0,if(lt(t,1.3),(t-0.8)*2,1))'"
        )
    if tertiary_text:
        filters.append(
            f"drawtext=text='{tertiary_text}':fontcolor=0x10b981:fontsize=42:"
            f"x=(w-text_w)/2:y=(h-text_h)/2+150:fontfile={FONT_BOLD}:"
            f"alpha='if(lt(t,1.3),0,if(lt(t,1.8),(t-1.3)*2,1))'"
        )
    vf = ",".join(filters)
    subprocess.run([
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"color=c=0x0f172a:s=1920x1080:d={dur:.3f}:r=30",
        "-vf", vf,
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
        "-pix_fmt", "yuv420p", "-t", f"{dur:.3f}", "-an", str(out),
    ], check=True, capture_output=True)
    return out


def normalize_webm(webm: Path, dur: float, tag: str) -> Path:
    """Escala/pad para 1920x1080@30fps, corta EXATAMENTE em `dur`s.
    Se o webm for mais curto, faz freeze do último frame (tpad clone)."""
    out = NORM / f"clip_{tag}.mp4"
    # tpad estende com clone; -t garante corte exato
    subprocess.run([
        "ffmpeg", "-y", "-i", str(webm),
        "-vf",
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,fps=30,"
        f"tpad=stop_mode=clone:stop_duration=5",
        "-t", f"{dur:.3f}",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-pix_fmt", "yuv420p", "-an", str(out),
    ], check=True, capture_output=True)
    return out


def compose(narration_files: list[Path], seg_durs: list[float],
            web_webms: dict[str, Path]) -> tuple[float, float]:
    # ---- 1) Vídeo: gerar 11 clips normalizados ----
    print("→ Normalização de clips (frame-perfect)…")
    norm_clips: list[Path] = []
    for i, (name, kind, path, text) in enumerate(SEGMENTS):
        dur = seg_durs[i]
        if kind == "slate":
            if name == "intro":
                clip = make_slate("intro", dur, "ConstruPilot")
            else:
                clip = make_slate(
                    "outro", dur,
                    "ConstruPilot",
                    "Da planta ao orcamento em minutos",
                    "construpilot.pt",
                )
        else:
            clip = normalize_webm(web_webms[name], dur, name)
        norm_clips.append(clip)
        d = _probe_duration(clip)
        print(f"  · clip {name:>5s} · alvo {dur:5.2f}s · ffprobe {d:5.2f}s (Δ={d-dur:+.3f}s)")

    # ---- 2) Concat vídeo ----
    print("→ Concat vídeo…")
    clips_txt = TMP / "clips.txt"
    clips_txt.write_text("\n".join(f"file '{p}'" for p in norm_clips))
    silent = TMP / "silent.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clips_txt),
        "-c", "copy", str(silent),
    ], check=True, capture_output=True)
    video_dur = _probe_duration(silent)

    # ---- 3) Concat áudio (todos os 11 segmentos WAV em sequência, sem encoder delay) ----
    print("→ Concat narração (WAV → sem drift)…")
    audios_txt = TMP / "audios.txt"
    audios_txt.write_text("\n".join(f"file '{p}'" for p in narration_files))
    narration = TMP / "narration.wav"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(audios_txt),
        "-c:a", "pcm_s16le", "-ar", "44100", "-ac", "2", str(narration),
    ], check=True, capture_output=True)
    narration_dur = _probe_duration(narration)

    # ---- 4) Trilha ambient com a mesma duração ----
    bg = build_bg_music(video_dur)

    # ---- 5) Mix narração + música ambiente (WAV → AAC final) ----
    print("→ Mix narração + música…")
    mixed = TMP / "mixed.m4a"
    subprocess.run([
        "ffmpeg", "-y", "-i", str(narration), "-i", str(bg),
        "-filter_complex",
        "[1:a]volume=0.1[bg];[0:a][bg]amix=inputs=2:duration=first:dropout_transition=0",
        "-c:a", "aac", "-b:a", "192k", str(mixed),
    ], check=True, capture_output=True)

    # ---- 6) Merge vídeo + áudio ----
    print("→ Merge final…")
    subprocess.run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(mixed),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-map", "0:v:0", "-map", "1:a:0",
        "-movflags", "+faststart",
        str(OUT),
    ], check=True, capture_output=True)

    return video_dur, narration_dur


# ==========================================================================
async def main() -> None:
    print("→ Narração PT-PT (João - Narrator)…")
    nar_files, seg_durs = build_narration()
    total_audio = sum(seg_durs)
    print(f"  Total narração: {total_audio:.2f}s · {len(nar_files)} segmentos")

    web_targets = {
        name: seg_durs[i]
        for i, (name, kind, _p, _t) in enumerate(SEGMENTS)
        if kind == "playwright"
    }
    print(f"→ Screencasts Playwright ({len(web_targets)} cenas, cada uma = duração do áudio)…")
    web_webms = await capture_scenes(web_targets)

    print("→ Compositing final ffmpeg…")
    video_dur, narration_dur = compose(nar_files, seg_durs, web_webms)

    size_mb = OUT.stat().st_size / 1024 / 1024
    delta = video_dur - narration_dur
    print("=" * 70)
    print(f"✓ OK: {OUT} ({size_mb:.2f} MB)")
    print(f"  video_dur    = {video_dur:.3f}s")
    print(f"  audio_dur    = {narration_dur:.3f}s")
    print(f"  sync delta   = {delta*1000:+.0f} ms")
    print(f"  segmentos    = {len(seg_durs)}")
    for i, (name, kind, path, _t) in enumerate(SEGMENTS):
        print(f"    [{i:02d}] {name:>5s}  {seg_durs[i]:6.2f}s  {kind:10s}  {path or '(slate)'}")


if __name__ == "__main__":
    asyncio.run(main())
