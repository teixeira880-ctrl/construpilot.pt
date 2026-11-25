"""Coloca o módulo PIC numa página própria do menu, adaptando-se ao estado atual dos ficheiros.
Uso:  python3 apply_pic_placement.py pt|fr <sha_do_ramo>   (correr em /app)
Atómico: verifica todas as âncoras antes de escrever; se faltar alguma, mostra o contexto e sai com código 2."""
import re, subprocess, sys

lang, sha = sys.argv[1], sys.argv[2]
C = {
 "pt": dict(route="/plano-estaleiro", comp="PlanoEstaleiro", title="Plano de estaleiro",
   words="estaleiro plano de estaleiro grua lança alcance carga ponta contentor descarga vedação instalações sociais corte vertical altura sob gancho 3d vista aérea pss act folha técnica",
   benefit="Planta de estaleiro com grua calculada, zonas, corte vertical com alturas, vista 3D e folha técnica à escala.",
   tab='["pic", "Plano de estaleiro"], ', badge=" · Estaleiro"),
 "fr": dict(route="/installation-chantier", comp="InstallationChantier", title="Plan d'installation de chantier",
   words="pic plan d'installation de chantier grue flèche portée charge bout de flèche benne aire de livraison clôture base vie coupe verticale hauteur sous crochet 3d vue aérienne folio technique",
   benefit="PIC avec grue calculée, zones, coupe verticale avec hauteurs, vue 3D et folio technique à l'échelle.",
   tab='["pic", "Installation de chantier"], ', badge=None),
}[lang]
FE = "frontend/src"
errors, writes = [], {}

def read(p):
    return writes.get(p) or open(p, encoding="utf-8").read()

def ctx(p, pat):
    out = subprocess.run(["grep", "-n", "-E", pat, p], capture_output=True, text=True).stdout
    return out[:1500] or "(nada)"

# 0) page
page_path = f"{FE}/pages/{C['comp']}.jsx"
page = subprocess.run(["git", "show", f"{sha}:{page_path}"], capture_output=True, text=True)
if page.returncode:
    errors.append(f"git show {sha}:{page_path} falhou: {page.stderr.strip()}")
else:
    writes[page_path] = page.stdout

# 1) App.js : import + route (copiada da linha /planning)
p = f"{FE}/App.js"; s = read(p)
if C["route"] in s:
    print("App.js: rota já existe — sem alteração")
else:
    m = re.search(r'^[^\n]*<Route path="/planning"[^\n]*\n', s, re.M)
    if not m:
        errors.append("App.js: linha <Route path=\"/planning\" …> não encontrada\n" + ctx(p, "planning|Planning"))
    else:
        line = m.group(0)
        uses_suspense_import = "Suspense" in s and "RouteSkeleton" in s and re.search(r"\blazy\b", s)
        if uses_suspense_import:
            decl = f'const {C["comp"]} = lazy(() => import("@/pages/{C["comp"]}"));\n'
            el = f"<{C['comp']} />" if "Suspense" in line else f"<Suspense fallback={{<RouteSkeleton />}}><{C['comp']} /></Suspense>"
        else:
            decl = f'import {C["comp"]} from "@/pages/{C["comp"]}";\n'
            el = f"<{C['comp']} />"
        new = line.replace('path="/planning"', f'path="{C["route"]}"')
        new2 = re.sub(r"<Planning\s*/>", el, new)
        if new2 == new:
            errors.append("App.js: <Planning /> não encontrado na linha da rota:\n" + line)
        else:
            s = s[:m.end()] + new2 + s[m.end():]
            mi = re.search(r'^(?:const Planning = lazy\([^\n]*|import Planning from [^\n]*)\n', s, re.M)
            if not mi:
                mi = list(re.finditer(r'^(?:const \w+ = lazy\(\(\) => import\([^\n]*|import \w+ from "@/pages/[^\n]*)\n', s, re.M))
                mi = mi[-1] if mi else None
            if not mi:
                errors.append("App.js: sítio para o import não encontrado")
            else:
                s = s[:mi.end()] + decl + s[mi.end():]
                writes[p] = s

# 2) navigation.js : entrada do menu + benefício + ícone
p = f"{FE}/components/workspace/navigation.js"; s = read(p)
if f'to: "{C["route"]}"' in s:
    print("navigation.js: entrada já existe — sem alteração")
else:
    m = re.search(r'^[ \t]*\{ to: "/planning",[^\n]*\n', s, re.M)
    if not m:
        errors.append('navigation.js: entrada { to: "/planning", … } não encontrada\n' + ctx(p, "/planning|suivi-chantier"))
    else:
        line = m.group(0)
        indent = re.match(r"[ \t]*", line).group(0)
        extra = ""
        for k in ("family", "group", "suite", "hub"):
            mk = re.search(rf'\b{k}: "([^"]+)"', line)
            if mk:
                extra += f'{k}: "{mk.group(1)}", '
        if "group:" not in extra:
            extra += 'group: "chantiers", '
        entry = f'{indent}{{ to: "{C["route"]}", label: "{C["title"]}", icon: Construction, {extra}pro: true, pin: true, words: "{C["words"]}" }},\n'
        s = s[:m.end()] + entry + s[m.end():]
        mb = re.search(r'^[ \t]*"/planning": [^\n]*\n', s, re.M)
        if mb:
            ind = re.match(r"[ \t]*", mb.group(0)).group(0)
            s = s[:mb.end()] + f'{ind}"{C["route"]}": "{C["benefit"]}",\n' + s[mb.end():]
        else:
            print("navigation.js: sem mapa de benefícios para /planning — benefício não adicionado")
        ml = re.search(r'import \{([^}]*)\} from "lucide-react";', s)
        if not ml:
            errors.append("navigation.js: import de lucide-react não encontrado")
        elif not re.search(r"\bConstruction\b", ml.group(1)):
            body = ml.group(1).rstrip()
            sep = "" if body.endswith(",") else ","
            s = s[:ml.start(1)] + body + f"{sep} Construction " + s[ml.end(1):]
        writes[p] = s

# 3) PT : família «obra», se o ficheiro existir
if lang == "pt":
    p = f"{FE}/components/workspace/families.js"
    try:
        s = read(p)
    except FileNotFoundError:
        s = None
        print("families.js: ausente neste servidor — saltado (a entrada no menu chega)")
    if s and C["route"] not in s:
        m = re.search(r'members: \[([^\]]*"/planning"[^\]]*)\]', s)
        if m:
            s = s[:m.end(1)] + f', "{C["route"]}"' + s[m.end(1):]
            writes[p] = s
        else:
            print("families.js: família com /planning não encontrada — saltado")

# 4) TechAnalysis : retirar o separador duplicado
p = f"{FE}/pages/TechAnalysis.jsx"; s = read(p)
if C["tab"] in s:
    s = s.replace(C["tab"], "")
    s = re.sub(r'^[ \t]*\{tab === "pic" && <PicTab[^\n]*\n', "", s, flags=re.M)
    s = re.sub(r'^import PicTab from "@/components/tech/PicTab";\n', "", s, flags=re.M)
    if C["badge"]:
        s = s.replace(C["badge"], "")
    writes[p] = s
else:
    print("TechAnalysis.jsx: separador PIC não presente — sem alteração")

if errors:
    print("STOP — nada foi escrito:\n" + "\n\n".join(errors))
    sys.exit(2)
for path, text in writes.items():
    open(path, "w", encoding="utf-8").write(text)
    print("escrito:", path)
