#!/usr/bin/env python3
"""Integração do Dossier de Obra (commits 6f9eedc + 70e89fd) nos 2 ficheiros que divergiram no Emergent.

Uso (no /app do Emergent, durante o cherry-pick de 6f9eedc em conflito) :
    git checkout --ours frontend/src/App.js frontend/src/pages/Chantiers.jsx
    python3 /tmp/do/aplicar.py /app
Mantém a versão do HEAD (lazy imports existentes, WorkspacePageHeading…) e só ACRESCENTA :
  App.js        : const DossierObra = lazy(...) + rota /chantiers/:chantierId/dossier/*
  Chantiers.jsx : botão « Exemplo demonstrativo » (só fora de construpilot.pt/.fr) ao lado de « Nova obra »
Idempotente. Se uma âncora não for encontrada : sai com código 2 sem escrever nada. Escrito pelo Claude — o agente só executa.
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/app")
FALHAS = []


def need(cond, msg):
    if not cond:
        FALHAS.append(msg)


def app_js(s):
    if 'lazy(() => import("@/pages/DossierObra"))' not in s:
        m = list(re.finditer(r'^const \w+ = lazy\(\(\) => import\("@/pages/[^"]+"\)\);\n', s, re.M))
        need(bool(m), "App.js: nenhum « const X = lazy(() => import(\"@/pages/…\")) » encontrado")
        if m:
            s = s[:m[-1].end()] + 'const DossierObra = lazy(() => import("@/pages/DossierObra"));\n' + s[m[-1].end():]
    if 'path="/chantiers/:chantierId/dossier/*"' not in s:
        m = re.search(r'^( *)<Route path="/chantiers/:chantierId" element=[^\n]*\n', s, re.M)
        need(m is not None, 'App.js: rota <Route path="/chantiers/:chantierId" …> não encontrada')
        if m:
            i = m.group(1)
            rota = (f'{i}<Route path="/chantiers/:chantierId/dossier/*" element={{<ProRoute><Shell><Suspense fallback={{<div className="p-6 text-sm '
                    f'text-muted-foreground">A carregar…</div>}}><DossierObra /></Suspense></Shell></ProRoute>}} />\n')
            s = s[:m.end()] + rota + s[m.end():]
    need(re.search(r'\bSuspense\b', s.split("function AppRouter")[0]) is not None, "App.js: Suspense não importado")
    need("ProRoute" in s and "Shell" in s, "App.js: ProRoute / Shell não encontrados")
    return s


def chantiers(s):
    if "chantiers-demo-btn" in s:
        return s
    if not re.search(r'import \{[^}]*\btoast\b[^}]*\} from "sonner"', s):
        m = re.search(r'^import [^\n]*from "lucide-react";\n', s, re.M)
        need(m is not None, "Chantiers.jsx: import lucide-react não encontrado")
        if m:
            s = s[:m.end()] + 'import { toast } from "sonner";\n' + s[m.end():]
    m = re.search(r'^export default function Chantiers\(', s, re.M)
    need(m is not None, "Chantiers.jsx: export default function Chantiers não encontrado")
    if m and "DEMO_ALLOWED =" not in s:
        s = s[:m.start()] + ('// Dados fictícios só fora de produção (o servidor recusa também em produção).\n'
                             'const DEMO_ALLOWED = typeof window !== "undefined" && !/(^|\\.)construpilot\\.(pt|fr)$/.test(window.location.hostname);\n\n') + s[m.start():]
    nv = re.search(r'const (\w+) = useNavigate\(\)', s)
    need(nv is not None, "Chantiers.jsx: const X = useNavigate() não encontrado")
    nav = nv.group(1) if nv else "nav"
    m = re.search(r'^( *)return \(\n', s[s.find("export default function Chantiers("):], re.M) if "export default function Chantiers(" in s else None
    need(m is not None, "Chantiers.jsx: « return ( » do componente não encontrado")
    if m and "const createDemo" not in s:
        pos = s.find("export default function Chantiers(") + m.start()
        i = m.group(1)
        s = s[:pos] + (f'{i}const createDemo = async () => {{\n'
                       f'{i}  try {{ const {{ data }} = await api.post("/dossier-obra/demo"); {nav}(`/chantiers/${{data.chantier_id}}/dossier`); }}\n'
                       f'{i}  catch (e) {{ toast.error(e?.response?.data?.detail || "Exemplo indisponível neste ambiente."); }}\n'
                       f'{i}}};\n') + s[pos:]
    m = re.search(r'<Button(?:(?!</Button>).)*?data-testid="chantiers-new-btn"(?:(?!</Button>).)*?</Button>', s, re.S)
    need(m is not None, 'Chantiers.jsx: botão data-testid="chantiers-new-btn" não encontrado')
    if m:
        demo = ('{DEMO_ALLOWED && <Button variant="outline" className="gap-2" onClick={createDemo} data-testid="chantiers-demo-btn">'
                'Exemplo demonstrativo</Button>}')
        s = s[:m.start()] + "<>" + demo + m.group(0) + "</>" + s[m.end():]
    need("api" in s and re.search(r'import \{[^}]*\bapi\b[^}]*\} from "@/lib/api"', s) is not None, "Chantiers.jsx: api não importado")
    return s


ALVOS = [("frontend/src/App.js", app_js), ("frontend/src/pages/Chantiers.jsx", chantiers)]
res = []
for rel, fn in ALVOS:
    p = ROOT / rel
    antes = p.read_text(encoding="utf-8")
    need("<<<<<<<" not in antes and ">>>>>>>" not in antes, f"{rel}: ainda tem marcadores de conflito — fazer antes git checkout --ours")
    res.append((p, antes, fn(antes)))
if FALHAS:
    print("FALHA — nada foi escrito :")
    for f in FALHAS:
        print(" -", f)
    sys.exit(2)
for p, antes, depois in res:
    if antes != depois:
        p.write_text(depois, encoding="utf-8")
    print(("ALTERADO  " if antes != depois else "JÁ OK     ") + str(p.relative_to(ROOT)))
print("OK")
