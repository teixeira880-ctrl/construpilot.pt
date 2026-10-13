"""Génère la narration FR (ElevenLabs) + assemble la vidéo de démo ConstruPilot."""
import json
import os
import subprocess
from pathlib import Path

from elevenlabs.client import ElevenLabs

API_KEY = os.environ.get("ELEVENLABS_API_KEY") or "sk_b4103bf3c2bcd9560f3d700dd20ae09e33af857cfa8b18e3"
VOICE_ID = "6DEjyaHWnTHsvXM5Byys"  # Hugo - Deep French Storyteller (fr)
OUT = Path("/app/frontend/public/demo")
AUD = OUT / "audio"
AUD.mkdir(parents=True, exist_ok=True)

CHAPTERS = [
    ("home", "home.png", "Bienvenue sur ConstruPilot, la plateforme de chiffrage et de métré pour les professionnels du bâtiment. En quelques minutes, estimez, métrez et éditez vos devis, avec des calculs cent pour cent déterministes.", "Bienvenue sur ConstruPilot"),
    ("estimation", "estimation.png", "Décrivez votre projet en langage naturel. ConstruPilot génère une estimation détaillée, poste par poste, et un aperçu du plan en trois dimensions, avant même de contacter un artisan.", "Estimation instantanée"),
    ("metre", "metre.png", "Importez vos plans en PDF, image ou DXF, puis mesurez directement à l'écran : surfaces, périmètres et linéaires. Les ouvertures sont déduites automatiquement, et le métré net part vers votre devis.", "Métré sur plan"),
    ("calculateurs", "calculateurs.png", "Les calculateurs de matériaux vous donnent les quantités exactes, marges incluses : peinture, carrelage, placo, béton ou isolation, avec pertes de pose et conditionnements.", "Calculateurs de matériaux"),
    ("escaliers", "escaliers.png", "Le module escaliers calcule votre ouvrage béton de façon déterministe : optimiseur de solutions, contrôle des normes DTU trente-six trois, analyse du béton armé, et dossier PDF coté, prêt pour le chantier.", "Calcul d'escaliers béton"),
    ("plan", "plan.png", "Regroupez plusieurs plans d'un même chantier, fondations, rez-de-chaussée et étages, en un projet multi-niveaux, avec métré et chiffrage consolidés, puis générez un devis global en un seul clic.", "Projets multi-niveaux"),
    ("pro", "pro.png", "Passez à l'offre Pro : sept jours d'essai gratuit, puis un abonnement clair et sans engagement. Devis clients, bibliothèque de prix et outils avancés, au service de votre rentabilité.", "L'offre Pro"),
    ("dashboard", "dashboard.png", "Votre tableau de bord centralise chantiers, devis et factures. ConstruPilot vous fait gagner du temps à chaque étape, du premier chiffrage jusqu'à la facturation finale.", "Votre tableau de bord"),
]

client = ElevenLabs(api_key=API_KEY)


def synth(text, path):
    resp = client.text_to_speech.convert(
        voice_id=VOICE_ID, model_id="eleven_multilingual_v2",
        output_format="mp3_44100_128", text=text)
    with open(path, "wb") as f:
        for ch in resp:
            if ch:
                f.write(ch)


def duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def main():
    manifest = []
    segs = []
    for i, (key, img, text, title) in enumerate(CHAPTERS):
        mp3 = AUD / f"{key}.mp3"
        print("TTS", key, flush=True)
        synth(text, mp3)
        d = duration(mp3)
        seg = OUT / f"_seg_{i}.mp4"
        subprocess.run([
            "ffmpeg", "-y", "-loop", "1", "-i", str(OUT / img), "-i", str(mp3),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2:white,format=yuv420p",
            "-c:v", "libx264", "-preset", "medium", "-tune", "stillimage",
            "-c:a", "aac", "-b:a", "128k", "-r", "25", "-shortest", str(seg),
        ], check=True, capture_output=True)
        segs.append(seg)
        manifest.append({"key": key, "title": title, "image": f"/demo/{img}",
                         "audio": f"/demo/audio/{key}.mp3", "narration": text, "duration": round(d, 2)})
        print("seg done", key, round(d, 2), flush=True)

    lst = OUT / "_concat.txt"
    lst.write_text("".join(f"file '{s}'\n" for s in segs))
    final = OUT / "construpilot-demo.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "copy", str(final)], check=True, capture_output=True)
    for s in segs:
        s.unlink(missing_ok=True)
    lst.unlink(missing_ok=True)
    total = round(sum(m["duration"] for m in manifest), 1)
    (OUT / "demo.json").write_text(json.dumps(
        {"video": "/demo/construpilot-demo.mp4", "total_duration": total, "chapters": manifest},
        ensure_ascii=False, indent=2))
    print("VIDEO OK", final, os.path.getsize(final), "total", total, flush=True)


if __name__ == "__main__":
    main()
