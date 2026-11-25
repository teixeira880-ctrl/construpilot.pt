#!/usr/bin/env python3
"""Dossier de Obra — integração em frontend/src/components/workspace/WorkspaceNavigation.jsx (commit 70e89fd em conflito).

Uso (no /app do Emergent, durante o cherry-pick de 70e89fd em conflito) :
    git checkout --ours frontend/src/components/workspace/WorkspaceNavigation.jsx
    python3 /tmp/do/navegacao.py /app
Mantém TUDO o que o HEAD tem (BrandWordmark, workspace-tiles.css, workspace-refinement.css…) e só ACRESCENTA :
  - import "@/styles/workspace-green.css" depois do último import de @/styles/*.css
  - imports DossierSidebarSection / DossierFinalLink / useDossierSidebar
  - const dossierOpen = Boolean(useDossierSidebar());
  - <DossierSidebarSection /> logo a seguir ao grupo «O essencial»
  - com um dossier aberto: «Documento final» no lugar do cartão de ajuda e da ligação «Conta» (fora do dossier: igual ao HEAD)
Idempotente. Âncora em falta → « FALHA », sai com código 2 e não escreve nada. Escrito pelo Claude — o agente só executa.
"""
import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else "/app")
P = ROOT / "frontend/src/components/workspace/WorkspaceNavigation.jsx"
FALHAS = []


def need(cond, msg):
    if not cond:
        FALHAS.append(msg)
    return cond


s = P.read_text(encoding="utf-8")
orig = s
need("<<<<<<<" not in s and ">>>>>>>" not in s, "ainda tem marcadores de conflito — fazer antes git checkout --ours")

# 1) CSS verde (depois do último import de estilos)
if '"@/styles/workspace-green.css"' not in s:
    m = list(re.finditer(r'^import "@/styles/[^"]+\.css";\n', s, re.M))
    if need(bool(m), 'nenhum import "@/styles/….css" encontrado'):
        s = s[:m[-1].end()] + 'import "@/styles/workspace-green.css";\n' + s[m[-1].end():]

# 2) imports dos componentes do dossier (depois do último import do ficheiro)
if "DossierSidebarSection" not in s.split("export default function")[0]:
    m = list(re.finditer(r'^import [^\n]+;\n', s, re.M))
    if need(bool(m), "nenhuma linha import encontrada"):
        s = s[:m[-1].end()] + ('import { DossierSidebarSection, DossierFinalLink } from "@/components/dossierObra/SidebarSection";\n'
                               'import { useDossierSidebar } from "@/components/dossierObra/sidebarStore";\n') + s[m[-1].end():]

# 3) estado «dossier aberto»
if "const dossierOpen" not in s:
    m = re.search(r'^( *)const navigate = useNavigate\(\);\n', s, re.M)
    if need(m is not None, "« const navigate = useNavigate(); » não encontrado"):
        s = s[:m.end()] + f"{m.group(1)}const dossierOpen = Boolean(useDossierSidebar());\n" + s[m.end():]

# 4) secção ESPECIALIDADES a seguir ao grupo «O essencial»
if "<DossierSidebarSection" not in s:
    m = re.search(r'^( *)<div className="workspace-nav-group" data-testid="workspace-nav-essentials">.*?</div>\n', s, re.M)
    if need(m is not None, 'grupo data-testid="workspace-nav-essentials" (numa linha) não encontrado'):
        s = s[:m.end()] + f"{m.group(1)}<DossierSidebarSection />\n" + s[m.end():]

# 5) «Documento final» no lugar do cartão de ajuda e da ligação Conta, só com um dossier aberto
if "<DossierFinalLink" not in s:
    m = re.search(r'^( *)(<Link to="/aide" className="workspace-help-card"[^\n]*</Link>)\n', s, re.M)
    if need(m is not None, 'cartão de ajuda <Link to="/aide" className="workspace-help-card" …> (numa linha) não encontrado'):
        s = s[:m.start()] + f"{m.group(1)}{{dossierOpen ? <DossierFinalLink /> : {m.group(2)}}}\n" + s[m.end():]
    m = re.search(r'^( *)(<Link className="workspace-sidebar-account"[^\n]*</Link>)\n', s, re.M)
    if need(m is not None, 'ligação <Link className="workspace-sidebar-account" …> (numa linha) não encontrada'):
        s = s[:m.start()] + f"{m.group(1)}{{!dossierOpen && {m.group(2)}}}\n" + s[m.end():]

for f in ("frontend/src/components/dossierObra/SidebarSection.jsx", "frontend/src/components/dossierObra/sidebarStore.js"):
    need((ROOT / f).exists(), f"{f} não existe (o commit 6f9eedc/70e89fd tem de estar aplicado)")

if FALHAS:
    print("FALHA — nada foi escrito :")
    for f in FALHAS:
        print(" -", f)
    sys.exit(2)
if s != orig:
    P.write_text(s, encoding="utf-8")
print(("ALTERADO  " if s != orig else "JÁ OK     ") + str(P.relative_to(ROOT)))
print("OK")
