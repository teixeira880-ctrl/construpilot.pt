import asyncio
import os
import subprocess
from dotenv import load_dotenv

load_dotenv("/app/backend/.env")
from emergentintegrations.llm.openai import OpenAITextToSpeech  # noqa: E402

MEDIA = "/app/.media"
CLIPS = f"{MEDIA}/clips"
CAPS = f"{MEDIA}/caps"
os.makedirs(CLIPS, exist_ok=True)
os.makedirs(CAPS, exist_ok=True)
FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
OUT = "/app/frontend/public/construpilot_tiktok.mp4"

VO = {
    "a": "Tu veux rénover, mais tous les artisans te donnent des prix différents ?",
    "b": "Ne te fais plus avoir. Avec ConstruPilot, tu estimes le vrai prix de tes travaux "
         "instantanément, avec les vrais tarifs des matériaux.",
    "c": "C'est cent pour cent gratuit pour les particuliers. Fais ton estimation et reçois "
         "un devis direct. Lien dans la bio !",
}


async def tts():
    engine = OpenAITextToSpeech(api_key=os.getenv("EMERGENT_LLM_KEY"))
    for k, text in VO.items():
        out = f"{MEDIA}/vo_{k}.mp3"
        if os.path.exists(out):
            print("tts cached", k); continue
        audio = await engine.generate_speech(text=text, model="tts-1-hd", voice="onyx", speed=1.06)
        with open(out, "wb") as f:
            f.write(audio)
        print("tts", k, len(audio), "bytes")


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def write_cap(name, text):
    p = f"{CAPS}/{name}.txt"
    with open(p, "w") as f:
        f.write(text)
    return p


def clip(img, d, cap_text, out, zoom=False):
    capfile = write_cap(os.path.basename(out), cap_text)
    draw = (f"drawtext=fontfile={FONT}:textfile={capfile}:fontcolor=white:fontsize=60:"
            f"box=1:boxcolor=0x0A0D14@0.72:boxborderw=28:line_spacing=14:"
            f"x=(w-text_w)/2:y=h-560")
    base = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920"
    if zoom:
        frames = max(2, int(d * 30))
        vf = (f"{base},zoompan=z='min(zoom+0.0009,1.14)':d={frames}:"
              f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920:fps=30,{draw}")
    else:
        vf = f"{base},{draw}"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{d:.3f}", "-r", "30",
           "-vf", vf, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", out]
    subprocess.run(cmd, check=True, capture_output=True)
    print("clip", os.path.basename(out), f"{d:.2f}s")


def main():
    asyncio.run(tts())
    da = dur(f"{MEDIA}/vo_a.mp3")
    db = dur(f"{MEDIA}/vo_b.mp3")
    dc = dur(f"{MEDIA}/vo_c.mp3")
    print("durations", da, db, dc)

    F = f"{MEDIA}/frames"
    S = f"{MEDIA}/scenes"
    cap_hook = "Combien coûte VRAIMENT\ncette rénovation\nen 2026 ?"
    cap_calc = "Calcul automatique\nen 10 secondes"
    cap_price = "Le vrai prix,\ninstantanément"
    cap_free = "100% GRATUIT\npour les particuliers"
    cap_bio = "Lien dans la bio\npour tester"

    order = []
    # A — hook (AI couple)
    clip(f"{S}/cena2.jpg", da, cap_hook, f"{CLIPS}/s01.mp4", zoom=True); order.append("s01")
    # B — real app screens
    b_imgs = [(f"{F}/01_step0.png", cap_calc), (f"{F}/03_step2.png", cap_calc),
              (f"{F}/04_result_top.png", cap_price), (f"{F}/05_result_mid.png", cap_price)]
    bd = db / len(b_imgs)
    for i, (img, cap) in enumerate(b_imgs):
        clip(img, bd, cap, f"{CLIPS}/b{i}.mp4", zoom=False); order.append(f"b{i}")
    # C — free + bio (AI tech + artisan)
    cd = dc / 2
    clip(f"{S}/cena3.jpg", cd, cap_free, f"{CLIPS}/c01.mp4", zoom=True); order.append("c01")
    clip(f"{S}/cena1.jpg", cd, cap_bio, f"{CLIPS}/c02.mp4", zoom=True); order.append("c02")

    # concat video
    with open(f"{CLIPS}/list.txt", "w") as f:
        for n in order:
            f.write(f"file '{CLIPS}/{n}.mp4'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{CLIPS}/list.txt",
                    "-c", "copy", f"{MEDIA}/video_noaudio.mp4"], check=True, capture_output=True)
    # concat audio
    with open(f"{MEDIA}/alist.txt", "w") as f:
        for k in ["a", "b", "c"]:
            f.write(f"file '{MEDIA}/vo_{k}.mp3'\n")
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", f"{MEDIA}/alist.txt",
                    "-c:a", "aac", "-b:a", "192k", f"{MEDIA}/voice.m4a"], check=True, capture_output=True)
    # mux
    subprocess.run(["ffmpeg", "-y", "-i", f"{MEDIA}/video_noaudio.mp4", "-i", f"{MEDIA}/voice.m4a",
                    "-c:v", "copy", "-c:a", "aac", "-shortest", OUT], check=True, capture_output=True)
    print("TOTAL video dur", dur(OUT))
    print("OUTPUT", OUT, os.path.getsize(OUT), "bytes")


if __name__ == "__main__":
    main()
