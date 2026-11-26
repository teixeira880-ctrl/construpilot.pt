"""Junta ao servidor .pt (código local mais recente do que o GitHub) o que falta para CLT e construção tradicional ficarem
ao nível do LSF, SEM substituir nada do que lá está:

- novos (copiados do ramo, recusados se já existirem): engines/clt/ (estudo CLT painel a painel: ligações, camadas, dossier,
  Excel, 3D, foto), engines/tradicional/estudo/ (estrutura de betão armado dimensionada elemento a elemento; a alvenaria é
  assente pelo motor engines/tradicional/engine.py JÁ EXISTENTE), engines/foto_estrutura.py, routes/clt_estudo.py,
  routes/tradicional_estudo.py, páginas CltStudies / TradicionalStudies e os testes;
- inserções por âncora nos ficheiros existentes (cada âncora tem de aparecer UMA vez): rotas no server.py e no App.js,
  entradas do menu, ligações a partir das páginas /construcao-tradicional e /clt-industrial, foto fotorrealista no LSF,
  ferramentas calcul_clt / calcul_tradicional do Assistente, opções do adaptador LSF;
- sem regras exclusivas da conta CLT Rezult (a conta continua): acompanhamento ao vivo para todas as contas profissionais,
  sem documentos forçados em inglês, sem desvio automático para o modelo Ucrânia, mesma cache para todos.

Uso (em /app, árvore limpa, sem cherry-pick/merge em curso):
    git fetch https://github.com/teixeira880-ctrl/construpilot.pt claude/estruturas-pod
    python3 scripts/apply_estruturas_pod_pt.py FETCH_HEAD          # ou o SHA

Atómico: prepara tudo em memória, verifica todas as âncoras e compila os .py alterados; se algo falhar mostra o contexto e
sai com código 2 SEM escrever nada. Idempotente: o que já estiver aplicado é saltado.
"""
import os
import py_compile
import subprocess
import sys
import tempfile

REV = sys.argv[1] if len(sys.argv) > 1 else "FETCH_HEAD"
FE, BE = "frontend/src", "backend"
errors, notes, writes = [], [], {}

NEW_DIRS = [f"{BE}/engines/clt", f"{BE}/engines/tradicional/estudo"]
NEW_FILES = [f"{BE}/engines/foto_estrutura.py", f"{BE}/routes/clt_estudo.py", f"{BE}/routes/tradicional_estudo.py",
             f"{BE}/tests/test_clt_motor.py", f"{BE}/tests/test_clt_routes_pt.py", f"{BE}/tests/test_tradicional_motor.py",
             f"{BE}/tests/test_tradicional_routes_pt.py", f"{FE}/pages/CltStudies.jsx", f"{FE}/pages/TradicionalStudies.jsx"]
# o motor de alvenaria do servidor é USADO, nunca substituído
MUST_EXIST = [f"{BE}/engines/tradicional/engine.py", f"{BE}/engines/lsf/adapter.py", f"{BE}/engines/lsf/geom.py", f"{BE}/engines/photoreal.py",
              f"{BE}/engines/calc_lots/structure.py", f"{BE}/engines/mep/adapter.py", f"{FE}/pages/Tradicional.jsx", f"{FE}/pages/CltIndustrial.jsx"]


def git(*a, binary=False):
    r = subprocess.run(["git", *a], capture_output=True)
    if r.returncode:
        return None
    return r.stdout if binary else r.stdout.decode("utf-8")


def read(p):
    if p in writes:
        return writes[p]
    with open(p, encoding="utf-8") as f:
        return f.read()


def ctx(p, needle):
    try:
        lines = read(p).splitlines()
    except OSError:
        return "(ficheiro inexistente)"
    key = needle.strip().splitlines()[0][:40]
    hits = [f"{i + 1}: {ln[:160]}" for i, ln in enumerate(lines) if key[:25] in ln]
    return "\n".join(hits[:8]) or f"(nenhuma linha com «{key[:25]}»)"


