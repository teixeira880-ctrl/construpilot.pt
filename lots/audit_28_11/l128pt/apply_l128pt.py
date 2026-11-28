"""Lot 128pt (.pt) — /bim?atelier=… (projeto do Ateliê aberto no visualizador BIM) rebentava com «L is not defined»: os textos L eram definidos em BimViewer mas usados em BimPlanViewer. Detetado pela nova verificação automática (eslint no-undef).
Usage : python3 lots/audit_28_11/l128pt/apply_l128pt.py /app pt
Application FICHIER PAR FICHIER : un fichier dont l'ancre diffère est IGNORÉ sans bloquer les autres
(les patches d'un même fichier restent tout-ou-rien). Idempotent : relancé, il répond « DÉJÀ »."""
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]); here = pathlib.Path(__file__).resolve().parent
data = json.loads((here / "patches.json").read_text(encoding="utf-8"))
groups = {}
for p in data["patches"]:
    groups.setdefault(p["file"], []).append(p)
tot_ok = tot_ign = 0
for fn, ps in groups.items():
    f = root / fn
    if not f.exists():
        print(f"ABSENT    {fn}"); tot_ign += 1; continue
    t = f.read_text(encoding="utf-8"); todo, done, ok = [], 0, True
    for p in ps:
        if p["new"] in t: done += 1
        elif t.count(p["old"]) == 1: todo.append(p)
        else: ok = False
    if not ok:
        print(f"IGNORÉ    {fn} — ancre différente sur le serveur (rien modifié dans ce fichier)"); tot_ign += 1; continue
    for p in todo:
        if t.count(p["old"]) != 1:
            print(f"IGNORÉ    {fn} — chevauchement"); ok = False; break
        t = t.replace(p["old"], p["new"], 1)
    if not ok: tot_ign += 1; continue
    if todo: f.write_text(t, encoding="utf-8")
    tot_ok += 1
    print(("OK        " if todo else "DÉJÀ      ") + f"{fn} : {len(todo)} appliquée(s), {done} déjà présente(s)")
for n in data.get("new_files", []):
    dst = root / n["file"]; dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((here / "files" / n["src"]).read_text(encoding="utf-8"), encoding="utf-8"); print(f"POSÉ      {n['file']}")
print(f"l128pt : {tot_ok} fichier(s) OK/DÉJÀ, {tot_ign} ignoré(s)")
