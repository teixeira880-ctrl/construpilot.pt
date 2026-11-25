"""Instala o « Caderno de encargos e concurso » (commit 85cce3f) num servidor cujo frontend divergiu do GitHub.

Uso (em /app) :  python3 scripts/apply_cctp_placement.py <sha>      (sha = 85cce3f)

Atómico : prepara tudo em memória e verifica todas as âncoras ; se algo falhar, mostra o contexto e sai com
código 2 SEM escrever nada. Idempotente : o que já existir é saltado.

- ficheiros novos (motores, rota, testes, página) : copiados do commit ;
- server.py, routes/missions.py, tests/test_missions_lots.py, Nav.jsx : fusão a 3 vias (git merge-file) entre o
  ficheiro atual, o pai do commit e o commit — conflito = erro ;
- App.js e workspace/navigation.js : inserção por âncoras sobre o estado ATUAL (a seguir às linhas /dpgf) ;
- workspace/families.js : saltado se ausente neste servidor.
"""
import os
import re
import subprocess
import sys
import tempfile

sha = sys.argv[1] if len(sys.argv) > 1 else "85cce3f"
FE = "frontend/src"
ROUTE = "/caderno-encargos"
errors: list[str] = []
writes: dict[str, str] = {}
notes: list[str] = []

NOVOS = ["backend/engines/cctp_catalogue.py", "backend/engines/cctp_redacteur.py", "backend/engines/cctp_pieces.py",
         "backend/engines/dce_pieces.py", "backend/routes/cctp.py", "backend/tests/test_cctp_redacteur.py",
         f"{FE}/pages/CctpPage.jsx"]
FUNDIR = ["backend/server.py", "backend/routes/missions.py", "backend/tests/test_missions_lots.py", f"{FE}/components/Nav.jsx"]


def git_show(rev: str, path: str) -> str | None:
    r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
    return None if r.returncode else r.stdout


def read(p: str) -> str:
    return writes.get(p) if p in writes else open(p, encoding="utf-8").read()


def ctx(p: str, pat: str) -> str:
    out = subprocess.run(["grep", "-n", "-E", pat, p], capture_output=True, text=True).stdout
    return out[:1500] or "(nada)"


# 0) ficheiros novos
for p in NOVOS:
    s = git_show(sha, p)
    if s is None:
        errors.append(f"git show {sha}:{p} falhou (fazer git fetch do ramo claude/caderno-encargos)")
    elif os.path.exists(p) and open(p, encoding="utf-8").read() == s:
        notes.append(f"{p}: já idêntico — saltado")
    else:
        writes[p] = s

# 1) fusão a 3 vias dos ficheiros que fundem sem conflito
for p in FUNDIR:
    base, theirs = git_show(f"{sha}^", p), git_show(sha, p)
    if base is None or theirs is None:
        errors.append(f"{p}: versões do commit indisponíveis")
        continue
    if not os.path.exists(p):
        errors.append(f"{p}: ausente neste servidor")
        continue
    cur = open(p, encoding="utf-8").read()
    if cur == theirs:
        notes.append(f"{p}: já idêntico — saltado")
        continue
    with tempfile.TemporaryDirectory() as d:
        fb, ft = os.path.join(d, "base"), os.path.join(d, "theirs")
        open(fb, "w", encoding="utf-8").write(base)
        open(ft, "w", encoding="utf-8").write(theirs)
        r = subprocess.run(["git", "merge-file", "-p", p, fb, ft], capture_output=True, text=True)
    if r.returncode != 0:
        errors.append(f"{p}: conflito na fusão a 3 vias ({r.returncode} zona(s))")
    else:
        writes[p] = r.stdout

# 2) App.js : import + rota (a seguir à rota /dpgf) + redirecionamento /cctp
p = f"{FE}/App.js"
s = read(p)
if ROUTE in s:
    notes.append("App.js: rota já existe — saltado")