def edit(p, marker, anchor, text, mode="after_line", optional=False):
    """mode: after_line (insere a seguir à linha que contém a âncora), before_line, replace (substitui a âncora)."""
    try:
        s = read(p)
    except OSError:
        errors.append(f"{p}: ficheiro inexistente")
        return
    if marker and marker in s:
        notes.append(f"{p}: já aplicado ({marker[:50]})")
        return
    n = s.count(anchor)
    if n != 1:
        if optional:
            notes.append(f"{p}: âncora opcional encontrada {n}× — saltado: {anchor[:70]!r}")
            return
        errors.append(f"{p}: âncora encontrada {n}× (esperado 1): {anchor[:90]!r}\n{ctx(p, anchor)}")
        return
    i = s.index(anchor)
    if mode == "replace":
        s = s[:i] + text + s[i + len(anchor):]
    elif mode == "after_line":
        j = s.find("\n", i + len(anchor))
        j = len(s) if j < 0 else j + 1
        s = s[:j] + text + s[j:]
    elif mode == "before_line":
        j = s.rfind("\n", 0, i) + 1
        s = s[:j] + text + s[j:]
    writes[p] = s


# --------------------------------------------------------------------------------------------------- 0. pré-condições
if not os.path.isdir(".git") or not os.path.isdir(BE) or not os.path.isdir(FE):
    sys.exit("Correr em /app (raiz do repositório).")
for f in ("CHERRY_PICK_HEAD", "MERGE_HEAD", "REVERT_HEAD", "rebase-merge", "rebase-apply"):
    if os.path.exists(os.path.join(".git", f)):
        sys.exit(f"Operação git em curso (.git/{f}): termina-a primeiro. Nada escrito.")
st = git("status", "--porcelain", "--untracked-files=no") or ""
sujos = [ln for ln in st.splitlines() if ".emergent/" not in ln]
if sujos:
    sys.exit("Árvore com alterações por gravar (exceto .emergent):\n" + "\n".join(sujos[:20]) + "\nNada escrito.")
if git("rev-parse", "--verify", REV + "^{commit}") is None:
    sys.exit(f"Commit {REV} desconhecido: faz primeiro o git fetch do ramo claude/estruturas-pod. Nada escrito.")
for p in MUST_EXIST:
    if not os.path.exists(p):
        errors.append(f"{p}: devia existir neste servidor")

# --------------------------------------------------------------------------------------------------- 1. ficheiros novos
novos = list(NEW_FILES)
for d in NEW_DIRS:
    lst = git("ls-tree", "-r", "--name-only", REV, "--", d)
    if not lst:
        errors.append(f"{d}: não existe no commit {REV}")
        continue
    novos += [x for x in lst.splitlines() if "__pycache__" not in x]
binarios = {}
for p in novos:
    data = git("show", f"{REV}:{p}", binary=True)
    if data is None:
        errors.append(f"{p}: não existe no commit {REV}")
        continue
    if os.path.exists(p):
        with open(p, "rb") as f:
            if f.read() == data:
                notes.append(f"{p}: já presente (idêntico)")
                continue
        errors.append(f"{p}: JÁ EXISTE neste servidor com outro conteúdo — nada é substituído; rever à mão")
        continue
    binarios[p] = data

# --------------------------------------------------------------------------------------------------- 2. backend
edit(f"{BE}/server.py", "routes import tradicional_estudo",
     "api_router.include_router(tradicional_routes.router)",
     "from routes import tradicional_estudo as tradicional_estudo_routes  # noqa: E402  — construção tradicional: estudo completo (betão armado dimensionado + alvenaria), dossier, Excel, 3D, foto\n"
     "api_router.include_router(tradicional_estudo_routes.router)\n"
     "from routes import clt_estudo as clt_estudo_routes  # noqa: E402  — CLT: estudo painel a painel a partir da planta (ligações, camadas, prensa, dossier, Excel, 3D, foto)\n"
     "api_router.include_router(clt_estudo_routes.router)\n")

