"""Instala os motores LSF + CLT + construção tradicional (ramo claude/motor-clt, PR #32) num servidor cujo histórico git e
frontend divergiram do GitHub.

Uso (em /app, depois de `git fetch https://github.com/teixeira880-ctrl/construpilot.pt claude/motor-clt`):
    python3 scripts/apply_motor_clt_placement.py <sha> [<base>]        (sha = 05bcfc7, base = eb38923)

Atómico: prepara tudo em memória e verifica todas as âncoras; se algo falhar, mostra o contexto e sai com código 2 SEM
escrever nada. Idempotente: o que já existir é saltado.
- ficheiros novos (motores, rotas, testes, páginas): copiados do commit;
- ficheiros modificados do backend e Assistant.jsx / CalcLive.jsx / translations.js: fusão a 3 vias (git merge-file) entre o
  ficheiro atual, a base e o commit — conflito = erro;
- App.js e workspace/navigation.js: inserção por âncoras sobre o estado ATUAL (a seguir à rota /plano-estaleiro ou /dpgf);
- workspace/families.js: fusão a 3 vias se existir, senão saltado.
"""
import os
import re
import subprocess
import sys
import tempfile

sha = sys.argv[1] if len(sys.argv) > 1 else "05bcfc7"
base = sys.argv[2] if len(sys.argv) > 2 else "eb38923"
FE = "frontend/src"
errors, notes, writes = [], [], {}
PAGES = [("/estrutura-lsf", "LsfStudies", "nav.lsf", "Estrutura em aço leve (LSF)",
          "lsf light steel framing aço leve estrutura metálica perfis montantes guias quantidades parafusos placas osb lista de corte",
          "Estrutura em aço leve a partir da sua planta: cada perfil, plano de corte das placas, parafusos contados um a um, alçados de fabrico, Excel e 3D."),
         ("/estrutura-clt", "CltStudies", "nav.clt", "Estrutura em CLT (madeira lamelada-colada cruzada)",
          "clt cross laminated timber x-lam madeira lamelada colada cruzada painéis madeira maciça m3 prensa esquadros hold-down parafusos quantidades rezult",
          "Estrutura em CLT a partir da sua planta: cada painel com os vãos recortados, plano de prensa, ligações contadas uma a uma, alçados de fabrico, Excel, 3D e render fotorrealista."),
         ("/construcao-tradicional", "TradicionalStudies", "nav.tradicional", "Construção tradicional (betão armado + alvenarias)",
          "construção tradicional betão armado alvenaria tijolo bloco pilares vigas sapatas lajes medições mapa de quantidades por piso aço cofragem fundações",
          "Construção tradicional a partir da sua planta: cada elemento de betão armado dimensionado, alvenarias contadas fiada a fiada, mapa por piso das fundações à cobertura, Excel, 3D e render fotorrealista.")]


def git(*a):
    r = subprocess.run(["git", *a], capture_output=True, text=True)
    return None if r.returncode else r.stdout


def git_show(rev, p):
    return git("show", f"{rev}:{p}")


def read(p):
    return writes.get(p) if p in writes else open(p, encoding="utf-8").read()


def ctx(p, pat):
    return subprocess.run(["grep", "-n", "-E", pat, p], capture_output=True, text=True).stdout[:1500] or "(nada)"


diff = git("diff", "--name-status", base, sha)
if diff is None:
    print(f"git diff {base} {sha} falhou (git fetch do ramo claude/motor-clt?)")
    sys.exit(2)
ANCORADOS = {f"{FE}/App.js", f"{FE}/components/workspace/navigation.js"}
for ln in diff.splitlines():
    st, p = ln.split("\t", 1)
    if p in ANCORADOS:
        continue
    theirs = git_show(sha, p)
    if st == "A":
        if os.path.exists(p) and open(p, encoding="utf-8", errors="ignore").read() == theirs:
            notes.append(f"{p}: já idêntico — saltado")
        else:
            writes[p] = theirs
        continue
    if not os.path.exists(p):
        if p.endswith("families.js"):
            notes.append("families.js: ausente neste servidor — saltado (a entrada no menu chega)")
        else:
            errors.append(f"{p}: ausente neste servidor")
        continue
    cur = open(p, encoding="utf-8").read()
    if cur == theirs:
        notes.append(f"{p}: já idêntico — saltado")
        continue
    with tempfile.TemporaryDirectory() as d:
        fb, ft = os.path.join(d, "base"), os.path.join(d, "theirs")
        open(fb, "w", encoding="utf-8").write(git_show(base, p) or "")
        open(ft, "w", encoding="utf-8").write(theirs)
        r = subprocess.run(["git", "merge-file", "-p", p, fb, ft], capture_output=True, text=True)
    if r.returncode != 0:
        errors.append(f"{p}: conflito na fusão a 3 vias ({r.returncode} zona(s))")
    else:
        writes[p] = r.stdout

