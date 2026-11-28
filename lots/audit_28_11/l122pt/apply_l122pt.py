"""Lot 122pt (construpilot.pt) — mesmos erros do .fr adaptados ao código português, encontrados pela auditoria do .pt :
 • divisões : contorno estreito (vazio entre os dois traços de uma parede, largura média < 30 cm) já não conta como divisão ;
 • planos de execução elétrica/canalização : contornos parasitas ignorados (< 0,5 m² ou largura < 30 cm) ;
 • Planos & medições : área de pavimento controlada pela soma das divisões medidas (betão/aço da laje proporcional, badge « CONTROLADO ») ;
 • escadas, PDF : « Altura livre -1 mm » → « não verificada » ;
 • « Fatura importada » (e não « importado ») ; poupanças com separador de milhares, sem nome de fornecedor (Tavily) ;
 • diagnóstico BTP : tarefa « em curso » há mais de 10 min → interrompida com mensagem ; duração anunciada realista ;
 • erros « nome não definido » (análise estática) : `traceback` em bet_core/assistant_tool (estudo UA falhado mascarado) e `prev_z` em calc_lots/especialidades.
Usage : python3 lots/l122pt/apply_l122pt.py <racine /app> <fr|pt>
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
    print("IGNORÉ    l122pt — ancres absentes dans : " + ", ".join(sorted(set(missing))) + " → rien n'a été modifié")
    sys.exit(1)
for p in todo:
    if texts[p["file"]].count(p["old"]) != 1:
        print("IGNORÉ    l122pt — chevauchement dans " + p["file"] + " → rien n'a été modifié"); sys.exit(1)
    texts[p["file"]] = texts[p["file"]].replace(p["old"], p["new"], 1)
for k, t in texts.items():
    if t is not None:
        (root / k).write_text(t, encoding="utf-8")
for n in nf:
    dst = root / n["file"]; dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((here / "files" / n["src"]).read_text(encoding="utf-8"), encoding="utf-8")
print(("DÉJÀ      " if not todo else "OK        ") + f"l122pt ({site}) : {len(todo)} modification(s) appliquée(s), {done} déjà présente(s), {len(nf)} fichier(s) posé(s)")