# LSF: opções do adaptador (espessuras de outro sistema construtivo — usadas pelos estudos CLT e tradicional)
edit(f"{BE}/engines/lsf/adapter.py", 'o.get("dtExt_mm")',
     "    out_off = (esp_int + dt_ext) / 1000.0            # m: face interior → face exterior da estrutura",
     '    if o.get("dtExt_mm"):                             # outro sistema construtivo (ex.: CLT) — espessuras próprias\n'
     '        dt_ext = float(o["dtExt_mm"])\n'
     '        out_off = (float(o.get("espInt_mm") or 0) + dt_ext) / 1000.0\n')
edit(f"{BE}/engines/lsf/adapter.py", 'o.get("profPiso_mm")',
     'prof_piso = viga["h"] + 2 * viga["t"] + pl_piso["esp"]',
     'prof_piso = float(o["profPiso_mm"]) if o.get("profPiso_mm") else viga["h"] + 2 * viga["t"] + pl_piso["esp"]', mode="replace")
# LSF: o dossier do Assistente usa a foto fotorrealista preparada pela ponte (todas as contas)
edit(f"{BE}/engines/lsf/note.py", 'a.get("_renders")',
     '    renders = []\n    if a.get("render", True):',
     '    renders = list(a.get("_renders") or [])          # render calculado + foto fotorrealista já preparados pela ponte do Assistente\n'
     '    if not renders and a.get("render", True):', mode="replace")
# LSF: foto fotorrealista a pedido (guardada à parte, invalidada quando o projeto muda)
edit(f"{BE}/routes/lsf.py", "/studies/{study_id}/photo",
     '@router.delete("/studies/{study_id}")',
     '@router.post("/studies/{study_id}/photo")\n'
     'async def study_photo(study_id: str, user=Depends(current_user)) -> Response:\n'
     '    """Foto fotorrealista da estrutura montada, a partir do render calculado (mesma geometria) — todas as contas Pro."""\n'
     '    import hashlib\n'
     '    import json as _json\n'
     '    doc = await _get(study_id, user["user_id"])\n'
     '    chave = hashlib.sha256(_json.dumps(doc.get("project"), sort_keys=True, default=str).encode()).hexdigest()\n'
     '    old = await db.lsf_photos.find_one({"study_id": study_id, "user_id": user["user_id"], "chave": chave}, {"_id": 0, "png_b64": 1})\n'
     '    if old:\n'
     '        img = base64.b64decode(old["png_b64"])\n'
     '    else:\n'
     '        st = await _full(doc, user["user_id"])\n'
     '        ren = await _render(doc, st, user["user_id"])\n'
     '        if not ren:\n'
     '            raise HTTPException(503, "Render indisponível neste servidor")\n'
     '        from engines.foto_estrutura import fotorrealista\n'
     '        r = await fotorrealista(ren[0][1], "lsf")\n'
     '        if not r:\n'
     '            raise HTTPException(503, "Motores de imagem indisponíveis — o render calculado continua disponível")\n'
     '        img = r[0]\n'
     '        await db.lsf_photos.update_one({"study_id": study_id, "user_id": user["user_id"]},\n'
     '                                       {"$set": {"chave": chave, "png_b64": base64.b64encode(img).decode()}}, upsert=True)\n'
     '    return Response(content=img, media_type="image/jpeg" if img[:3] == b"\\xff\\xd8\\xff" else "image/png")\n\n\n',
     mode="before_line")

