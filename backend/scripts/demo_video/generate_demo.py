"""Gera o vídeo demo institucional ConstruPilot (PT-PT · ~180s · 1920x1080).

Pipeline:
  1. Narração PT-PT com gTTS (voz sintetizada Google, TLD .pt para PT-PT).
  2. Captura de screencasts do preview autenticado com Playwright (record_video).
  3. Trilha ambient gerada com ffmpeg (sines suaves) — sem dependência de CDN.
  4. Compositing final: concat vídeo + mix narração+música → MP4 H.264 30fps.

Saída: /app/frontend/public/construpilot-demo.mp4
"""
from __future__ import annotations
import asyncio
import subprocess
from pathlib import Path
from gtts import gTTS
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


def build_narration() -> list[Path]:
    files: list[Path] = []
    for name, dur, text in SEGMENTS:
        mp3 = AUD / f"{name}.mp3"
        gTTS(text=text, lang="pt", tld="pt", slow=False).save(str(mp3))
        # padding para bater a duração exata do segmento
        padded = AUD / f"{name}_pad.mp3"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(mp3),
            "-af", f"apad=whole_dur={dur}",
            "-t", str(dur), "-ar", "44100", "-ac", "2",
            str(padded)
        ], check=True, capture_output=True)
        files.append(padded)
    return files


# --------------------------------------------------------------------------
# 2) Screencasts (uma sessão Playwright, navegando pelos 9 flows)
# --------------------------------------------------------------------------
FLOWS = [
    # (path, dwell_seconds, [(sel_to_click_optional, wait_ms), ...])
    ("/",                       23, []),
    ("/login",                  20, []),   # login submete via código Python
    ("/photo",                  18, []),
    ("/biblioteca",             18, []),
    ("/calculadoras",           18, []),
    ("/plan-takeoff",           20, []),
    ("/orcamentos",             20, []),
    ("/dashboard",              18, []),
    ("/coach",                  18, []),
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
        for path, dwell, _ in FLOWS:
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

    # concat vídeos webm (transcode para mp4 30fps 1920x1080)
    # 1 - normalizar cada webm para mp4 1080p30
    norm_dir = TMP / "norm"
    norm_dir.mkdir(exist_ok=True)
    norm_files = []
    for i, v in enumerate(video_files):
        out = norm_dir / f"clip_{i:02d}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-i", str(v),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2:black,fps=30",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
            "-an", str(out)
        ], check=True, capture_output=True)
        norm_files.append(out)

    clips_txt = TMP / "clips.txt"
    clips_txt.write_text("\n".join(f"file '{p}'" for p in norm_files))
    silent = TMP / "silent.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clips_txt),
        "-c", "copy", str(silent)
    ], check=True, capture_output=True)

    # combinar vídeo + áudio final (limita ao total_dur)
    subprocess.run([
        "ffmpeg", "-y", "-i", str(silent), "-i", str(mixed),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-t", str(total_dur),
        "-movflags", "+faststart",
        str(OUT)
    ], check=True, capture_output=True)


# --------------------------------------------------------------------------
async def main() -> None:
    total = sum(dur for _, dur, _ in SEGMENTS)  # 198s
    print(f"→ Duração alvo: {total}s")
    print("→ Narração PT-PT (gTTS)…")
    nar_files = build_narration()
    print(f"  {len(nar_files)} segmentos gerados")
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
    print(f"✓ OK: {OUT} ({size/1024/1024:.2f} MB)")


if __name__ == "__main__":
    asyncio.run(main())
