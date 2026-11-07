"""Lote 109 PT — Interface v2 (construpilot.pt apenas).

Mesmas cores e marca (verde #285541, cobre #875133, creme), novo acabamento visual:
  1. Página inicial : cabeçalho em pílula de vidro, botões com profundidade, títulos com itálico cobre
     (Fraunces), pré-visualização em janela de app, passos e ferramentas em grelha "bento" com ícones
     coloridos, preços com cartão em destaque, FAQ em cartões, chamada final com malha de cor.
  2. Espaço de trabalho : barra lateral verde-escura com ícones coloridos, barra "Procurar" em destaque,
     cartões do painel e bloco "Hoje" redesenhados, barra inferior do telemóvel flutuante com botão central.
  3. Página de obra : novo fluxo "Plantas → Medição → Orçamento → Envio e assinatura → Obra e faturação"
     (componente ProjectFlow, só lê os dados já carregados; cada passo leva à ação certa).
  4. Acessibilidade : correções da auditoria (ver A11Y abaixo).

Só CSS + 1 componente novo + pequenas correções; nenhum endpoint, nenhuma dependência nova.
Idempotente. ARRÊT (nada escrito) se faltar a âncora obrigatória. Partes opcionais são saltadas com aviso.
Uso : python3 lots/l109_interface_v2/apply.py /app
"""
import pathlib
import shutil
import sys

root = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "/app")
here = pathlib.Path(__file__).resolve().parent
F = root / "frontend"
S = F / "src"
FILES = {
    "index": S / "index.js",
    "html": F / "public" / "index.html",
    "chantier": S / "pages" / "ChantierDetail.jsx",
}
EXTRA = {}  # preenchido pelas correções A11Y
T = {k: p.read_text(encoding="utf-8") for k, p in FILES.items()}
if "brand-v2.css" in T["index"]:
    print("já aplicado"); print("L109 OK"); sys.exit(0)


def stop(what):
    print("ÂNCORA não encontrada — ARRÊT, nada escrito:", what); sys.exit(1)


def rep(text, old, new, what, optional=False):
    if text.count(old) != 1:
        if optional:
            print("(opcional, ignorado)", what); return text, False
        stop(what)
    return text.replace(old, new, 1), True


# 1. Folha de estilos global — importada DEPOIS da App (fica por cima no cascade)
T["index"], _ = rep(T["index"], 'import App from "@/App";\n', 'import App from "@/App";\nimport "@/styles/brand-v2.css";\n', "index.js: import App")

# 2. Fonte Fraunces (itálico dos títulos) — opcional, há fallback Georgia
if "family=Fraunces" not in T["html"]:
    T["html"], _ = rep(T["html"], "&family=JetBrains+Mono:", "&family=Fraunces:ital,opsz,wght@1,9..144,400;1,9..144,500&family=JetBrains+Mono:", "index.html: link Google Fonts", optional=True)

# 3. Fluxo do projeto na página de obra — opcional (as duas âncoras ou nenhuma)
imp_old = 'import { ChantierCostsPanel } from "@/components/chantiers/ChantierCostsPanel";\n'
nav_old = '      <nav className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2 rounded-2xl'
if T["chantier"].count(imp_old) == 1 and T["chantier"].count(nav_old) == 1:
    T["chantier"] = T["chantier"].replace(imp_old, imp_old + 'import { ProjectFlow } from "@/components/chantiers/ProjectFlow";\n', 1)
    T["chantier"] = T["chantier"].replace(nav_old, '      <ProjectFlow c={c} chantierId={chantierId} onTab={selectTab} />\n' + nav_old, 1)
    flow = True
else:
    print("(opcional, ignorado) ChantierDetail.jsx: fluxo do projeto"); flow = False

# 4. Correções de acessibilidade (A11Y) — cada uma opcional
A11Y = []
exec((here / "a11y_fixes.py").read_text(encoding="utf-8")) if (here / "a11y_fixes.py").exists() else None

# Escrita (só chega aqui se nenhuma âncora obrigatória faltou)
shutil.copyfile(here / "brand-v2.css", S / "styles" / "brand-v2.css")
if flow:
    shutil.copyfile(here / "ProjectFlow.jsx", S / "components" / "chantiers" / "ProjectFlow.jsx")
for k, p in FILES.items():
    p.write_text(T[k], encoding="utf-8")
for p, text in EXTRA.items():
    p.write_text(text, encoding="utf-8")
print("A11Y aplicadas:", len(A11Y), *A11Y, sep="\n  ")
print("L109 OK")