# Assistente: ferramentas calcul_clt e calcul_tradicional (a calcul_lsf já existe)
O = f"{BE}/engines/calc_lots/outils.py"
edit(O, '"calcul_tradicional",', "CALC_TOOLS = [CLT_SO_TOOL,", '''# --------------------------------------------------------------------------------------------------------------------------------
# Estrutura em CLT a partir da planta lida — engines/clt (painel a painel, como o LSF)
CLT_TOOL = _tool(
    "calcul_clt",
    "Estudo ESTRUTURAL de uma construção em CLT / madeira lamelada-colada cruzada a partir da PLANTA LIDA no ConstruPilot (plan_id), da mesma "
    "forma que calcul_lsf: painéis de parede, laje, cobertura e empenas com a geometria real e os vãos recortados, volumes líquido / envolvente / "
    "de prensa e perda (plano de prensa), ligações contadas painel a painel (esquadros, hold-downs, parafusos de canto e de apoio, réguas de junta, "
    "fitas, bandas), isolamento e membranas (exceto com so_clt); mapa de quantidades com preços da biblioteca da empresa; dossier PDF com plantas, "
    "alçados de fabrico numerados e plano de prensa, Excel, visualizador 3D e foto fotorrealista. Para o dossier comercial da página CLT "
    "(preços, plano, rentabilidade) usa estudo_clt_completo; para só o custo de produção do CLT a partir do PDF dos planos usa clt_so_quantidades.",
    {"plan_id": _NS("planta já lida no ConstruPilot (plans_takeoff) — preferir sempre que exista"),
     "modelo_json": _NS("projeto CLT completo em JSON (formato engines.clt), se fornecido"),
     "implantacao": _obj({"comprimento_m": {"type": "number"}, "largura_m": {"type": "number"}, "pisos": _n("número de pisos"),
                          "pe_direito_m": {"type": ["array", "null"], "items": {"type": "number"}}}, "moradia retangular sem planta"),
     "vaos": _arr(_VAO_LSF, desc="vãos por fachada (só com implantacao)"),
     "inclinacao_graus": _n("cobertura de duas águas; null = 30"), "beiral_mm": _n("null = 500"),
     "cobertura": _enum(["auto", "duas_aguas", "plana"]),
     "produto": _enum(["generico_c24", "rezult_clt"], "produto CLT com ETA (prensa, classe); null = genérico C24"),
     "parede_exterior": _enum(["CLT80-3s", "CLT90-3s", "CLT100-3s", "CLT120-3s", "CLT140-5s"], "composição das paredes exteriores; null = CLT100-3s"),
     "parede_interior": _enum(["CLT80-3s", "CLT90-3s", "CLT100-3s", "CLT120-3s"], "composição das paredes interiores; null = CLT100-3s"),
     "so_clt": {"type": ["boolean", "null"], "description": "true = só o CLT e as suas ligações (sem isolamento, membranas…)"},
     "titulo": _NS(), "lingua": _enum(["pt", "fr", "en", "uk"], "língua do dossier (null = pt)"), "pais": _enum(["PT", "FR"])})

# Construção tradicional (betão armado dimensionado + alvenarias) — engines/tradicional/estudo
TRAD_TOOL = _tool(
    "calcul_tradicional",
    "Estudo completo de uma construção TRADICIONAL (estrutura porticada de betão armado + alvenarias de tijolo / bloco) a partir da planta: "
    "sapatas, vigas de fundação, pilares, vigas, lajes e cobertura dimensionados elemento a elemento (NP EN 1992-1-1 / 1997-1) com as cargas "
    "descidas piso a piso; betão, cofragem e aço pelos varões e malhas calculados; alvenarias assentes unidade a unidade (motor de alvenaria), "
    "vergas, pavimento térreo, ETICS, rebocos, telhas; mapa de quantidades POR PISO das fundações à cobertura (preços só da biblioteca da "
    "empresa); dossier PDF com plantas estruturais e alçado de cada parede, Excel, visualizador 3D e foto fotorrealista. "
    "Use plan_id quando a planta já foi lida no ConstruPilot; senão modelo_json; senão a implantação.",
    {"plan_id": _NS("planta já lida no ConstruPilot (plans_takeoff) — preferir sempre que exista"),
     "modelo_json": _NS("projeto completo em JSON (formato engines.tradicional.estudo), se fornecido"),
     "implantacao": _obj({"comprimento_m": {"type": "number"}, "largura_m": {"type": "number"}, "pisos": _n("número de pisos"),
                          "pe_direito_m": {"type": ["array", "null"], "items": {"type": "number"}}}, "moradia retangular sem planta"),
     "vaos": _arr(_VAO_LSF, desc="vãos por fachada (só com implantacao)"),
     "inclinacao_graus": _n("cobertura de duas águas; null = 30"), "beiral_mm": _n("null = 500"),
     "cobertura": _enum(["auto", "duas_aguas", "plana"]),
     "q_adm_kpa": _n("tensão admissível do terreno do estudo geotécnico (kPa); null = 200 kPa assinalado como hipótese"),
     "alvenaria_exterior": _enum(["T30x20x22", "T30x20x15", "B50x20x20", "B50x20x15"], "unidade das paredes exteriores; null = tijolo 30×20×22"),
     "alvenaria_interior": _enum(["T30x20x11", "T30x20x15", "B50x20x15"], "unidade das paredes interiores; null = tijolo 30×20×11"),
     "titulo": _NS(), "pais": _enum(["PT", "FR"])})

''', mode="before_line")
edit(O, "LSF_TOOL, CLT_TOOL, TRAD_TOOL]", "ESTUDO_CLT_TOOL, LSF_TOOL]", "ESTUDO_CLT_TOOL, LSF_TOOL, CLT_TOOL, TRAD_TOOL]", mode="replace")
edit(O, '"calcul_tradicional": "A dimensionar',
     '    "calcul_lsf": "A calcular a estrutura em aço leve (LSF) perfil a perfil, as placas e os parafusos…",',
     '    "calcul_clt": "A calcular a estrutura em CLT painel a painel, o plano de prensa e as ligações…",\n'
     '    "calcul_tradicional": "A dimensionar a estrutura de betão armado elemento a elemento e a assentar as alvenarias unidade a unidade…",\n')
