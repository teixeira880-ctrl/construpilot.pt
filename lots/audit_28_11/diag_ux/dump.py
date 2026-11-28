"""Diagnóstico (só leitura): mostra as partes do .pt necessárias para adaptar a ergonomia (l127pt) e as escadas (l126pt)."""
import pathlib, re, sys
root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/app") / "frontend/src"
def show(rel, pats, ctx=6, whole_max=0):
    f = root / rel
    print(f"\n######## {rel} ########")
    if not f.exists(): print("ABSENT"); return
    L = f.read_text(encoding="utf-8").split("\n")
    print(f"({len(L)} linhas)")
    if whole_max and len(L) <= whole_max:
        for i, l in enumerate(L): print(f"{i+1:5d}| {l}")
        return
    shown = set()
    for i, l in enumerate(L):
        if any(re.search(p, l) for p in pats):
            for j in range(max(0, i - ctx), min(len(L), i + ctx + 1)):
                if j not in shown: print(f"{j+1:5d}| {L[j][:400]}"); shown.add(j)
            print("   ...")
show("components/workspace/WorkspaceNavigation.jsx", [], whole_max=400)
show("components/workspace/navigation.js", [r"^import ", r"workspaceEssentials", r"WORKSPACE_GROUPS", r"hub:"], ctx=4)
show("pages/StairCalculator.jsx", [r"DEFAULT_FORM", r"function AlertRow", r"ALERT_META", r"a\.code"], ctx=12)
pk = root.parent / "package.json"
txt = pk.read_text(encoding="utf-8"); m = re.search(r'"jest"\s*:\s*\{[^}]*\}', txt); print("\n######## package.json jest ########\n", m.group(0) if m else "(sem bloco jest)")
for c in ["craco.config.js", "jsconfig.json"]:
    p = root.parent / c; print(f"\n######## {c} ########"); print(p.read_text(encoding='utf-8')[:1500] if p.exists() else "ABSENT")
