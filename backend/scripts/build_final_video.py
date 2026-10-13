"""Étape 3 — Muxe les pistes de narration (déjà générées) sur la vidéo enregistrée,
aux offsets réels. Comme chaque page reste affichée au moins la durée de sa voix,
les pistes ne se chevauchent jamais → synchronisation garantie."""
import json, os, subprocess
from pathlib import Path

OUT = Path("/app/frontend/public/demo")
NARR = json.loads(Path("/tmp/narration.json").read_text())


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True)
    return float(r.stdout.strip() or 0)


def main():
    meta = json.loads(Path("/tmp/rec_meta.json").read_text())
    webm, offs = meta["video"], meta["offsets"]
    vdur = dur(webm)
    chapters, inputs, filters, mixes = [], ["-i", webm], [], []
    idx = 1
    for name, info in NARR.items():
        if name not in offs:
            continue
        mp3 = info["file"]
        start = offs[name]
        inputs += ["-i", str(mp3)]
        filters.append(f"[{idx}:a]adelay={int(start*1000)}:all=1[a{idx}]")
        mixes.append(f"[a{idx}]")
        chapters.append({"key": name, "title": info["title"], "start": start,
                         "narration": info["text"], "image": None})
        idx += 1
    fc = ";".join(filters) + ";" + "".join(mixes) + f"amix=inputs={len(mixes)}:normalize=0[aout]"
    final = OUT / "construpilot-demo.mp4"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", fc,
           "-map", "0:v", "-map", "[aout]", "-c:v", "libx264", "-preset", "veryfast",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-shortest", str(final)]
    print("MUX", len(mixes), "pistes, vdur", round(vdur, 1), flush=True)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print("FFMPEG ERR", r.stderr[-800:]); return
    (OUT / "demo.json").write_text(json.dumps(
        {"video": "/demo/construpilot-demo.mp4", "total_duration": round(vdur, 1),
         "chapters": chapters}, ensure_ascii=False, indent=2))
    print("DONE", final, os.path.getsize(final), flush=True)


if __name__ == "__main__":
    main()
