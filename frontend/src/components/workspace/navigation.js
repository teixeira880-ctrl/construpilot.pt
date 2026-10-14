import { AssistantMark } from "@/components/assistant/AssistantMark";
import { Trash2, Bot, LayoutDashboard, FileText, Calculator, Ruler, Search, Users, HardHat, Building2, Receipt, Layers, Camera, Truck, Wand2, Radar, Contact, Library, Tag, Brain, KeyRound, Sparkles, Wrench, FileSearch, MessageSquare, Handshake, TrendingUp, Inbox, Shield, Globe, LifeBuoy, FileSpreadsheet, Footprints, Leaf, CalendarRange } from "lucide-react";

export const AssistantIcon = ({ size = 18, className = "" }) => (
  <AssistantMark size={size} className={className} />
);

// A single catalogue drives the sidebar, search and mobile navigation.
// These visibility rules complement the existing server/route permissions.
export const WORKSPACE_LINKS = [
  { to: "/dashboard", key: "nav.dashboard", label: "Painel", ui: "home", icon: LayoutDashboard, group: "today", pin: true },
  { to: "/assistant", key: "nav.assistant", label: "Assistente Construção", ui: "assistant", icon: AssistantIcon, group: "assistant", pin: true, min: "particulier_payant", upsell: true, words: "chat ajuda e-mail carta relatório aurora assistente construção" },
  { to: "/chantiers", key: "nav.chantiers", label: "Dossiers de obra", icon: HardHat, group: "chantiers", pro: true, pin: true, words: "processo obra cliente plantas orçamento fotografias dossier" },
  { to: "/devis", key: "nav.tracking", label: "Acompanhamento de orçamentos", ui: "quotes", icon: FileText, group: "billing", pro: true, perm: "devis", pin: true },
  { to: "/devis-editeur", key: "nav.newquote", label: "Novo orçamento", ui: "newQuote", icon: FileText, group: "billing", pro: true, perm: "devis", upsell: true, pin: true },
  { to: "/factures", key: "nav.invoices", label: "Faturas", icon: Receipt, group: "billing", pro: true, perm: "factures", pin: true },
  { to: "/clients", key: "nav.clients", label: "Clientes", icon: Contact, group: "clients", pro: true, pin: true },
  { to: "/corbeille", key: "nav.trash", label: "Lixo", icon: Trash2, group: "account", pro: true, words: "eliminado recuperar restaurar orçamento apagado" },
  { to: "/situations", key: "nav.situations", label: "Autos de medição", icon: Layers, group: "billing", min: "business", perm: "situations" },
  { to: "/dpgf", key: "nav.dpgf", label: "Mapa de quantidades do arquiteto → orçamento", icon: FileSpreadsheet, group: "billing", pro: true, perm: "devis", pin: true, words: "mapa quantidades orçamento excel caderno encargos concurso subempreiteiro orçamentação arquiteto" },
  { to: "/analyse-documents", key: "nav.docintel", label: "Análise de documentos", icon: FileSearch, group: "billing", pro: true, pin: true, words: "mapa quantidades orçamento pdf excel proveniência verificação iva quantidades fórmula fonte caderno encargos fatura leitura" },
  { to: "/plan", key: "nav.plan2d", label: "Plantas e medições", ui: "plan", icon: Ruler, group: "chantiers", pro: true, pin: true, upsell: true, words: "pdf dwg dxf áreas medição medições" },
  { to: "/agents", key: "nav.agents", label: "Pilote ConstruPilot", icon: Bot, group: "assistant", pin: true, personalPin: true, words: "agente automático processo orçamento medição deteção comparação segundo plano tarefa automatização" },
  { to: "/renovation", key: "nav.renovation", label: "Renovação energética", icon: Leaf, group: "chantiers", pro: true, pin: true, words: "renopilot energia certificado energético auditoria isolamento térmico cenários remodelação" },
  { to: "/structuro", key: "nav.structuro", label: "StructuroPilot (estudo)", icon: Building2, group: "chantiers", pro: true, words: "estrutura viga parede resistente abertura sapata estudo descida de cargas ipe hea heb gabinete projeto eurocódigo" },
  { to: "/estudo-moradia", key: "nav.house", label: "Estudo estrutural de moradia", icon: Building2, group: "chantiers", pro: true, pin: true, words: "laje armaduras cofragem sapata lintel cinta pilarete betão armado plano de execução gros oeuvre ferraillage moradia estrutura" },
  { to: "/structuro-bet", key: "nav.betdossier", label: "Análise de processo de engenharia", icon: FileSearch, group: "chantiers", pro: true, pin: true, words: "gabinete projeto engenharia memória cálculo revisão índice incoerência controlo planta comparar versões processo" },
  { to: "/btp-solver", key: "nav.solver", label: "Resolver um problema", icon: Wrench, group: "chantiers", pin: true, words: "fissura humidade patologia diagnóstico solução" },
  { to: "/plans-pro", key: "nav.plansPro", label: "Plantas BIM / Autodesk", icon: Layers, group: "chantiers", min: "pro", pin: false, words: "autodesk revit ifc visão quantidades paredes portas janelas" },
  { to: "/controle-cotes", key: "nav.cotes", label: "Controlo das cotas", icon: Ruler, group: "chantiers", pro: true, pin: false, words: "paredes dimensões interior planta" },
  { to: "/escaliers", key: "nav.stairs", label: "Cálculo de escadas", icon: Footprints, group: "chantiers", pro: true, pin: true, words: "escada degraus cobertor espelho blondel rgeu quarto de volta helicoidal betão armado lanço armaduras" },
  { to: "/suivi-chantier", key: "nav.site", label: "Acompanhamento de obra", icon: HardHat, group: "chantiers", pro: true, perm: "chantier", pin: true },
  { to: "/planning", label: "Planeamento de obra", icon: CalendarRange, group: "chantiers", pro: true, pin: true, words: "planeamento gantt caminho crítico equipas atraso replaneamento sequenciamento or-tools prazos" },
  { to: "/plan/compare", label: "Comparar plantas", icon: Layers, group: "chantiers", pro: true },
  { to: "/appro", key: "nav.appro", label: "Análise técnica & Aprovisionamento IA", icon: Truck, group: "chantiers", pro: true, words: "aço armaduras fornecedores encomenda" },
  { to: "/rendu-ia", key: "nav.render", label: "Renderização IA (antes/depois)", icon: Wand2, group: "chantiers", min: "particulier_payant" },
  { to: "/etudes-pc", key: "nav.studies", label: "Estudos de licença", icon: FileSearch, group: "chantiers", pro: true, words: "licença construção" },
  { to: "/mesure-photo", key: "nav.photomeasure", label: "Medir em fotografia", icon: Camera, group: "chantiers", min: "particulier_payant" },
  { to: "/estimation", key: "nav.estimator", label: "Estimador", ui: "estimate", icon: Calculator, group: "today", personalPin: true },
  { to: "/smart-project", label: "Smart Project", ui: "smart", icon: Sparkles, group: "today" },
  { to: "/precos", key: "nav.prices", label: "Preços de materiais", icon: Search, group: "library", personalPin: true },
  { to: "/calculadoras", key: "nav.calculators", label: "Calculadoras", icon: Calculator, group: "library", personalPin: true },
  { to: "/scanner-devis", key: "nav.scanner", label: "Scanner de orçamentos", icon: FileSearch, group: "billing", subscriber: true },
  { to: "/entreprise", key: "nav.company", label: "Espaço Empresa", icon: Building2, group: "account", min: "business", perm: "entreprise" },
  { to: "/ma-page", key: "nav.myPage", label: "A minha página & documentos", icon: Globe, group: "clients", pro: true, pin: true, words: "site montra página pública cabeçalho rodapé pdf personalização fotografias obras realizadas" },
  { to: "/equipe", key: "nav.team", label: "Equipa", icon: Users, group: "account", min: "business" },
  { to: "/rh", key: "hr.nav", label: "RH — Ponto", icon: Users, group: "account", min: "business", perm: "rh" },
  { to: "/mon-catalogue", key: "nav.catalog", label: "Catálogo de preços", icon: Tag, group: "library", pro: true, perm: "catalogue" },
  { to: "/bibliotheque", key: "nav.library", label: "Biblioteca", icon: Library, group: "library", pin: true, pro: true },
  { to: "/rentabilite", label: "Relatório de rentabilidade", icon: TrendingUp, group: "billing", pro: true, perm: "factures" },
  { to: "/factures-electroniques", label: "Faturação eletrónica", icon: Receipt, group: "billing", pro: true, perm: "factures" },
  { to: "/mes-demandes", key: "nav.myleads", label: "Os meus pedidos", icon: Inbox, group: "clients", pin: true, pro: true },
  { to: "/radar", key: "nav.radar", label: "Radar Obras", icon: Radar, group: "clients", pro: true },
  { to: "/mes-avis", key: "nav.reviews", label: "Opiniões de clientes", icon: MessageSquare, group: "clients", pro: true },
  { to: "/fournisseur", label: "Espaço fornecedor", icon: Truck, group: "account", pro: true },
  { to: "/photo", key: "nav.photo", label: "Análise de fotografia", icon: Camera, group: "discover" },
  { to: "/coach", key: "nav.coach", label: "Coach IA", icon: MessageSquare, group: "assistant" },
  { to: "/diy", key: "nav.diy", label: "Faço eu mesmo", icon: Wrench, group: "discover", personalPin: true },
  { to: "/particulares/autorizacao-obras", label: "Autorização de obras", icon: Shield, group: "discover", words: "licenciamento comunicação prévia escassa relevância rjue dl 555 obra licença câmara" },
  { to: "/marketplace", key: "nav.marketplace", label: "Encontrar um profissional", icon: Wrench, group: "discover", personalPin: true },
  { to: "/blog", key: "nav.blog", label: "Blog", icon: FileSearch, group: "discover" },
  { to: "/fonctionnalites", key: "nav.features", label: "Funcionalidades", icon: Sparkles, group: "discover" },
  { to: "/comparatif", key: "nav.compare", label: "Comparativo", icon: Tag, group: "discover" },
  { to: "/docs", key: "nav.docs", label: "API e Programadores", icon: FileSearch, group: "discover", min: "business" },
  { to: "/developpeurs", label: "Chaves API", icon: KeyRound, group: "account", min: "business" },
  { to: "/preferences", key: "nav.preferences", label: "Memória e preferências", ui: "preferences", icon: Brain, group: "account" },
  { to: "/compte", key: "nav.account", label: "A minha conta", ui: "account", icon: KeyRound, group: "account" },
  { to: "/planos", key: "nav.pricing", label: "Preços & subscrição", ui: "subscription", icon: Sparkles, group: "account" },
  { to: "/inviter", key: "nav.referral", label: "Recomendar", icon: Handshake, group: "account" },
  { to: "/investisseurs", key: "nav.investors", label: "Investidores", icon: Handshake, group: "discover" },
  { to: "/aide", key: "nav.help", label: "Ajuda e assistência", icon: LifeBuoy, group: "discover", words: "aide support assistance contact faq help ajuda" },
  { to: "/admin", key: "nav.admin", label: "Administração", icon: Shield, group: "account", admin: true },
  { to: "/admin/despesas", label: "Despesas das APIs", icon: Receipt, group: "account", admin: true, pin: true, words: "despesas custos budget autodesk ctt correio" },
  { to: "/admin/growth", label: "Growth · SEO & IA", icon: TrendingUp, group: "account", admin: true, pin: true, words: "growth seo visibilidade ia referenciação conteúdos blogue auditoria" },
];
export const WORKSPACE_GROUPS = ["favorites", "today", "chantiers", "billing", "clients", "library", "assistant", "discover", "account"];
// Keep every specialist tool available in the directory; only daily work is pinned.
export const workspaceEssentials = (links, professional) => {
  const paths = professional
    ? ["/dashboard", "/chantiers", "/plan", "/agents", "/devis", "/factures", "/clients", "/assistant"]
    : ["/dashboard", "/estimation", "/assistant", "/agents", "/calculadoras", "/precos", "/marketplace"];
  return paths.map(path => links.find(item => item.to === path && !item.locked)).filter(Boolean);
};
const RANK = { particulier_gratuit: 0, particulier_payant: 1, pro: 2, business: 3 };
const _levelOf = (user, tier) => {
  if (!user) return "particulier_gratuit";
  if (user.role === "admin") return "business";
  const base = user.account_type === "pro_business" ? "business"
    : user.account_type === "pro" ? "pro" : "particulier_gratuit";
  const fromTier = { pro_business: "business", pro: "pro", premium: "particulier_payant", project_pass: "particulier_payant" }[tier];
  let level = fromTier && RANK[fromTier] > RANK[base] ? fromTier : base;
  // Séparation stricte : un compte particulier ne dépasse jamais "particulier_payant"
  // (le mode promo gratuit ne transforme pas un particulier en pro/business).
  const isPart = user.account_type !== "pro" && user.account_type !== "pro_business";
  if (isPart && RANK[level] > RANK["particulier_payant"]) level = "particulier_payant";
  return level;
};
const _minLevel = (item) => item.min || (item.pro ? "pro" : item.subscriber ? "particulier_payant" : "particulier_gratuit");
// Source de vérité partagée (aligne le frontend sur engines/access.py).
export const LEVEL_RANK = RANK;
export const accountLevel = (user, tier) => _levelOf(user, tier);
export const meetsLevel = (user, tier, minimum) => RANK[_levelOf(user, tier)] >= RANK[minimum];
export const isProfessional = (user) => Boolean(user) && (user.account_type === "pro" || user.account_type === "pro_business" || user.role === "admin");
export const LEVEL_LABELS = { particulier_payant: "Particular Pagante", pro: "Pro", business: "Business" };
export const UPSELL_BENEFITS = {
  "/assistant": "Redija orçamentos, cartas e relatórios em segundos com a IA da construção.",
  "/devis-editeur": "Crie orçamentos e faturas profissionais, detalhados e conformes.",
  "/devis": "Acompanhe o estado dos seus orçamentos: enviados, aceites, relançados.",
  "/factures": "Emita as suas faturas e acompanhe os pagamentos, IVA incluído.",
  "/clients": "Centralize os seus clientes, o seu histórico e os seus documentos.",
  "/chantiers": "Reúna plantas, fotografias, orçamentos e acompanhamento por obra.",
  "/plan": "Meça áreas e quantidades diretamente nas suas plantas PDF/DWG.",
  "/agents": "Lance agentes que reúnem plantas, medições, orçamentação e PDF em segundo plano.",
  "/renovation": "Auditoria energética, cenários de remodelação e apoios.",
  "/structuro": "Estruture um estudo: recolha guiada, rastreabilidade das fontes.",
  "/estudo-moradia": "Pré-dimensionamento de moradia: lajes, sapatas, lintéis, escadas e dossier PDF com desenhos.",
  "/structuro-bet": "Controle um processo de engenharia: revisões, incoerências e relatório de controlo.",
  "/plans-pro": "Análise de plantas Pro: quantidades de paredes/portas/janelas por IA.",
  "/controle-cotes": "Verifique automaticamente as cotas e dimensões das plantas.",
  "/escaliers": "Cálculo de escadas conforme o RGEU e o DL 163/2006 (lei de Blondel).",
  "/suivi-chantier": "Acompanhe o avanço, as notas e as fotografias de obra.",
  "/planning": "Gantt determinístico: caminho crítico, equipas, replaneamento e propostas de reorganização.",
  "/dpgf": "Transforme um mapa de quantidades do arquiteto num orçamento detalhado automaticamente.",
  "/analyse-documents": "Verifique a proveniência, o IVA e as quantidades dos seus documentos.",
  "/situations": "Faturação por autos de medição com dedução do adiantamento.",
  "/appro": "Análise técnica e encomenda de aprovisionamento assistida.",
  "/rendu-ia": "Gere um render antes/depois realista das suas obras.",
  "/mesure-photo": "Meça elementos diretamente numa fotografia.",
  "/etudes-pc": "Prepare os seus processos de licenciamento mais depressa.",
  "/entreprise": "Faça a gestão da sua empresa: KPIs, membros, funções.",
  "/equipe": "Convide a sua equipa e gira os acessos por função.",
  "/rh": "Registo de horas na obra, folhas de horas e presenças.",
  "/mon-catalogue": "A sua biblioteca de preços e artigos reutilizáveis.",
  "/bibliotheque": "Modelos e artigos prontos a reutilizar nos seus orçamentos.",
  "/ma-page": "A sua página pública e os seus documentos personalizados.",
  "/radar": "Detete obras e oportunidades perto de si.",
  "/docs": "API e integrações para ligar as suas ferramentas.",
};
export const benefitFor = (to, level) => UPSELL_BENEFITS[to] || `Função incluída na oferta ${LEVEL_LABELS[level] || "payante"}.`;
export const visibleWorkspaceLinks = (user, can, tier) => {
  const level = _levelOf(user, tier);
  return WORKSPACE_LINKS.filter(item =>
    user && (!item.admin || user.role === "admin") &&
    (RANK[level] >= RANK[_minLevel(item)]) &&
    (!item.perm || can(item.perm)));
};
// Same catalogue. Accessible items respect team permissions; locked (higher-tier)
// items are HIDDEN for lower tiers EXCEPT a few `upsell` vedettes kept as teasers.
export const workspaceLinks = (user, can, tier) => {
  const level = _levelOf(user, tier);
  return WORKSPACE_LINKS
    .filter(item => user && (!item.admin || user.role === "admin"))
    .map(item => {
      const minLevel = _minLevel(item);
      const locked = RANK[level] < RANK[minLevel];
      return { ...item, locked, requiredLevel: locked ? minLevel : null };
    })
    .filter(item => item.locked ? !!item.upsell : (!item.perm || can(item.perm)));
};
export const routePermission = (pathname, search = "") => {
  if (pathname === "/pointage") return "pointage";
  if (pathname.startsWith("/devis-editeur") && new URLSearchParams(search).get("type") === "invoice") return "factures";
  return WORKSPACE_LINKS.filter(item => item.perm && routeMatches(pathname, item.to)).sort((a, b) => b.to.length - a.to.length)[0]?.perm;
};
export const routeMatches = (pathname, to) => pathname === to || pathname.startsWith(to + "/");
export const activeWorkspaceLink = (pathname, links) => links.filter(l => routeMatches(pathname, l.to)).sort((a,b) => b.to.length - a.to.length)[0]?.to;
export const OPEN_WORKSPACE_MENU = "construpilot:open-tools";

