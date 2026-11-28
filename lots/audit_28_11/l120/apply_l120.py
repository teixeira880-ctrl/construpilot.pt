"""Lot 120 (FR + PT) — LSF : dimensionnement automatique. Les éléments « à revoir » (taux > 1) de la vérification
EN 1993-1-3 sont renforcés seuls : épaisseur des montants (même section, géométrie inchangée), puis entraxe ; linteaux,
solives et fermes à la section supérieure. Un mur de périmètre n'est renforcé que sur le côté concerné (tiposLado).
Maison exemple : 5 éléments à revoir (taux max 1,64) → 0 (taux max ≤ 1). Les renforts sont listés dans les hypothèses
du dossier ; « dimensionamentoAuto: false » dans le projet les désactive. Tests de géométrie de référence alignés.
Usage : python3 lots/audit_28_11/l120/apply_l120.py <racine /app> <fr|pt>
Tout ou rien : si une seule ancre manque, rien n'est modifié (rapport « IGNORÉ » avec le fichier en cause).
Idempotent : relancé après application, il répond « DÉJÀ »."""
import json, pathlib, sys
root = pathlib.Path(sys.argv[1]); site = sys.argv[2] if len(sys.argv) > 2 else "fr"
here = pathlib.Path(__file__).resolve().parent
data = json.loads((here / "patches.json").read_text(encoding="utf-8"))
SKIP_PT = set([])
todo, done, missing = [], 0, []
texts = {}
for p in data["patches"]:
    if site == "pt" and p["file"] in SKIP_PT:
        continue
    f = root / p["file"]
    if p["file"] not in texts:
        texts[p["file"]] = f.read_text(encoding="utf-8") if f.exists() else None
    t = texts[p["file"]]
    if t is None:
        missing.append(p["file"] + " (absent)")
    elif p["new"] in t:
        done += 1
    elif t.count(p["old"]) == 1:
        todo.append(p)
    else:
        missing.append(p["file"])
nf = [n for n in data["new_files"] if not (site == "pt" and n["file"] in SKIP_PT)]
if missing:
    print("IGNORÉ    l120 — ancres absentes dans : " + ", ".join(sorted(set(missing))) + " → rien n'a été modifié")
    sys.exit(1)
for p in todo:
    if texts[p["file"]].count(p["old"]) != 1:
        print("IGNORÉ    l120 — chevauchement dans " + p["file"] + " → rien n'a été modifié"); sys.exit(1)
    texts[p["file"]] = texts[p["file"]].replace(p["old"], p["new"], 1)
for k, t in texts.items():
    if t is not None:
        (root / k).write_text(t, encoding="utf-8")
for n in nf:
    dst = root / n["file"]; dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((here / "files" / n["src"]).read_text(encoding="utf-8"), encoding="utf-8")
print(("DÉJÀ      " if not todo else "OK        ") + f"l120 ({site}) : {len(todo)} modification(s) appliquée(s), {done} déjà présente(s), {len(nf)} fichier(s) posé(s)")