edit(O, "calcul_tradicional, com plan_id", '"(os motores calculam, tu restituis).")',
     '"; estrutura CLT a partir da planta lida (painéis, ligações, prensa, alçados de fabrico): calcul_clt, com plan_id "\n'
     '    "; construção tradicional (betão armado + alvenaria: sapatas, pilares, vigas, lajes, tijolos, mapa por piso): calcul_tradicional, com plan_id "\n'
     '    "(os motores calculam, tu restituis).")', mode="replace", optional=True)
edit(O, 'if name == "calcul_tradicional":', '    raise ValueError(f"ferramenta de cálculo desconhecida: {name}")', '''    if name == "calcul_clt":
        from engines.clt import note as clt_note
        args_priv = {k: v for k, v in (args or {}).items() if k.startswith("_")}
        o = clt_note.note({**a, **args_priv})
        out_ = {"titre": o["titre"], "resume": o["resume"] + "\\n" + FIM, "pdf": o["pdf"], "png": o["png"], "data": o["data"]}
        if o.get("files_extra"):
            out_["files_extra"] = o["files_extra"]
        return out_
    if name == "calcul_tradicional":
        from engines.tradicional.estudo import note as trad_note
        args_priv = {k: v for k, v in (args or {}).items() if k.startswith("_")}
        o = trad_note.note({**a, **args_priv})
        return {"titre": o["titre"], "resume": o["resume"] + "\\n" + FIM, "pdf": o["pdf"], "png": o["png"], "data": o["data"],
                "files_extra": o["files_extra"]}
''', mode="before_line")

B = f"{BE}/engines/calc_lots/assistant_bridge.py"
edit(B, '"calcul_tradicional"):',
     '        if name == "calcul_lsf":                            # LSF: planta lida, marca e biblioteca de preços da empresa\n'
     '            args = await _lsf_contexto(dict(args or {}), uid, db)\n',
     '        if name in ("calcul_lsf", "calcul_clt", "calcul_tradicional"):   # planta lida, marca e biblioteca de preços da empresa\n'
     '            args = await _lsf_contexto(dict(args or {}), uid, db)\n'
     '            if (args or {}).get("render", True) is not False:   # render calculado + foto fotorrealista (todas as contas)\n'
     '                from engines.foto_estrutura import renders_assistente\n'
     '                args["_renders"] = await renders_assistente({"calcul_clt": "clt", "calcul_lsf": "lsf"}.get(name, "tradicional"), args)\n',
     mode="replace")
