"""Lot 120pt — dimensionamento automático LSF no construpilot.pt (adaptação do l120 do .fr).
Núcleo (engine.py, verificacao.py, __init__.py + novo dimensionar.py) : tudo-ou-nada.
note.py e tests/test_lsf_engine.py : âncoras flexíveis (regex) porque divergem do .fr.
Usage : python3 lots/audit_28_11/l120pt/apply_l120pt.py /app pt — idempotente."""
import json, pathlib, re, sys
root = pathlib.Path(sys.argv[1]); here = pathlib.Path(__file__).resolve().parent
data = json.loads((here / "patches.json").read_text(encoding="utf-8"))
FLEX = {"backend/engines/lsf/note.py", "backend/tests/test_lsf_engine.py"}
core = [p for p in data["patches"] if p["file"] not in FLEX]
texts, todo, done, missing = {}, [], 0, []
for p in core:
    f = root / p["file"]
    if p["file"] not in texts:
        texts[p["file"]] = f.read_text(encoding="utf-8") if f.exists() else None
    t = texts[p["file"]]
    if t is None: missing.append(p["file"] + " (absent)")
    elif p["new"] in t: done += 1
    elif t.count(p["old"]) == 1: todo.append(p)
    else: missing.append(p["file"])
if missing:
    print("IGNORÉ    l120pt núcleo — âncoras ausentes em : " + ", ".join(sorted(set(missing))) + " → nada alterado"); sys.exit(1)
for p in todo:
    texts[p["file"]] = texts[p["file"]].replace(p["old"], p["new"], 1)
for k, t in texts.items():
    (root / k).write_text(t, encoding="utf-8")
for n in data["new_files"]:
    dst = root / n["file"]; dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text((here / "files" / n["src"]).read_text(encoding="utf-8"), encoding="utf-8")
print(("OK        " if todo else "DÉJÀ      ") + f"l120pt núcleo : {len(todo)} aplicada(s), {done} já presente(s), dimensionar.py posto")

# note.py : a nota PDF usa os mesmos perfis reforçados que o estudo
nf = root / "backend/engines/lsf/note.py"
t = nf.read_text(encoding="utf-8")
if "dimensionar(" in t:
    print("DÉJÀ      note.py")
else:
    m = re.search(r"^(\s*)(\w+) = projeto\(([^)]*)\)\n(\s*)(\w+) = calcular\(\2\)\n", t, re.M)
    if m:
        ind, pv, rv = m.group(1), m.group(2), m.group(5)
        new = (f"{ind}{pv} = projeto({m.group(3)})\n"
               f"{ind}from .dimensionar import dimensionar\n"
               f"{ind}{pv}, _reforcos = dimensionar({pv})  # mesmos perfis que o estudo\n"
               f"{ind}{rv} = calcular({pv})\n"
               f"{ind}if _reforcos:\n{ind}    {rv}[\"dimensionamento\"] = _reforcos\n")
        nf.write_text(t[:m.start()] + new + t[m.end():], encoding="utf-8"); print("OK        note.py (regex)")
    else:
        print("IGNORÉ    note.py — padrão projeto()/calcular() não encontrado ; linhas com calcular( :")
        for i, l in enumerate(t.split("\n")):
            if "calcular(" in l or "projeto(" in l: print(f"   {i+1:5d}| {l}")

# testes : os testes de referência usam a geometria sem reforços ; novo teste de dimensionamento
tf = root / "backend/tests/test_lsf_engine.py"
if tf.exists():
    t = tf.read_text(encoding="utf-8")
    if "test_dimensionamento_automatico_sem_elementos_a_rever" in t:
        print("DÉJÀ      test_lsf_engine.py")
    else:
        t2 = re.sub(r"estudo\(exemplo\((\"FR\"|'FR')?\)", lambda m: "estudo({**exemplo(" + (m.group(1) or "") + "), \"dimensionamentoAuto\": False}", t)
        t2 = re.sub(r"(\w+_?)\s*,\s*(\w+_?)\s*=\s*exemplo\(\)\s*,\s*exemplo\((\"FR\"|'FR')\)",
                    lambda m: f"{m.group(1)}, {m.group(2)} = {{**exemplo(), \"dimensionamentoAuto\": False}}, {{**exemplo({m.group(3)}), \"dimensionamentoAuto\": False}}", t2)
        if "import json" not in t2: t2 = "import json\n" + t2
        t2 = t2.rstrip("\n") + '''


def test_dimensionamento_automatico_sem_elementos_a_rever():
    """Reforços automáticos : nenhum elemento « a rever » no exemplo."""
    st = estudo(exemplo())
    v = st["resultado"]["verificacao"]
    assert v["resumo"]["a_rever"] == 0 and v["resumo"]["ratio_max"] <= 1.0
    assert st["resultado"]["dimensionamento"]
    st2 = estudo(exemplo())
    assert json.dumps(st2["linhas"], sort_keys=True) == json.dumps(st["linhas"], sort_keys=True)
'''
        tf.write_text(t2, encoding="utf-8"); print("OK        test_lsf_engine.py (regex + novo teste)")
