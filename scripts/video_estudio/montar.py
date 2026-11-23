"""Monta o vídeo do Estúdio de Projeto: capturas reais + legenda (o texto da narração). Uma cena = um ficheiro mp4.
Se existir audio/<id>.mp3 a duração da cena segue o áudio; caso contrário é estimada pelo comprimento do texto."""
import json, re, subprocess, sys, textwrap
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

B = Path("/home/claude/video")
CAP, OUT, AUD = B / "cap", B / "cenas", B / "audio"
OUT.mkdir(exist_ok=True)
W, H, FPS = 1280, 720, 30
F_T = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 21)
F_X = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 22)
F_G = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 54)
VERDE, CREME = (31, 122, 92), (245, 240, 232)
ENC = ["-c:v", "libx264", "-crf", "19", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-r", str(FPS)]


def dur_audio(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    return float(r.stdout.strip())


def quadro(img_path, titulo, frase, n, total):
    im = Image.open(img_path).convert("RGB").resize((W, H), Image.LANCZOS) if img_path else Image.new("RGB", (W, H), CREME)
    d = ImageDraw.Draw(im, "RGBA")
    linhas = textwrap.wrap(frase, 92)[:3]
    alt = 46 + 30 * len(linhas)
    d.rectangle([0, H - alt, W, H], fill=(20, 28, 34, 225))
    d.rectangle([0, H - alt, 8, H], fill=VERDE + (255,))
    d.text((28, H - alt + 10), f"{n}/{total} · {titulo}", font=F_T, fill=(120, 214, 178, 255))
    for i, l in enumerate(linhas):
        d.text((28, H - alt + 40 + 30 * i), l, font=F_X, fill=(255, 255, 255, 255))
    return im


def cartao(titulo, sub):
    im = Image.new("RGB", (W, H), (20, 28, 34))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, W, 10], fill=VERDE)
    d.text((W / 2, H / 2 - 40), titulo, font=F_G, fill=(255, 255, 255), anchor="mm")
    d.text((W / 2, H / 2 + 30), sub, font=F_X, fill=(120, 214, 178), anchor="mm")
    return im


cenas = json.load(open(B / "narracao.json", encoding="utf-8"))
# duração de cada faixa ElevenLabs (mp3 a 128 kbit/s constantes: bytes / 16000)
BYTES = {"01_intro": 259595, "02_desenhar": 336082, "03_vaos": 214874, "04_mobiliario": 256670, "05_materiais": 205261, "06_3d": 246221,
         "07_visita": 113310, "08_alcados": 118325, "09_medicoes": 181019, "10_exportar": 235772, "11_fim": 81127}
DUR = {k_: v_ / 16000.0 for k_, v_ in BYTES.items()}
inicios = []
lista, total_s = [], 0.0
for k, c in enumerate(cenas, 1):
    imgs = sorted(CAP.glob(c["id"][:2] + "*.jpg"))
    if c["id"].startswith("02"):
        imgs = [CAP / "02a.jpg", CAP / "02c.jpg", CAP / "02b.jpg"]
    frases = [f.strip() for f in re.split(r"(?<=[.!?])\s+", c["texto"]) if f.strip()]
    mp3 = AUD / f"{c['id']}.mp3"
    dur = dur_audio(mp3) + 0.5 if mp3.exists() else (DUR[c["id"]] + 0.7 if c["id"] in DUR else len(c["texto"]) / 14.0 + 1.0)
    inicios.append((c["id"], round(total_s + (2.5 if k == 1 else 0.0) + 0.15, 3)))
    pesos = [len(f) for f in frases]
    partes = []
    for j, f in enumerate(frases):
        img = imgs[min(len(imgs) - 1, j * len(imgs) // len(frases))] if imgs else None
        partes.append((quadro(img, c["titulo"], f, k, len(cenas)), dur * pesos[j] / sum(pesos)))
    if k == 1:
        partes.insert(0, (cartao("Estúdio de Projeto", "ConstruPilot · como se trabalha"), 2.5))
    if k == len(cenas):
        partes.append((cartao("ConstruPilot", "Estúdio de Projeto · construpilot.pt"), 2.5))
    # uma cena = concat de imagens paradas, num só ficheiro
    txt = B / "cenas" / f"{c['id']}.txt"
    linhas = []
    for j, (im, d_) in enumerate(partes):
        p = OUT / f"{c['id']}_{j}.png"
        im.save(p)
        linhas += [f"file '{p}'", f"duration {d_:.3f}"]
    linhas.append(f"file '{p}'")
    txt.write_text("\n".join(linhas))
    dt = sum(d_ for _, d_ in partes)
    tmp, fim = OUT / f"{c['id']}.tmp.mp4", OUT / f"{c['id']}.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(txt)]
    if mp3.exists():
        atraso = 2500 if k == 1 else 0
        cmd += ["-i", str(mp3), "-af", f"adelay={atraso}:all=1,apad", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-ac", "2"]
    else:
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-c:a", "aac", "-b:a", "96k"]
    cmd += ["-vf", f"fps={FPS},format=yuv420p", *ENC, "-t", f"{dt:.3f}", str(tmp)]
    subprocess.run(cmd, check=True)
    tmp.rename(fim)
    lista.append(f"file '{fim}'")
    total_s += dt
    print(c["id"], len(imgs), "capturas", f"{dt:.1f}s", "áudio" if mp3.exists() else "sem áudio")
(B / "lista.txt").write_text("\n".join(lista))
final = B / (sys.argv[1] if len(sys.argv) > 1 else "ConstruPilot-Estudio-de-Projeto.mp4")
subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(B / "lista.txt"), "-c", "copy", "-movflags", "+faststart", str(final)], check=True)
(B / "inicios.json").write_text(json.dumps(inicios))
print("FINAL", final, f"{total_s:.1f}s", inicios)