# sem regras da conta CLT Rezult: mesma cache para todas as contas; sem documentos forçados em inglês
edit(B, "igual para todas as contas",
     '    from engines import calc_live\n'
     '    # conta seguida ao vivo (CLT Rezult): recalcula sempre, para a página de acompanhamento mostrar o cálculo real\n'
     '    old = None if calc_live.ativo() else await db.assistant_artifacts.find_one(',
     '    # o mesmo pedido devolve o mesmo estudo (mesmos números) — igual para todas as contas\n'
     '    old = await db.assistant_artifacts.find_one(', mode="replace")
edit(B, "documentos na língua pedida",
     '            from bim_studio.clt_access import is_pilot\n'
     '            if is_pilot(user) and not args.get("lingua"):\n'
     '                args["lingua"] = "en"                         # the CLT Rezult account receives its documents in English\n',
     '            # documentos na língua pedida (ou a da conversa) — sem língua imposta a uma conta\n', mode="replace")

L = f"{BE}/engines/calc_live.py"
edit(L, "def acesso(",
     '''def is_clt(user: Optional[Dict[str, Any]]) -> bool:
    """Conta CLT Rezult (e as contas extra da variável CALC_LIVE_EMAILS, separadas por vírgulas)."""
    if not user:
        return False
    email = str(user.get("email") or "").strip().lower()
    extra = {e.strip().lower() for e in (os.environ.get("CALC_LIVE_EMAILS") or "").split(",") if e.strip()}
    return email in CLT_EMAILS or email in extra
''',
     '''def acesso(user: Optional[Dict[str, Any]]) -> bool:
    """Acompanhamento ao vivo: todas as contas profissionais (Pro, Pro Business, contas de empresa, admin) — mais as contas da
    variável CALC_LIVE_EMAILS (vírgulas). Sem regra exclusiva de uma conta."""
    if not user:
        return False
    if user.get("account_type") in ("pro", "pro_business") or user.get("role") == "admin" or user.get("company_id") or user.get("organization_id"):
        return True
    email = str(user.get("email") or "").strip().lower()
    extra = {e.strip().lower() for e in (os.environ.get("CALC_LIVE_EMAILS") or "").split(",") if e.strip()}
    return bool(email) and email in extra


is_clt = acesso          # nome antigo (rotas /calc-live e Assistente)
''', mode="replace")
edit(L, '"calcul_tradicional": "Motor',
     '    "generate_bet_lot_plans": "Planos de execução por especialidade",',
     '    "calcul_lsf": "Motor LSF — estrutura em aço leve perfil a perfil",\n'
     '    "calcul_clt": "Motor CLT — painéis, plano de prensa e ligações",\n'
     '    "calcul_tradicional": "Motor de construção tradicional — betão armado dimensionado e alvenaria unidade a unidade",\n')
edit(f"{BE}/engines/assistant_bet_core_tool.py", "sem desvio automático para o modelo Ucrânia",
     "    args = conta_clt_ua(user, name, args)\n",
     "    # sem desvio automático para o modelo Ucrânia por causa da conta (o utilizador escolhe o país do estudo)\n", mode="replace")

# --------------------------------------------------------------------------------------------------- 3. frontend
A = f"{FE}/App.js"
edit(A, "CltEstudoLazy", 'const CltIndustrialLazy = lazy(() => import("@/pages/CltIndustrial"));',
     'const CltEstudoLazy = lazy(() => import("@/pages/CltStudies"));\n'
     'const TradicionalEstudoLazy = lazy(() => import("@/pages/TradicionalStudies"));\n')
edit(A, 'path="/clt-industrial/estudo"', '<Route path="/clt-industrial" element=',
     '      <Route path="/clt-industrial/estudo" element={<ProRoute><Shell><Suspense fallback={<RouteSkeleton />}><CltEstudoLazy /></Suspense></Shell></ProRoute>} />\n'
     '      <Route path="/construcao-tradicional/estudo" element={<ProRoute><Shell><Suspense fallback={<RouteSkeleton />}><TradicionalEstudoLazy /></Suspense></Shell></ProRoute>} />\n')
