"""Instala o «fio do projeto» num pod ConstruPilot (.fr ou .pt).  Uso:  python instalar_fio.py fr|pt  (a partir de /app)

Pré-requisito: os ficheiros novos já copiados do ramo (backend/engines/fio_projeto/*, backend/routes/fio_projeto.py,
backend/tests/test_fio_projeto.py, frontend/src/components/fio/*).

Obrigatório (tudo-ou-nada): server.py (rota), routes/assistant.py (3 ferramentas + instruções), AtelierArchitecte.jsx
(painel do fio), Assistant.jsx (?atelier=<pid>). Opcional (avisa e salta): BimStudio.jsx (ligação da maquete + botão
Assistente), RenderFotorrealista.jsx (render e vista 3D guardados no dossier). Idempotente.
"""
import os
import re
import sys

LANG = (sys.argv[1] if len(sys.argv) > 1 else "").strip().lower()
if LANG not in ("fr", "pt"):
    sys.exit("uso: python instalar_fio.py fr|pt")
os.chdir(os.environ.get("APP_DIR", "/app")) if os.path.isdir(os.environ.get("APP_DIR", "/app")) else None

erros, avisos, escritas = [], [], {}


def ler(p):
    return escritas.get(p) or open(p, encoding="utf-8").read()


def um(s, old, new, rotulo, p, obrigatorio=True):
    n = s.count(old)
    if n == 1:
        return s.replace(old, new, 1)
    (erros if obrigatorio else avisos).append(f"{p}: âncora «{rotulo}» encontrada {n}× (esperado 1)")
    return s


for f in ("backend/engines/fio_projeto/servico.py", "backend/engines/fio_projeto/tools.py", "backend/engines/fio_projeto/termica.py", "backend/routes/fio_projeto.py",
          "frontend/src/components/fio/FioProjeto.jsx", "frontend/src/components/fio/fioAssistente.js"):
    if not os.path.isfile(f):
        erros.append(f"ficheiro novo em falta: {f}")
if erros:
    print("\n".join("ERRO " + e for e in erros))
    sys.exit(1)

# ------------------------------------------------------------------ 1) server.py — rota
P = "backend/server.py"
s = ler(P)
if "fio_projeto_routes" not in s:
    linhas = s.split("\n")
    idx = [i for i, l in enumerate(linhas) if "include_router(" in l and "atelier_archi" in l]
    if len(idx) != 1:
        erros.append(f"{P}: linha include_router do atelier_archi encontrada {len(idx)}×")
    else:
        l = linhas[idx[0]]
        ind = l[:len(l) - len(l.lstrip())]
        rec = re.match(r"\s*(\w+)\.include_router\(", l)
        pref = re.search(r"(,\s*prefix\s*=\s*['\"][^'\"]*['\"])", l)
        if not rec:
            erros.append(f"{P}: receptor do include_router não reconhecido: {l.strip()}")
        else:
            linhas[idx[0] + 1:idx[0] + 1] = [
                f"{ind}from routes import fio_projeto as fio_projeto_routes  # noqa: E402 — fio do projeto: Ateliê → BIM → térmica → execução → orçamento → dossier",
                f"{ind}{rec.group(1)}.include_router(fio_projeto_routes.router{pref.group(1) if pref else ''})"]
            escritas[P] = "\n".join(linhas)

# ------------------------------------------------------------------ 2) routes/assistant.py — ferramentas
P = "backend/routes/assistant.py"
s = ler(P)
formato = "function"
if "from engines.fio_projeto.tools import" in s:
    _lg = "backend/engines/fio_projeto/lingua.py"
    if os.path.isfile(_lg) and "anthropic" in open(_lg, encoding="utf-8").read():
        formato = "anthropic"
