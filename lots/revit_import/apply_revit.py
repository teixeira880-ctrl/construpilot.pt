"""Lot import Revit (.rvt) — métré complet via Autodesk APS.
Usage : python3 lots/revit_import/apply_revit.py /app
N'ÉCRASE AUCUN FICHIER EXISTANT : les fichiers existants reçoivent seulement des insertions ancrées.
Application FICHIER PAR FICHIER : un fichier dont l'ancre diffère est IGNORÉ (tout-ou-rien par fichier), avec diagnostic.
Les fichiers NOUVEAUX ne sont posés que s'ils n'existent pas encore (sinon DÉJÀ / DIFFÉRENT, jamais écrasés).
Idempotent : relancé, il répond « DÉJÀ »."""
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]); here = pathlib.Path(__file__).resolve().parent
data = json.loads((here / "patches.json").read_text(encoding="utf-8"))
groups = {}
for p in data["patches"]:
    groups.setdefault(p["file"], []).append(p)
ok_n = ign = 0
for fn, ps in groups.items():
    f = root / fn
    if not f.exists():
        print(f"ABSENT    {fn}"); ign += 1; continue
    t = f.read_text(encoding="utf-8"); todo, done, bad = [], 0, []
    for i, p in enumerate(ps):
        if p["new"] in t: done += 1
        elif t.count(p["old"]) == 1: todo.append(p)
        else: bad.append((i, t.count(p["old"]), p["old"].splitlines()[0][:100]))
    if bad:
        print(f"IGNORÉ    {fn} — ancre(s) différente(s) sur le serveur, rien modifié dans ce fichier :")
        for i, c, first in bad:
            print(f"            patch {i}: trouvée {c} fois — début de l'ancre : {first!r}")
        ign += 1; continue
    for p in todo:
        t = t.replace(p["old"], p["new"], 1)
    if todo: f.write_text(t, encoding="utf-8")
    ok_n += 1
    print(("OK        " if todo else "DÉJÀ      ") + f"{fn} : {len(todo)} appliquée(s), {done} déjà présente(s)")
for n in data.get("new_files", []):
    dst = root / n["file"]; src = (here / "files" / n["src"]).read_text(encoding="utf-8")
    if dst.exists():
        print(("DÉJÀ      " if dst.read_text(encoding="utf-8") == src else "DIFFÉRENT ") + f"{n['file']} (existant, non écrasé)"); continue
    dst.parent.mkdir(parents=True, exist_ok=True); dst.write_text(src, encoding="utf-8"); print(f"POSÉ      {n['file']}")
for b in data.get("binary_files", []):
    print(("PRÉSENT   " if (root / b["file"]).exists() else "MANQUANT  ") + b["file"] + " (git checkout FETCH_HEAD -- " + b["file"] + ")")
print(f"revit_import : {ok_n} fichier(s) OK/DÉJÀ, {ign} ignoré(s)")