# App.js
p = f"{FE}/App.js"
s = read(p)
m = re.search(r'^([ \t]*)<Route path="/(plano-estaleiro|dpgf)"[^\n]*\n', s, re.M)
if not m:
    errors.append('App.js: rota âncora /plano-estaleiro ou /dpgf não encontrada\n' + ctx(p, "plano-estaleiro|dpgf"))
else:
    line, comp_m = m.group(0), re.search(r"<(\w+) />", m.group(0))
    if not comp_m:
        errors.append("App.js: componente da rota âncora não encontrado:\n" + line)
    else:
        comp = comp_m.group(1)
        di = re.search(rf'^(?:const {comp} = lazy\([^\n]*|import {comp} from [^\n]*)\n', s, re.M)
        if not di:
            errors.append(f"App.js: declaração de {comp} não encontrada\n" + ctx(p, comp))
        else:
            rotas, decls = "", ""
            for route, page, *_ in PAGES:
                if f'path="{route}"' in s:
                    notes.append(f"App.js: rota {route} já existe — saltado")
                    continue
                rotas += line.replace(f'path="/{m.group(2)}"', f'path="{route}"').replace(f"<{comp} />", f"<{page}Lazy />")
                decls += f'const {page}Lazy = lazy(() => import("@/pages/{page}"));\n' if "lazy(" in di.group(0) else f'import {page}Lazy from "@/pages/{page}";\n'
            if rotas:
                s = s[:m.end()] + rotas + s[m.end():]
                di = re.search(rf'^(?:const {comp} = lazy\([^\n]*|import {comp} from [^\n]*)\n', s, re.M)
                s = s[:di.end()] + decls + s[di.end():]
                writes[p] = s

# navigation.js
p = f"{FE}/components/workspace/navigation.js"
s = read(p)
m = re.search(r'^([ \t]*)\{ to: "/(plano-estaleiro|dpgf)",[^\n]*\n', s, re.M)
if not m:
    errors.append("navigation.js: entrada âncora não encontrada\n" + ctx(p, "plano-estaleiro|dpgf"))
else:
    line, novo, ben = m.group(0), "", ""
    icon = "Ruler" if re.search(r"\bRuler\b", s) else None
    for route, page, key, label, words, benef in PAGES:
        if f'to: "{route}"' in s:
            notes.append(f"navigation.js: {route} já existe — saltado")
            continue
        n = re.sub(r'to: "/[\w-]+"', f'to: "{route}"', line, count=1)
        n = re.sub(r'key: "[^"]*"', f'key: "{key}"', n, count=1)
        n = re.sub(r'label: "[^"]*"', f'label: "{label}"', n, count=1)
        n = re.sub(r'words: "[^"]*"', f'words: "{words}"', n, count=1)
        n = re.sub(r'badge: "[^"]*", ?', "", n)
        if icon:
            n = re.sub(r"icon: \w+", f"icon: {icon}", n, count=1)
        novo += n
        ben += f'  "{route}": "{benef}",\n'
    if novo:
        s = s[:m.end()] + novo + s[m.end():]
        mb = re.search(r'^[ \t]*"/(plano-estaleiro|dpgf)": "[^\n]*\n', s, re.M)
        if mb:
            s = s[:mb.end()] + ben + s[mb.end():]
        else:
            notes.append("navigation.js: textos de benefício âncora não encontrados — entradas sem benefício")
        writes[p] = s

for n in notes:
    print(n)
if errors:
    print("\n=== ERROS — NADA FOI ESCRITO ===")
    for e in errors:
        print("-", e)
    sys.exit(2)
for p, s in writes.items():
    if os.path.dirname(p):
        os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)
    print("escrito:", p)
