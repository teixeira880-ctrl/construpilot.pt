# Lote 109 PT — correções da auditoria de botões e acessibilidade.
# Executado por apply.py (usa rep, S, EXTRA, A11Y). Cada correção é opcional:
# se a âncora não existir no pod, é ignorada com aviso e o resto continua.
import re as _re


def _fix(rel, pairs, label):
    p = S / rel
    if not p.exists():
        print("(opcional, ignorado)", label, "— ficheiro ausente"); return
    text = EXTRA.get(p, p.read_text(encoding="utf-8"))
    changed = False
    for old, new, count in pairs:
        n = text.count(old)
        if n == 0 or (count and n != count):
            continue
        text = text.replace(old, new); changed = True
    if changed:
        EXTRA[p] = text; A11Y.append(label)
    else:
        print("(opcional, ignorado)", label)


# --- Botões/ligações mortos (levavam a páginas que não existem) ---
_fix("pages/ClientPortal.jsx", [("to={`/devis/signer/${q.signature_token}`}", "to={`/sign/${q.signature_token}`}", 0)],
     "Portal do cliente: botão «Assinar» levava a /devis/signer (inexistente) → /sign/:token")
_fix("pages/Payment.jsx", [('<Link to="/estimateur">', '<Link to="/estimation">', 0)],
     "Pagamento: «Criar um projeto» levava a /estimateur (inexistente) → /estimation")
_fix("pages/ProOffer.jsx", [('navigate("/register?intent=pro")', 'navigate("/inscription?signup=1&intent=pro")', 0)],
     "Oferta Pro: «Experimentar» sem sessão levava a /register (inexistente) → /inscription")
_fix("pages/ProjectDetail.jsx", [('navigate("/smart")', 'navigate("/smart-project")', 0)],
     "Projeto: «Gerar estimativa» levava a /smart (inexistente) → /smart-project")

# --- Inscrição: os botões «Experimentar» abriam o separador «Entrar» em vez de «Criar conta» ---
_fix("pages/Login.jsx", [('defaultValue={(params.get("email") || params.get("signup")) ? "register" : "login"}',
                          'defaultValue={(location.pathname === "/inscription" || params.get("email") || params.get("signup")) ? "register" : "login"}', 1)],
     "/inscription abre diretamente o separador «Criar conta»")

# --- Formulários: etiquetas ligadas aos campos (leitores de ecrã) + preenchimento automático ---
_lp = S / "pages" / "Login.jsx"
if _lp.exists():
    _t = EXTRA.get(_lp, _lp.read_text(encoding="utf-8"))
    _pat = _re.compile(r'<Label>([^<]*)</Label>(\s*\n\s*)<Input ((?:(?!data-testid|\bid=)[^>])*)data-testid="([^"]+)"')
    _n = len(_pat.findall(_t))
    if _n:
        _t = _pat.sub(lambda m: f'<Label htmlFor="{m.group(4)}">{m.group(1)}</Label>{m.group(2)}<Input id="{m.group(4)}" {m.group(3)}data-testid="{m.group(4)}"', _t)
        _t = _t.replace('type="email" value={form.email} onChange={set("email")} data-testid="login-email-input"', 'type="email" autoComplete="email" value={form.email} onChange={set("email")} data-testid="login-email-input"')
        _t = _t.replace('type="password" value={form.password} onChange={set("password")} data-testid="login-password-input"', 'type="password" autoComplete="current-password" value={form.password} onChange={set("password")} data-testid="login-password-input"')
        EXTRA[_lp] = _t; A11Y.append(f"Entrar/Criar conta: {_n} etiquetas ligadas aos campos + autocomplete")
    else:
        print("(opcional, ignorado) Login: etiquetas")

# --- Botões só com ícone, sem nome para leitores de ecrã ---
_fix("components/NotificationsBell.jsx", [('data-testid="notif-bell-btn"', 'data-testid="notif-bell-btn" aria-label="Notificações"', 1)],
     "Sino de notificações: nome acessível")
_fix("components/HelpChatbot.jsx", [('<button onClick={() => setOpen(true)} data-testid="help-chatbot-open"',
                                     '<button type="button" aria-label={t("help.open")} onClick={() => setOpen(true)} data-testid="help-chatbot-open"', 1)],
     "Botão «Precisa de ajuda?» no telemóvel (só ícone): nome acessível")
_fix("components/StarterChecklist.jsx", [('<button onClick={close} data-testid="checklist-dismiss"',
                                          '<button type="button" aria-label="Ocultar a lista de início" onClick={close} data-testid="checklist-dismiss"', 1)],
     "Lista de início: botão fechar com nome acessível")

# --- Nome acessível diferente do texto visível ---
_fix("components/landing/LandingLayout.jsx", [('aria-label="Entrar"', 'aria-label="Iniciar sessão"', 1)],
     "Cabeçalho: «Iniciar sessão» com o mesmo nome para voz/leitor de ecrã")
_fix("components/workspace/WorkspaceNavigation.jsx", [('data-testid="workspace-search-trigger" aria-label={ui("search")} ', 'data-testid="workspace-search-trigger" aria-label={`${ui("search")} Ctrl K`} ', 1)],
     "Barra de procura: nome acessível = texto visível")

_lt = S / "context" / "I18nContext.jsx"
if _lt.exists():
    _t = EXTRA.get(_lt, _lt.read_text(encoding="utf-8"))
    _old = '        aria-label="Mudar idioma"\n        aria-haspopup="menu"'
    if _t.count(_old) == 1:
        EXTRA[_lt] = _t.replace(_old, '        aria-label={`Mudar idioma: ${current.code_label}`}\n        aria-haspopup="menu"')
        A11Y.append("Botão de idioma: nome acessível inclui o idioma visível (PT)")
    else:
        print("(opcional, ignorado) Botão de idioma")