else:
    m = re.search(r'^([ \t]*)<Route path="/dpgf"[^\n]*\n', s, re.M)
    if not m:
        errors.append('App.js: linha <Route path="/dpgf" …> não encontrada\n' + ctx(p, "dpgf|Dpgf"))
    else:
        line = m.group(0)
        if "<DpgfPage />" not in line:
            errors.append("App.js: <DpgfPage /> não encontrado na linha da rota:\n" + line)
        else:
            novo = line.replace('path="/dpgf"', f'path="{ROUTE}"').replace("<DpgfPage />", "<CctpPage />")
            if re.search(r"\bNavigate\b", s):
                novo += f'{m.group(1)}<Route path="/cctp" element={{<Navigate to="{ROUTE}" replace />}} />\n'
            s = s[:m.end()] + novo + s[m.end():]
            mi = re.search(r'^(?:const DpgfPage = lazy\([^\n]*|import DpgfPage from [^\n]*)\n', s, re.M)
            if not mi:
                errors.append("App.js: declaração de DpgfPage não encontrada\n" + ctx(p, "DpgfPage"))
            else:
                decl = ('const CctpPage = lazy(() => import("@/pages/CctpPage"));\n' if "lazy(" in mi.group(0)
                        else 'import CctpPage from "@/pages/CctpPage";\n')
                s = s[:mi.end()] + decl + s[mi.end():]
                writes[p] = s

# 3) navigation.js : entrada do menu + benefício
p = f"{FE}/components/workspace/navigation.js"
s = read(p)
if f'to: "{ROUTE}"' in s:
    notes.append("navigation.js: entrada já existe — saltado")
else:
    m = re.search(r'^([ \t]*)\{ to: "/dpgf",[^\n]*\n', s, re.M)
    if not m:
        errors.append('navigation.js: entrada { to: "/dpgf", … } não encontrada\n' + ctx(p, "dpgf"))
    else:
        line = m.group(0)
        icon = "FileText" if re.search(r"import\s*\{[^}]*\bFileText\b[^}]*\}\s*from\s*\"lucide-react\"", s, re.S) else "FileSpreadsheet"
        novo = re.sub(r'to: "/dpgf"', f'to: "{ROUTE}"', line, count=1)
        novo = re.sub(r'key: "nav\.dpgf"', 'key: "nav.cctp"', novo, count=1)
        novo = re.sub(r'label: "[^"]*"', 'label: "Caderno de encargos e concurso"', novo, count=1)
        novo = re.sub(r'icon: \w+', f"icon: {icon}", novo, count=1)
        novo = re.sub(r'words: "[^"]*"', 'words: "caderno de encargos condições técnicas cláusulas concurso programa de concurso '
                      'mapa de quantidades peças escritas empreitada capítulos especialidades ited rtiebt"', novo, count=1)
        novo = re.sub(r'badge: "[^"]*", ?', "", novo)
        if novo == line or 'to: "/caderno-encargos"' not in novo:
            errors.append("navigation.js: não foi possível derivar a entrada a partir de:\n" + line)
        else:
            s = s[:m.end()] + novo + s[m.end():]
            mb = re.search(r'^([ \t]*)"/dpgf": "[^\n]*\n', s, re.M)
            if mb:
                s = (s[:mb.end()] + f'{mb.group(1)}"{ROUTE}": "Redija o caderno de encargos por capítulos, o mapa de '
                     'quantidades e as peças do concurso.",\n' + s[mb.end():])
            else:
                notes.append("navigation.js: texto de benefício /dpgf não encontrado — entrada sem benefício")
            writes[p] = s

# 4) families.js : só se existir neste servidor
p = f"{FE}/components/workspace/families.js"
if not os.path.exists(p):
    notes.append("families.js: ausente neste servidor — saltado (a entrada no menu chega)")
else:
    s = read(p)
    if f'"{ROUTE}"' in s:
        notes.append("families.js: já contém a rota — saltado")
    elif '"/dpgf", ' in s:
        writes[p] = s.replace('"/dpgf", ', f'"/dpgf", "{ROUTE}", ', 1)
    else:
        notes.append("families.js: lista com /dpgf não encontrada — saltado")

for n in notes:
    print(n)
if errors:
    print("\n=== ERROS — NADA FOI ESCRITO ===")
    for e in errors:
        print("-", e)
    sys.exit(2)
for p, s in writes.items():
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)
    print("escrito:", p)