else:
    grupos = re.findall(r"^from engines\.([\w.]+)\.tools import (\w+)_INSTRUCTIONS, \2_TOOLS, \2_TOOL_NAMES, run_(\w+)_tool\s*$", s, re.M)
    escolhido = None
    for mod, X, run in sorted(grupos, key=lambda g: (g[1] not in ("MEP", "METRE"), g[1])):
        if s.count(f"*{X}_TOOLS,") == 1 and s.count(f"if name in {X}_TOOL_NAMES:") == 1:
            escolhido = (mod, X, run)
            break
    if not escolhido:
        erros.append(f"{P}: nenhum grupo de ferramentas «engines.X.tools» com âncoras únicas (vistos: {[g[1] for g in grupos]})")
    else:
        mod, X, run = escolhido
        src_tools = f"backend/engines/{mod.replace('.', '/')}/tools.py"
        if os.path.isfile(src_tools) and "input_schema" in open(src_tools, encoding="utf-8").read():
            formato = "anthropic"
        imp = re.search(rf"^from engines\.{re.escape(mod)}\.tools import .*$", s, re.M).group(0)
        s = s.replace(imp, imp + "\nfrom engines.fio_projeto.tools import FIO_INSTRUCTIONS, FIO_TOOLS, FIO_TOOL_NAMES, run_fio_tool", 1)
        m_lista = re.search(rf"^(\s*)\*{X}_TOOLS,\s*$", s, re.M)
        s = s[:m_lista.end()] + f"\n{m_lista.group(1)}*FIO_TOOLS," + s[m_lista.end():]
        m_h = re.search(rf"^(\s*)if name in {X}_TOOL_NAMES:\n(?:.*\n)*?\s*return await run_{run}_tool\((\w+), (\w+), (\w+), (\w+)", s, re.M)
        if m_h:
            ind, a, b, c, d = m_h.groups()
            novo = f"{ind}if name in FIO_TOOL_NAMES:\n{ind}    return await run_fio_tool({a}, {b}, {c}, {d})\n"
            pos = m_h.start()
            s = s[:pos] + novo + s[pos:]
        else:
            # despacho diferente (ex.: .pt, run_metre_tool síncrono): lê os nomes em uso na função que despacha
            m_if = re.search(rf"^(\s*)if name in {X}_TOOL_NAMES:\n", s, re.M)
            defs = list(re.finditer(r"^async def (\w+)\(([^)]*)\)", s[:m_if.start()], re.M)) if m_if else []
            if not m_if or not defs:
                erros.append(f"{P}: despacho de {X}_TOOL_NAMES não está dentro de uma função async")
            else:
                params = defs[-1].group(2)
                corpo = s[defs[-1].start():m_if.start()]
                nomes = set(re.findall(r"\b(\w+)\b", params))
                args_v = "args" if "args" in nomes else ("tool_input" if "tool_input" in nomes else None)
                if "user" in nomes:
                    user_v = "user"
                elif re.search(r"^\s*uid\s*=", corpo, re.M) or "uid" in nomes:
                    user_v = '{"user_id": uid}'
                else:
                    user_v = None
                if not args_v or not user_v or "name" not in nomes:
                    erros.append(f"{P}: não consegui identificar name/args/user na função {defs[-1].group(1)}({params.strip()[:120]})")
                else:
                    ind = m_if.group(1)
                    novo = f"{ind}if name in FIO_TOOL_NAMES:\n{ind}    return await run_fio_tool(name, {args_v}, {user_v}, db)\n"
                    s = s[:m_if.start()] + novo + s[m_if.start():]
                    avisos.append(f"{P}: despacho adaptado à função {defs[-1].group(1)} (user = {user_v})")
        occ = [m.start() for m in re.finditer(rf"\b{X}_INSTRUCTIONS\b", s)]
        expr = [o for o in occ if not s[s.rfind("\n", 0, o) + 1:o].lstrip().startswith("from ")]
        if not expr:
            erros.append(f"{P}: {X}_INSTRUCTIONS não aparece na montagem das instruções")
        else:
            o = expr[0]
            fim = o + len(f"{X}_INSTRUCTIONS")
            s = s[:fim] + ' + "\\n" + FIO_INSTRUCTIONS' + s[fim:]
        try:
            compile(s, P, "exec")
            escritas[P] = s
        except SyntaxError as e:
            erros.append(f"{P}: compilação falhou depois das alterações: {e}")

# lingua.py (língua do site + formato das ferramentas do pod)
escritas["backend/engines/fio_projeto/lingua.py"] = f'LANG = "{LANG}"\nFORMATO_TOOLS = "{formato}"\n'

# ------------------------------------------------------------------ 3) Ateliê — painel do fio
P = "frontend/src/pages/AtelierArchitecte.jsx"
s = ler(P)
if "components/fio/FioProjeto" not in s:
    ims = list(re.finditer(r"^import [^\n]*;\s*$", s, re.M))
    if not ims:
        erros.append(f"{P}: imports não encontrados")
    else:
        u = ims[-1]
        s = s[:u.end()] + '\nimport FioProjeto from "@/components/fio/FioProjeto";' + s[u.end():]
        m = list(re.finditer(r"^(\s*)<DcePanel [^\n]*/>\s*$", s, re.M))
        if len(m) != 1:
            erros.append(f"{P}: <DcePanel …/> encontrado {len(m)}×")
        else:
            lang_expr = "lang" if re.search(r"\bconst \{[^}]*\blang\b[^}]*\} = useI18n\(\)", s) else f'"{LANG}"'
            s = s[:m[0].end()] + f"\n{m[0].group(1)}<FioProjeto pid={{pid}} lang={{{lang_expr}}} />" + s[m[0].end():]
            escritas[P] = s