N = f"{FE}/components/workspace/navigation.js"
edit(N, 'to: "/construcao-tradicional"', '{ to: "/estrutura-lsf", key: "nav.lsf",',
     '  { to: "/construcao-tradicional", label: "Construção tradicional (betão armado + alvenaria)", icon: Hammer, family: "etudes", group: "chantiers", pro: true, words: "construção tradicional betão armado alvenaria tijolo bloco pilares vigas sapatas lajes fundações medições mapa de quantidades por piso aço cofragem argamassa reboco lintéis" },\n'
     '  { to: "/clt-industrial", label: "Estrutura em CLT (madeira lamelada-colada cruzada)", icon: Hammer, family: "etudes", group: "chantiers", pro: true, words: "clt cross laminated timber x-lam madeira lamelada colada cruzada painéis madeira maciça m3 prensa plano de corte esquadros hold-down parafusos ligações quantidades fabrico" },\n')
edit(N, '"/construcao-tradicional": "', '  "/estrutura-lsf": "Estrutura em aço leve a partir da sua planta',
     '  "/construcao-tradicional": "Construção tradicional a partir da sua planta: alvenaria tijolo a tijolo e, no estudo completo, a estrutura de betão armado dimensionada elemento a elemento, mapa por piso, dossier, Excel, 3D e foto.",\n'
     '  "/clt-industrial": "Estrutura em CLT: medições, corte, 3D e fabrico, custos e seguimento; estudo painel a painel a partir da planta com ligações contadas, dossier, Excel e foto.",\n')
T = f"{FE}/pages/Tradicional.jsx"
edit(T, "Link, useSearchParams", 'import { useSearchParams } from "react-router-dom";', 'import { Link, useSearchParams } from "react-router-dom";', mode="replace")
edit(T, "/construcao-tradicional/estudo", "A estrutura de betão armado ainda não entra neste cálculo.",
     'A estrutura de betão armado (sapatas, pilares, vigas, lajes, cobertura) está no{" "}'
     '<Link to="/construcao-tradicional/estudo" className="underline font-medium" data-testid="trad-estudo-completo">estudo completo a partir da planta</Link>'
     ' — dossier, Excel, 3D e foto fotorrealista.', mode="replace")
C = f"{FE}/pages/CltIndustrial.jsx"
edit(C, "/clt-industrial/estudo", '<h1 className="text-2xl font-semibold">ConstruPilot CLT</h1>',
     '<h1 className="text-2xl font-semibold">ConstruPilot CLT</h1>\n'
     '      <a href="/clt-industrial/estudo" className={secondary} data-testid="clt-estudo-planta">Estudo painel a painel a partir da planta (ligações, dossier, Excel, 3D, foto)</a>',
     mode="replace")
S = f"{FE}/pages/LsfStudies.jsx"
edit(S, "lsf-foto", 'Procurar preços de mercado</Button>',
     '        <Button variant="outline" onClick={() => run("foto", async () => { const res = await api.post(`/lsf/studies/${study.study_id}/photo`, {}, { responseType: "blob" }); window.open(URL.createObjectURL(res.data), "_blank"); })} disabled={!!busy} data-testid="lsf-foto">\n'
     '          {busy === "foto" ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : null}Foto fotorrealista</Button>\n')

# --------------------------------------------------------------------------------------------------- 4. verificação e escrita
for p, s in writes.items():
    if p.endswith(".py"):
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as t:
            t.write(s)
        try:
            py_compile.compile(t.name, doraise=True)
        except py_compile.PyCompileError as e:
            errors.append(f"{p}: não compila depois das inserções: {e.msg[:300]}")
        finally:
            os.unlink(t.name)
for n in notes:
    print("·", n)
if errors:
    print("\nERROS — NADA FOI ESCRITO:")
    for e in errors:
        print("✗", e)
    sys.exit(2)
for p, data in binarios.items():
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)
for p, s in writes.items():
    with open(p, "w", encoding="utf-8") as f:
        f.write(s)
print(f"\nOK: {len(binarios)} ficheiros novos, {len(writes)} ficheiros existentes com inserções:")
for p in sorted(writes):
    print("  ~", p)
for p in sorted(binarios):
    print("  +", p)
