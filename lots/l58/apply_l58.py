"""Lot 58 — pitch deck investisseurs v3.1 (FR · PT · EN) : chiffres et équipe à jour (04/11/2026, demande du fondateur).

Diapositive 8 : 85 utilisateurs (42 France, 43 Portugal), « quasiment sans publicité ».
Diapositive 11 : Ângelo Cunha CEO du groupe, plateforme construite par Martinho et Ângelo, parcours d'Ângelo,
équipe familiale qui parle PT · FR · EN · ES. Les 10 autres diapositives sont inchangées.

Remplace, dans chaque dossier backend/assets/investors/** dont le manifeste correspond à l'ancien deck de la
même langue : le .pptx, le .pdf, slides/8.webp et slides/11.webp, puis met à jour le manifeste et le test
iter159 s'il vérifie l'ancienne empreinte.
Usage : python3 lots/l58/apply_l58.py <racine /app>   (idempotent ; ARRÊT si aucun deck reconnu)
"""
import hashlib
import json
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1])
here = pathlib.Path(__file__).resolve().parent
OLD = {"e19c21a9995b1e398806791958c31a8943fffc0ca87a96cd050d6e5fbf29e2be": "fr",
       "2c89c412719f16c53c3b71cc5315647c6d43620482774daebd4c11303c84cebc": "pt",
       "62f0da6530595e12db03bdbcddd826564cc5cd6b5a92d711c7198c166693508b": "en"}
FILES = ("ConstruPilot_PitchDeck.pptx", "ConstruPilot_PitchDeck.pdf", "slides/8.webp", "slides/11.webp")


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


NEW = {l: sha(here / "assets" / l / "ConstruPilot_PitchDeck.pptx") for l in ("fr", "pt", "en")}
base = root / "backend" / "assets" / "investors"
done, already = [], []
old_by_prefix = {k[:12]: v for k, v in OLD.items()}
for man in sorted(base.rglob("manifest.json")):
    m = json.loads(man.read_text(encoding="utf-8"))
    src = m.get("source_sha256", "")
    lang = OLD.get(src) or old_by_prefix.get(src[:12])
    if src in NEW.values():
        already.append(str(man.relative_to(root))); continue
    if not lang:
        continue
    d = man.parent
    for rel in FILES:
        if rel not in m.get("files", {}):
            print(f"{man.relative_to(root)} : entrée {rel} absente — ARRÊT, rien écrit"); sys.exit(1)
    for rel in FILES:
        src_f = here / "assets" / lang / rel
        dst = d / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_f, dst)
        m["files"][rel] = {"sha256": sha(dst), "byte_size": dst.stat().st_size}
    m["source_sha256"] = m["files"]["ConstruPilot_PitchDeck.pptx"]["sha256"]
    man.write_text(json.dumps(m, indent=2, ensure_ascii=False), encoding="utf-8")
    done.append(f"{man.relative_to(root)} ({lang})")
if not done and not already:
    print("Aucun deck reconnu sous backend/assets/investors — ARRÊT, rien écrit"); sys.exit(1)
t = root / "backend" / "tests" / "test_iter159_pitch_deck_replacement.py"
if t.exists():
    s = t.read_text(encoding="utf-8")
    fr_man = base / "fr" / "manifest.json"
    if fr_man.exists():
        fm = json.loads(fr_man.read_text(encoding="utf-8"))
        s2 = s.replace("e19c21a9995b1e398806791958c31a8943fffc0ca87a96cd050d6e5fbf29e2be", fm["source_sha256"])
        for old_size in ("1013590",):
            s2 = s2.replace(f"== {old_size}", f"== {fm['files']['ConstruPilot_PitchDeck.pdf']['byte_size']}")
        if s2 != s:
            t.write_text(s2, encoding="utf-8"); print("ok tests/test_iter159 (empreinte FR mise à jour)")
(root / "backend" / "tests" / "test_l58.py").write_bytes((here / "tests" / "test_l58.py").read_bytes())
for x in done: print("ok", x)
for x in already: print("déjà à jour", x)
print("L58 OK")