# ------------------------------------------------------------------ 4) Assistente — ?atelier=<pid>
P = "frontend/src/pages/Assistant.jsx"
s = ler(P)
if "components/fio/fioAssistente" not in s:
    s = um(s, 'import { toast } from "sonner";\n',
           'import { toast } from "sonner";\nimport { fioPrompt, useFioConversa } from "@/components/fio/fioAssistente";\n', "import toast", P)
    s = um(s, "(!chantierParam && lastConversation(", '(!chantierParam && !searchParams.get("atelier") && lastConversation(',
           "requestedConversation", P)
    m = re.search(r'useState\(\(\) => searchParams\.get\("resumeQuote"\)', s)
    pos_lang = s.find("useI18n()")
    if not m or pos_lang < 0 or pos_lang > m.start():
        erros.append(f"{P}: texto inicial (resumeQuote) não encontrado ou lang declarado depois")
    else:
        s = s[:m.start()] + 'useState(() => searchParams.get("atelier") ? fioPrompt(searchParams.get("atelier"), lang) : searchParams.get("resumeQuote")' + s[m.end():]
    s = um(s, "  }, [chantierParam]);\n", "  }, [chantierParam]);\n  useFioConversa(searchParams, setSearchParams);\n", "efeito chantierParam", P)
    escritas[P] = s

# ------------------------------------------------------------------ 5) opcionais
P = "frontend/src/pages/BimStudio.jsx"
if os.path.isfile(P):
    s = ler(P)
    if "fio-projeto" not in s and "fioAssistente" not in s:
        s0 = s
        m = re.search(r"window\.localStorage\.setItem\(cle, JSON\.stringify\(\{ model_id: res\.model_id, maj: majProjet \}\)\);[^\n]*\n", s)
        if m:
            ind = re.match(r"\s*", s[s.rfind("\n", 0, m.start()) + 1:]).group(0)
            s = s[:m.end()] + (f"{ind}api.post(`/fio-projeto/${{encodeURIComponent(atelierId)}}/ligar`, {{ campo: \"bim_model_id\", valor: res.model_id }}).catch(() => {{}});\n") + s[m.end():]
        else:
            avisos.append(f"{P}: ligação automática da maquete ao fio não instalada (âncora localStorage)")
        m = re.search(r"(<a [^>]*href=\{`/atelier-[a-z]+\?projet=\$\{encodeURIComponent\(atelier\.id\)\}`\}[^>]*>[^<]*</a>)", s)
        if m:
            rot = "Continuer dans l'Assistant →" if LANG == "fr" else "Continuar no Assistente →"
            s = s[:m.end()] + f'\n          <a className="text-primary font-semibold hover:underline" href={{`/assistant?atelier=${{encodeURIComponent(atelier.id)}}`}}>{rot}</a>' + s[m.end():]
        else:
            avisos.append(f"{P}: botão Assistente na faixa do Ateliê não instalado (âncora «Revenir/Voltar ao projeto»)")
        if s != s0:
            escritas[P] = s

P = "frontend/src/components/licenciamento/RenderFotorrealista.jsx"
if os.path.isfile(P):
    s = ler(P)
    if "guardarImagemNoFio" not in s:
        if s.count("setUrls({ antes, depois: data.imagem });") == 1 and s.count('import { promptDoModelo } from "./promptRender";') == 1:
            s = s.replace('import { promptDoModelo } from "./promptRender";',
                          'import { promptDoModelo } from "./promptRender";\nimport { guardarImagemNoFio } from "@/components/fio/fioAssistente";', 1)
            leg = ("Rendu réel", "Vue 3D") if LANG == "fr" else ("Render real", "Vista 3D")
            s = s.replace("setUrls({ antes, depois: data.imagem });",
                          "setUrls({ antes, depois: data.imagem });\n"
                          "        const pidFio = new URLSearchParams(window.location.search).get(\"projet\");   // projeto do Ateliê: render e vista 3D vão para o dossier\n"
                          "        if (pidFio && window.location.pathname.startsWith(\"/atelier-ar\")) {\n"
                          f"          guardarImagemNoFio(pidFio, blob, \"bim\", \"{leg[1]}\").catch(() => {{}});\n"
                          f"          guardarImagemNoFio(pidFio, data.imagem, \"render\", \"{leg[0]}\").catch(() => {{}});\n"
                          "        }", 1)
            escritas[P] = s
        else:
            avisos.append(f"{P}: gravação automática do render no dossier não instalada (âncoras)")

for a in avisos:
    print("AVISO", a)
if erros:
    for e in erros:
        print("ERRO", e)
    print("NADA FOI ESCRITO")
    sys.exit(1)
for p, conteudo in escritas.items():
    open(p, "w", encoding="utf-8").write(conteudo)
    print("OK", p)
print(f"FIO INSTALADO ({LANG}, ferramentas formato {formato})")
