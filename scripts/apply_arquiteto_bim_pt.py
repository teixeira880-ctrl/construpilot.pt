#!/usr/bin/env python3
"""Instala a app « Arquiteto & BIM » (Atelier do Arquiteto) no servidor .pt SEM tocar em nenhum ficheiro existente.

Porquê um script: o ramo claude/arquiteto-bim (e8fd78d) foi feito sobre uma base diferente do servidor; 18 ficheiros
(CCTP, Estúdio de Projeto, server.py, App.js, navegação) já existem no servidor com outro conteúdo e o cherry-pick
entra em conflito. Este script:
  1. COPIA o motor do Estúdio (engines/estudio_projeto) e o motor CCTP/DCE do ramo para dentro de
     engines/atelier_archi/_vend/ (cópia privada do Atelier). O Estúdio e o CCTP do servidor não mudam.
  2. Acrescenta os ficheiros novos do Atelier (motor, rota /api/atelier-archi, página, esboço, Estúdio do Atelier).
  3. Faz inserções por âncora em server.py, App.js e navigation.js (só acrescenta linhas).
Atómico: verifica tudo antes de escrever; se uma verificação falhar, não escreve nada.

Uso:   python3 apply_arquiteto_bim_pt.py <ref-git do ramo>            (ex. FETCH_HEAD)
       python3 apply_arquiteto_bim_pt.py <ref> --rollback               (desfaz exatamente o que foi escrito)
       python3 apply_arquiteto_bim_pt.py <ref> --dry-run                (só verifica)
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys

ROOT = os.getcwd()
BACKUP = "/tmp/apply_arquiteto_bim_pt.backup.json"
VEND = "engines.atelier_archi._vend"

# ------------------------------------------------------------------ ficheiros copiados do ramo
ESTUDIO = ["__init__", "adapter_fr", "cobertura", "derivar", "desenhos", "escadas", "exportar", "i18n", "i18n_fr",
           "i18n_fr_acabamentos", "i18n_fr_biblioteca", "i18n_fr_objetos", "ifc", "materiais", "modelo", "objetos",
           "operacoes", "sitio"]
ATELIER = ["__init__", "croquis", "dce", "generateur", "programme", "vision"]
CCTP_ENGINES = ["cctp_catalogue", "cctp_pieces", "cctp_redacteur", "dce_pieces"]

# (origem no ramo, destino no servidor, tipo de reescrita)
COPIAS = [(f"backend/engines/atelier_archi/{n}.py", f"backend/engines/atelier_archi/{n}.py", "py") for n in ATELIER]
COPIAS += [(f"backend/engines/estudio_projeto/{n}.py", f"backend/engines/atelier_archi/_vend/estudio_projeto/{n}.py", "py")
           for n in ESTUDIO]
COPIAS += [(f"backend/engines/{n}.py", f"backend/engines/atelier_archi/_vend/{n}.py", "py") for n in CCTP_ENGINES]
COPIAS += [("backend/routes/cctp.py", "backend/engines/atelier_archi/_vend/cctp_routes.py", "py"),
           ("backend/routes/atelier_archi.py", "backend/routes/atelier_archi.py", "py"),
           ("backend/tests/test_atelier_archi.py", "backend/tests/test_atelier_archi_pt.py", "test"),
           ("frontend/src/pages/AtelierArchitecte.jsx", "frontend/src/pages/AtelierArchitecte.jsx", "js"),
           ("frontend/src/components/atelier/CroquisCanvas.jsx", "frontend/src/components/atelier/CroquisCanvas.jsx", "js"),
           ("frontend/src/components/licenciamento/EstudioProjeto.jsx", "frontend/src/components/atelier/EstudioAtelier.jsx", "js"),
           ("frontend/src/components/licenciamento/Estudio3D.jsx", "frontend/src/components/atelier/Estudio3DAtelier.jsx", "js"),
           ("frontend/src/components/licenciamento/estudioGeo.js", "frontend/src/components/atelier/estudioGeoAtelier.js", "js")]
NOVOS_VAZIOS = {"backend/engines/atelier_archi/_vend/__init__.py":
                '"""Cópia privada do Estúdio de Projeto e do motor CCTP/DCE usada só pelo Atelier do Arquiteto (não mexe nos do servidor)."""\n'}

PY_REGRAS = [
    (r"\bfrom engines\.estudio_projeto\b", f"from {VEND}.estudio_projeto"),
    (r"\bfrom engines import estudio_projeto\b", f"from {VEND} import estudio_projeto"),
    (r"\bimport engines\.estudio_projeto\b", f"import {VEND}.estudio_projeto"),
    (r"\bfrom engines\.(cctp_catalogue|cctp_pieces|cctp_redacteur|dce_pieces)\b", rf"from {VEND}.\1"),
    (r"\bfrom engines import (cctp_catalogue|cctp_pieces|cctp_redacteur|dce_pieces)\b", rf"from {VEND} import \1"),
    (r"\bfrom routes import cctp as\b", f"from {VEND} import cctp_routes as"),
    (r"\bfrom routes\.cctp import\b", f"from {VEND}.cctp_routes import"),
    (r"([\"'])engines\.estudio_projeto", rf"\1{VEND}.estudio_projeto"),
    (r"([\"'])engines\.(cctp_catalogue|cctp_pieces|cctp_redacteur|dce_pieces)", rf"\1{VEND}.\2"),
]
TEST_REGRAS = PY_REGRAS + [(r"pytest\.importorskip\(\"routes\.cctp\"\)", f'pytest.importorskip("{VEND}.cctp_routes")')]
JS_REGRAS = [
    (r"@/components/licenciamento/EstudioProjeto\b", "@/components/atelier/EstudioAtelier"),
    (r"@/components/licenciamento/Estudio3D\b", "@/components/atelier/Estudio3DAtelier"),
    (r"@/components/licenciamento/estudioGeo\b", "@/components/atelier/estudioGeoAtelier"),
]

# ------------------------------------------------------------------ inserções por âncora (só acrescentam)
SERVER_ADD = ("from routes import atelier_archi as atelier_archi_routes  # noqa: E402  — Atelier do Arquiteto (app « Arquiteto & BIM »)\n"
              "api_router.include_router(atelier_archi_routes.router)\n")
APP_LAZY = 'const AtelierArquitetoLazy = lazy(() => import("@/pages/AtelierArchitecte"));   // app « Arquiteto & BIM »\n'
APP_ROUTE = ('      <Route path="/atelier-arquiteto" element={<ProRoute><Shell><Suspense fallback={<RouteSkeleton />}>'
             '<AtelierArquitetoLazy /></Suspense></Shell></ProRoute>} />\n')


def git_show(ref, path):
    r = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=ROOT, capture_output=True)
    if r.returncode:
        raise SystemExit(f"✗ ficheiro em falta no ramo {ref}: {path}")
    return r.stdout.decode("utf-8")


def ler(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as f:
        return f.read()


def reescrever(txt, regras):
    for pat, rep in regras:
        txt = re.sub(pat, rep, txt)
    return txt


def inserir(txt, ancora_re, bloco, depois=True, nome=""):
    """Insere `bloco` numa linha própria antes/depois da ÚNICA linha que casa com ancora_re."""
    linhas = txt.splitlines(keepends=True)
    idx = [i for i, l in enumerate(linhas) if re.search(ancora_re, l)]
    if len(idx) != 1:
        raise ValueError(f"{nome}: âncora encontrada {len(idx)}× (esperado 1): {ancora_re!r}")
    i = idx[0] + (1 if depois else 0)
    return "".join(linhas[:i] + [bloco] + linhas[i:])


def modo_cctp():
    """O Atelier redige sempre o DCE em francês com a sua cópia do redator (pedido do Martinho).
    Os dossiers vão para o registo comum cctp_dossiers e são servidos por /api/pro/cctp/dossiers.
    'servidor' = o servidor já tem routes/cctp.py compatível (mesmo prefixo e mesmo registo) → não se regista nada;
    'copia'    = o servidor não tem routes/cctp.py → regista-se a rota da cópia em /api/pro/cctp."""
    if not os.path.exists(os.path.join(ROOT, "backend/routes/cctp.py")):
        return "copia", None
    t = ler("backend/routes/cctp.py")
    falta = [n for n, rx in (("prefix /pro/cctp", r'prefix="/pro/cctp"'), ("cctp_dossiers", r"db\.cctp_dossiers"),
                             ("ficheiros", r'"fichiers"'), ("dossiers/{dossier_id}", r"/dossiers/\{dossier_id\}"))
             if not re.search(rx, t)]
    return ("servidor", None) if not falta else (None, "backend/routes/cctp.py do servidor é incompatível (falta: " + ", ".join(falta) + ")")


def plano(ref):
    erros, escritas, avisos = [], {}, []
    modo, err = modo_cctp()
    if err:
        erros.append("✗ " + err)
    regras_rota, regras_teste = PY_REGRAS, TEST_REGRAS
    avisos.append("· DCE do Atelier: redator francês (cópia do Atelier); dossiers servidos por "
                  + ("/api/pro/cctp do servidor (inalterado)" if modo == "servidor" else "/api/pro/cctp da cópia (registado agora)"))
    # 1. ficheiros novos — nenhum pode existir já
    for orig, dest, tipo in COPIAS:
        if os.path.exists(os.path.join(ROOT, dest)):
            erros.append(f"✗ já existe no servidor (não é substituído): {dest}")
            continue
        try:
            regras = {"py": PY_REGRAS, "test": regras_teste, "js": JS_REGRAS}[tipo]
            if dest == "backend/routes/atelier_archi.py":
                regras = regras_rota
            escritas[dest] = reescrever(git_show(ref, orig), regras)
        except SystemExit as e:
            erros.append(str(e))
    for dest, txt in NOVOS_VAZIOS.items():
        if os.path.exists(os.path.join(ROOT, dest)):
            erros.append(f"✗ já existe no servidor: {dest}")
        escritas[dest] = txt
    # nenhuma referência ao Estúdio/CCTP do servidor pode sobrar nas cópias Python
    for dest, txt in escritas.items():
        if dest.endswith(".py"):
            rx = (r"(from|import) (engines\.estudio_projeto|engines\.(cctp_\w+|dce_pieces))\b|from engines import (estudio_projeto|cctp_\w+|dce_pieces)"
                  r"|routes\.cctp\b|from routes import cctp\b")
            for m in re.finditer(rx, txt):
                erros.append(f"✗ {dest}: import não reescrito: {m.group(0)}")
        if dest.endswith((".jsx", ".js")) and "@/components/licenciamento/" in txt:
            erros.append(f"✗ {dest}: import do Estúdio do servidor não reescrito")

    # 2. server.py
    try:
        s = ler("backend/server.py")
        if "routes import atelier_archi" in s:
            avisos.append("· server.py: Atelier já registado — ignorado")
        else:
            add = SERVER_ADD
            if modo == "copia" and "routes import cctp" not in s:
                add = (f"from {VEND} import cctp_routes as cctp_routes  # noqa: E402  — Redator CCTP / DCE (cópia do Atelier)\n"
                       "api_router.include_router(cctp_routes.router)\n") + add
            escritas["backend/server.py"] = inserir(s, r"^app\.include_router\(api_router\)\s*$", add, depois=False, nome="backend/server.py")
    except (OSError, ValueError) as e:
        erros.append(f"✗ {e}")

    # 3. App.js
    try:
        a = ler("frontend/src/App.js")
        if "AtelierArquitetoLazy" in a or 'path="/atelier-arquiteto"' in a:
            avisos.append("· App.js: rota /atelier-arquiteto já existe — ignorado")
        else:
            a = inserir(a, r"^(export default )?function AppRouter\(", APP_LAZY, depois=False, nome="frontend/src/App.js (lazy)")
            a = inserir(a, r'<Route path="/estrutura-lsf"', APP_ROUTE, depois=True, nome="frontend/src/App.js (rota)")
            escritas["frontend/src/App.js"] = a
    except (OSError, ValueError) as e:
        erros.append(f"✗ {e}")

    # 4. navigation.js — entrada no menu, na família « Arquiteto & BIM »
    try:
        n = ler("frontend/src/components/workspace/navigation.js")
        if '"/atelier-arquiteto"' in n:
            avisos.append("· navigation.js: entrada já existe — ignorado")
        else:
            lsf = [l for l in n.splitlines() if re.search(r'to: "/estrutura-lsf"', l)]
            if len(lsf) != 1:
                raise ValueError(f'navigation.js: entrada /estrutura-lsf encontrada {len(lsf)}× (esperado 1)')
            icone = re.search(r"icon: (\w+)", lsf[0]).group(1)            # ícone já importado no ficheiro
            fam = "plans"                                                  # espaço de cor existente (azul)
            entrada = ('  { to: "/atelier-arquiteto", label: "Atelier do Arquiteto", icon: ' + icone
                       + (f', family: "{fam}"' if fam else "")
                       + ', group: "chantiers", pro: true, pin: true, words: "arquiteto arquitetura esboço desenho mão levantada '
                         'caneta tablet fotografia prompt planta moradia modelo alçado corte 3d dxf ifc dce cctp dpgf estúdio de projeto '
                         'architecte croquis" },\n')
            n = inserir(n, r'to: "/estrutura-lsf"', entrada, depois=True, nome="navigation.js (entrada)")
            n = inserir(n, r'^\s*"/estrutura-lsf":', '  "/atelier-arquiteto": "Esboço à mão, fotografia de um esboço ou prompt → '
                        'modelo, plantas à escala, IFC e DCE completo (CCTP + DPGF).",\n', depois=True, nome="navigation.js (descrição)")
            escritas["frontend/src/components/workspace/navigation.js"] = n
    except (OSError, ValueError, AttributeError) as e:
        erros.append(f"✗ {e}")
    # 5. suites.js — nova app « Arquiteto & BIM » (hub /arquiteto-bim gerado automaticamente a partir de APP_SUITES)
    try:
        st = ler("frontend/src/components/workspace/suites.js")
        if 'id: "arquiteto"' in st:
            avisos.append("· suites.js: app Arquiteto & BIM já existe — ignorado")
        else:
            icone = "Map"
            if os.path.exists(os.path.join(ROOT, "frontend/node_modules/lucide-react/dist/esm/icons/drafting-compass.js")):
                icone = "DraftingCompass"
                st = inserir_texto(st, r' \} from "lucide-react";', ", DraftingCompass", "suites.js (ícone)")
            linhas = st.splitlines(keepends=True)
            idx = [i for i, l in enumerate(linhas) if re.search(r'^\s*id: "plantas",', l)]
            if len(idx) != 1 or linhas[idx[0] - 1].strip() != "{":
                raise ValueError(f'suites.js: app "plantas" encontrada {len(idx)}× ou formato inesperado')
            bloco = (
                "  {\n"
                "    // Regra do produto: toda a nova app de arquitetura ou de BIM vai para esta app.\n"
                f'    id: "arquiteto", to: "/arquiteto-bim", icon: {icone}, family: "plans", group: "chantiers", pin: true,\n'
                '    label: { pt: "Arquiteto & BIM", fr: "Architecte & BIM", en: "Architect & BIM" },\n'
                "    desc: {\n"
                '      pt: "Esboço à mão levantada, a partir de uma fotografia ou por prompt → modelo (plantas, alçados, cortes, 3D, DXF, IFC) → DCE completo (CCTP por lote + DPGF) em francês. BIM Studio e plantas BIM / Autodesk.",\n'
                '      fr: "Esquisse à main levée, depuis une photo de croquis ou par prompt → maquette (plans, façades, coupes, 3D, DXF, IFC) → DCE complet (CCTP par lot + DPGF) en français. BIM Studio et plans BIM / Autodesk.",\n'
                '      en: "Freehand sketch, photo of a sketch or prompt → model (plans, elevations, sections, 3D, DXF, IFC) → full tender package (CCTP per lot + DPGF) in French. BIM Studio and BIM / Autodesk plans.",\n'
                "    },\n"
                '    members: ["/atelier-arquiteto", "/bim", "/plans-pro"],\n'
                "  },\n")
            linhas.insert(idx[0] - 1, bloco)
            st = "".join(linhas)
            # o BIM sai de « Plantas, Medições & BIM » (passa para Arquiteto & BIM)
            n_rep = 0
            for a, b in (('"/plans-pro", "/bim", ', ""), ('"Plantas, Medições & BIM"', '"Plantas & Medições"'),
                         ('"Plans, métrés & BIM"', '"Plans & métrés"'), ('"Plans, take-off & BIM"', '"Plans & take-off"')):
                if st.count(a) == 1:
                    st = st.replace(a, b)
                    n_rep += 1
            avisos.append(f"· suites.js: app Arquiteto & BIM criada; {n_rep}/4 ajustes em « Plantas & Medições »")
            escritas["frontend/src/components/workspace/suites.js"] = st
    except (OSError, ValueError) as e:
        erros.append(f"✗ {e}")
    return erros, escritas, avisos


def inserir_texto(txt, ancora_re, add, nome):
    m = list(re.finditer(ancora_re, txt))
    if len(m) != 1:
        raise ValueError(f"{nome}: âncora encontrada {len(m)}× (esperado 1)")
    return txt[:m[0].start()] + add + txt[m[0].start():]


def aplicar(ref, dry):
    erros, escritas, avisos = plano(ref)
    for a in avisos:
        print(a)
    if erros:
        print("\nERROS — NADA FOI ESCRITO:")
        for e in erros:
            print(e)
        sys.exit(2)
    if dry:
        print(f"DRY-RUN OK — {len(escritas)} ficheiros seriam escritos:")
        for p in sorted(escritas):
            print("  ", "MOD" if os.path.exists(os.path.join(ROOT, p)) else "NOVO", p)
        return
    backup = {"criados": [], "alterados": {}, "pastas": []}
    for p in sorted(escritas):
        full = os.path.join(ROOT, p)
        if os.path.exists(full):
            backup["alterados"][p] = ler(p)
        else:
            backup["criados"].append(p)
    with open(BACKUP, "w", encoding="utf-8") as f:
        json.dump(backup, f)
    for p, txt in escritas.items():
        full = os.path.join(ROOT, p)
        d = os.path.dirname(full)
        falta = []
        while not os.path.isdir(d):
            falta.append(d)
            d = os.path.dirname(d)
        for x in reversed(falta):
            os.mkdir(x)
            backup["pastas"].append(x)
        with open(full, "w", encoding="utf-8") as f:
            f.write(txt)
    with open(BACKUP, "w", encoding="utf-8") as f:
        json.dump(backup, f)
    print(f"OK: {len(backup['criados'])} ficheiros novos + {len(backup['alterados'])} ficheiros com inserções "
          f"({', '.join(sorted(backup['alterados']))}). Cópia de segurança: {BACKUP}")


def rollback():
    with open(BACKUP, encoding="utf-8") as f:
        b = json.load(f)
    for p in b["criados"]:
        full = os.path.join(ROOT, p)
        if os.path.exists(full):
            os.remove(full)
    for p, txt in b["alterados"].items():
        with open(os.path.join(ROOT, p), "w", encoding="utf-8") as f:
            f.write(txt)
    for d in sorted(b.get("pastas", []), key=len, reverse=True):
        for sub in ("__pycache__",):
            sp = os.path.join(d, sub)
            if os.path.isdir(sp):
                for x in os.listdir(sp):
                    os.remove(os.path.join(sp, x))
                os.rmdir(sp)
        if os.path.isdir(d) and not os.listdir(d):
            os.rmdir(d)
    print(f"ROLLBACK OK: {len(b['criados'])} ficheiros removidos, {len(b['alterados'])} repostos.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if "--rollback" in sys.argv:
        rollback()
    else:
        aplicar(sys.argv[1], "--dry-run" in sys.argv)
