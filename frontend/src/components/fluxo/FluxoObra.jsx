import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { HardHat, ArrowRightLeft, Route as RouteIcon, X, Link2, Plus, ChevronDown, ChevronUp, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { usePermissions } from "@/context/PermissionContext";
import { useI18n } from "@/context/I18nContext";
import { meetsLevel, familyMemberLinks } from "@/components/workspace/navigation";
import { APP_FAMILIES, familyLabel, familyOfPath } from "@/components/workspace/families";
import { useToolLabel } from "@/components/workspace/FamilyTabs";
import { processoAtivo, definirProcessoAtivo, limparProcessoAtivo, paramsDoTrabalho, comProcesso } from "@/lib/processoAtivo";

// Fluxo de obra entre apps.
// Um processo de obra ativo acompanha o utilizador por TODAS as apps: o ?chantier=
// é reposto automaticamente em cada app, cada trabalho aberto (projeto do Ateliê,
// modelo BIM, plano medido, orçamento, estudo…) fica registado no percurso do
// processo, e a barra permite passar para qualquer outra app sem perder o fio.

const EXTRA = ["/assistant", "/devis-editeur", "/agents", "/acompanhamento-calculo", "/calc-live", "/appro", "/rentabilite", "/pc", "/analyse"];
const FERRAMENTAS = [...new Set([...APP_FAMILIES.flatMap(f => [f.to, ...f.members]), ...EXTRA])];
const corresponde = (p, to) => p === to || p.startsWith(to + "/");
const raizFerramenta = (p) => FERRAMENTAS.filter(to => corresponde(p, to)).sort((a, b) => b.length - a.length)[0] || null;

const NOMES = {
  "/atelier-arquiteto": "Ateliê Arquiteto", "/bim": "BIM Studio", "/plans-pro": "Plantas BIM", "/cctp": "CCTP / DCE",
  "/plan": "Medições em planta", "/devis-editeur": "Orçamento", "/assistant": "Assistente BTP", "/dpgf": "Mapa de quantidades",
  "/licenciamento-automatico": "Licenciamento automático", "/urbanismo": "Urbanismo", "/estudo-moradia": "Estudo de moradia",
  "/structuro": "Estrutura", "/planos-execucao": "Planos de execução", "/estudio-imagens": "Estúdio de imagens", "/rendu-ia": "Renders IA",
  "/suivi-chantier": "Acompanhamento de obra", "/planning": "Planeamento", "/situations": "Autos de medição", "/factures": "Faturas",
};

const T = {
  pt: { proc: "Processo", trocar: "Continuar noutra app", percurso: "Percurso", sair: "Sair do processo", ligar: "Ligar a um processo",
        escolher: "Escolha o processo de obra", novo: "Novo processo", nome: "Nome do processo", criar: "Criar", vazio: "Ainda não tem processos.",
        dica: "O trabalho segue consigo em todas as apps.", reduzir: "Reduzir", abrir: "Abrir barra do processo" },
  en: { proc: "Project", trocar: "Continue in another app", percurso: "Journey", sair: "Leave project", ligar: "Link to a project",
        escolher: "Choose the project", novo: "New project", nome: "Project name", criar: "Create", vazio: "No projects yet.",
        dica: "Your work follows you across every app.", reduzir: "Minimise", abrir: "Open project bar" },
  fr: { proc: "Dossier", trocar: "Continuer dans une autre app", percurso: "Parcours", sair: "Quitter le dossier", ligar: "Lier à un dossier",
        escolher: "Choisissez le dossier de chantier", novo: "Nouveau dossier", nome: "Nom du dossier", criar: "Créer", vazio: "Aucun dossier pour l'instant.",
        dica: "Votre travail vous suit dans toutes les apps.", reduzir: "Réduire", abrir: "Ouvrir la barre du dossier" },
  uk: { proc: "Проєкт", trocar: "Продовжити в іншому застосунку", percurso: "Маршрут", sair: "Вийти з проєкту", ligar: "Прив'язати до проєкту",
        escolher: "Оберіть проєкт", novo: "Новий проєкт", nome: "Назва проєкту", criar: "Створити", vazio: "Проєктів ще немає.",
        dica: "Ваша робота переходить з вами між застосунками.", reduzir: "Згорнути", abrir: "Відкрити панель проєкту" },
};

// Trabalhos já registados nesta sessão (evita pedidos repetidos ao navegar).
const registados = new Set();

export function nomeDaApp(pathname, lang = "pt") {
  const raiz = raizFerramenta(pathname);
  if (raiz && NOMES[raiz]) return NOMES[raiz];
  const fam = familyOfPath(pathname);
  return fam ? familyLabel(fam, lang) : pathname;
}

export function FluxoObra() {
  const { user } = useAuth();
  const { tier } = useBilling();
  const { can } = usePermissions();
  const { lang } = useI18n();
  const toolLabel = useToolLabel();
  const loc = useLocation();
  const nav = useNavigate();
  const t = T[lang] || T.pt;
  const pro = !!user && meetsLevel(user, tier, "pro");
  const raiz = raizFerramenta(loc.pathname);
  const naFerramenta = pro && !!raiz;
  const urlChantier = new URLSearchParams(loc.search).get("chantier") || "";

  const [ativo, setAtivo] = useState(() => (user ? processoAtivo(user.user_id) : null));
  const [menu, setMenu] = useState(null); // "apps" | "ligar" | null
  const [reduzida, setReduzida] = useState(() => { try { return sessionStorage.getItem("cp:fluxo-reduzida") === "1"; } catch { return false; } });
  const reinjecao = useRef({ path: "", n: 0, t: 0 });

  useEffect(() => {
    const sync = () => setAtivo(user ? processoAtivo(user.user_id) : null);
    sync();
    window.addEventListener("cp:processo-ativo", sync);
    window.addEventListener("storage", sync);
    return () => { window.removeEventListener("cp:processo-ativo", sync); window.removeEventListener("storage", sync); };
  }, [user]);

  useEffect(() => { setMenu(null); }, [loc.pathname]);

  // 1) Entrar numa app com ?chantier= torna esse processo o processo ativo.
  useEffect(() => {
    if (!naFerramenta || !urlChantier || ativo?.chantierId === urlChantier) return undefined;
    let vivo = true;
    api.get(`/chantiers/${urlChantier}`)
      .then(({ data }) => { if (vivo) definirProcessoAtivo(user.user_id, urlChantier, data?.name || ""); })
      .catch(() => { /* processo de outra conta ou apagado: ignora */ });
    return () => { vivo = false; };
  }, [naFerramenta, urlChantier, ativo?.chantierId, user]);

  // 2) Processo ativo + app sem ?chantier= → repor o processo no URL (o fio nunca se perde).
  useEffect(() => {
    if (!naFerramenta || !ativo || urlChantier) return;
    const r = reinjecao.current; const agora = Date.now();
    if (r.path === loc.pathname && agora - r.t < 3000) r.n += 1; else { r.path = loc.pathname; r.n = 1; }
    r.t = agora;
    if (r.n > 3) return; // a página reescreve os seus parâmetros: não entrar em ciclo
    const sp = new URLSearchParams(loc.search);
    sp.set("chantier", ativo.chantierId);
    nav({ pathname: loc.pathname, search: `?${sp.toString()}`, hash: loc.hash }, { replace: true, state: loc.state });
  }, [naFerramenta, ativo, urlChantier, loc.pathname, loc.search, loc.hash, loc.state, nav]);

  // 3) Cada trabalho aberto dentro do processo fica registado no percurso.
  useEffect(() => {
    if (!naFerramenta || !urlChantier) return undefined;
    const params = paramsDoTrabalho(loc.search);
    const temId = loc.pathname.length > (raiz || "").length;
    if (!Object.keys(params).length && !temId) return undefined;
    const chave = `${urlChantier}|${loc.pathname}|${JSON.stringify(params)}`;
    if (registados.has(chave)) return undefined;
    const timer = setTimeout(() => {
      registados.add(chave);
      api.post(`/chantiers/${urlChantier}/percurso`, {
        rota: loc.pathname, params, app: nomeDaApp(loc.pathname, "pt"), titulo: (document.title || "").slice(0, 200),
      }).catch(() => registados.delete(chave));
    }, 1500);
    return () => clearTimeout(timer);
  }, [naFerramenta, urlChantier, loc.pathname, loc.search, raiz]);

  const grupos = useMemo(() => {
    if (!pro) return [];
    return APP_FAMILIES.map(f => ({ id: f.id, label: familyLabel(f, lang), links: familyMemberLinks(f.id, user, can, tier) }))
      .filter(g => g.links.length);
  }, [pro, lang, user, can, tier]);

  if (!naFerramenta) return null;

  const assistente = loc.pathname === "/assistant";
  const pos = assistente
    ? "top-3 md:top-4"
    : "bottom-[calc(8.75rem+env(safe-area-inset-bottom))] md:bottom-4";
  const base = `fixed left-1/2 -translate-x-1/2 ${pos} z-40 max-w-[calc(100vw-1.5rem)]`;

  const sair = () => {
    limparProcessoAtivo();
    const sp = new URLSearchParams(loc.search); sp.delete("chantier");
    const qs = sp.toString();
    nav({ pathname: loc.pathname, search: qs ? `?${qs}` : "", hash: loc.hash }, { replace: true });
  };
  const alternarReduzida = (v) => { setReduzida(v); try { sessionStorage.setItem("cp:fluxo-reduzida", v ? "1" : "0"); } catch { /* */ } };

  // Sem processo ativo: oferecer ligar o trabalho aberto a um processo.
  if (!ativo && !urlChantier) {
    const temTrabalho = Object.keys(paramsDoTrabalho(loc.search)).length > 0 || loc.pathname.length > (raiz || "").length;
    if (!temTrabalho) return null;
    return <div className={base} data-testid="fluxo-obra-ligar">
      {menu === "ligar"
        ? <EscolherProcesso t={t} onFechar={() => setMenu(null)} onEscolher={(id, nome) => {
            definirProcessoAtivo(user.user_id, id, nome);
            nav(comProcesso(`${loc.pathname}${loc.search}${loc.hash}`, id), { replace: true });
          }} />
        : <button type="button" onClick={() => setMenu("ligar")} title={t.dica}
            className="inline-flex items-center gap-2 rounded-full border border-primary/30 bg-card/95 backdrop-blur px-3 py-2 text-xs font-medium shadow-lg hover:border-primary">
            <Link2 className="h-3.5 w-3.5 text-primary" />{t.ligar}
          </button>}
    </div>;
  }

  const id = urlChantier || ativo?.chantierId;
  const nome = (ativo?.chantierId === id && ativo?.nome) || "…";

  if (reduzida) {
    return <div className={base}>
      <button type="button" onClick={() => alternarReduzida(false)} aria-label={t.abrir} data-testid="fluxo-obra-reduzida"
        className="inline-flex items-center gap-2 rounded-full border border-primary/40 bg-card/95 backdrop-blur px-3 py-2 text-xs shadow-lg max-w-[70vw]">
        <HardHat className="h-3.5 w-3.5 text-primary shrink-0" /><span className="truncate font-semibold">{nome}</span><ChevronUp className="h-3.5 w-3.5" />
      </button>
    </div>;
  }

  return <div className={base} data-testid="fluxo-obra-barra">
    {menu === "apps" && <div className={`absolute left-1/2 -translate-x-1/2 ${assistente ? "top-full mt-2" : "bottom-full mb-2"} w-[min(92vw,640px)] max-h-[60vh] overflow-auto rounded-2xl border border-border bg-card shadow-2xl p-3`} data-testid="fluxo-obra-apps">
      <p className="text-xs text-muted-foreground mb-2">{t.dica}</p>
      <div className="grid sm:grid-cols-2 gap-3">
        {grupos.map(g => <div key={g.id}>
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">{g.label}</p>
          <div className="flex flex-col">
            {g.links.map(l => <Link key={l.to} to={comProcesso(l.to, id)} onClick={() => setMenu(null)}
              className={`rounded-lg px-2 py-1.5 text-sm hover:bg-secondary ${corresponde(loc.pathname, l.to) ? "font-semibold text-primary" : ""}`}
              data-testid={`fluxo-obra-app-${l.to.replace(/\W+/g, "-")}`}>{toolLabel(l)}</Link>)}
          </div>
        </div>)}
        <div>
          <p className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">ConstruPilot</p>
          <Link to={comProcesso("/assistant", id)} className="block rounded-lg px-2 py-1.5 text-sm hover:bg-secondary">Assistente BTP</Link>
          <Link to={comProcesso("/devis-editeur", id)} className="block rounded-lg px-2 py-1.5 text-sm hover:bg-secondary">{NOMES["/devis-editeur"]}</Link>
        </div>
      </div>
    </div>}
    <div className="flex items-center gap-1 rounded-full border border-primary/40 bg-card/95 backdrop-blur pl-3 pr-1 py-1 shadow-lg text-xs">
      <HardHat className="h-3.5 w-3.5 text-primary shrink-0" />
      <Link to={`/chantiers/${id}`} className="truncate max-w-[34vw] sm:max-w-[220px] hover:underline" data-testid="fluxo-obra-nome">
        <span className="text-muted-foreground hidden sm:inline">{t.proc}: </span><b>{nome}</b>
      </Link>
      <button type="button" onClick={() => setMenu(menu === "apps" ? null : "apps")} data-testid="fluxo-obra-trocar"
        className="ms-1 inline-flex items-center gap-1 rounded-full bg-primary text-primary-foreground px-2.5 py-1.5 font-medium">
        <ArrowRightLeft className="h-3.5 w-3.5" /><span className="hidden sm:inline">{t.trocar}</span>
      </button>
      <Link to={`/chantiers/${id}#percurso`} className="inline-flex items-center gap-1 rounded-full px-2 py-1.5 hover:bg-secondary" data-testid="fluxo-obra-percurso" title={t.percurso}>
        <RouteIcon className="h-3.5 w-3.5" /><span className="hidden md:inline">{t.percurso}</span>
      </Link>
      <button type="button" onClick={() => alternarReduzida(true)} aria-label={t.reduzir} title={t.reduzir} className="rounded-full p-1.5 hover:bg-secondary">
        <ChevronDown className="h-3.5 w-3.5" />
      </button>
      <button type="button" onClick={sair} aria-label={t.sair} title={t.sair} className="rounded-full p-1.5 hover:bg-secondary" data-testid="fluxo-obra-sair">
        <X className="h-3.5 w-3.5" />
      </button>
    </div>
  </div>;
}

function EscolherProcesso({ t, onEscolher, onFechar }) {
  const [lista, setLista] = useState(null);
  const [nome, setNome] = useState("");
  const [aCriar, setACriar] = useState(false);
  useEffect(() => {
    api.get("/chantiers").then(({ data }) => setLista(data?.chantiers || [])).catch(() => setLista([]));
  }, []);
  const criar = async () => {
    if (!nome.trim()) return;
    setACriar(true);
    try {
      const { data } = await api.post("/chantiers", { name: nome.trim().slice(0, 160) });
      if (data?.chantier_id) onEscolher(data.chantier_id, data.name || nome.trim());
    } catch { /* o erro de rede fica visível pelo botão que volta a ficar ativo */ }
    setACriar(false);
  };
  return <div className="w-[min(92vw,420px)] rounded-2xl border border-border bg-card shadow-2xl p-3" data-testid="fluxo-obra-escolher">
    <div className="flex items-center justify-between mb-2">
      <p className="text-sm font-semibold">{t.escolher}</p>
      <button type="button" onClick={onFechar} className="rounded-full p-1 hover:bg-secondary" aria-label="×"><X className="h-4 w-4" /></button>
    </div>
    <div className="max-h-[40vh] overflow-auto flex flex-col">
      {lista === null && <Loader2 className="h-4 w-4 animate-spin m-3" />}
      {lista?.length === 0 && <p className="text-xs text-muted-foreground p-2">{t.vazio}</p>}
      {(lista || []).slice(0, 50).map(c => <button key={c.chantier_id} type="button" onClick={() => onEscolher(c.chantier_id, c.name)}
        className="text-left rounded-lg px-2 py-1.5 text-sm hover:bg-secondary" data-testid={`fluxo-obra-processo-${c.chantier_id}`}>
        <b>{c.name}</b>{c.client_name ? <span className="text-muted-foreground"> · {c.client_name}</span> : null}
      </button>)}
    </div>
    <div className="mt-2 flex gap-2 border-t border-border pt-2">
      <input value={nome} onChange={e => setNome(e.target.value)} placeholder={t.nome} maxLength={160}
        onKeyDown={e => { if (e.key === "Enter") criar(); }}
        className="flex-1 min-w-0 rounded-lg border border-border bg-background px-2 py-1.5 text-sm" data-testid="fluxo-obra-novo-nome" />
      <button type="button" onClick={criar} disabled={aCriar || !nome.trim()} data-testid="fluxo-obra-criar"
        className="inline-flex items-center gap-1 rounded-lg bg-primary text-primary-foreground px-3 py-1.5 text-sm disabled:opacity-50">
        {aCriar ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}{t.criar}
      </button>
    </div>
  </div>;
}
