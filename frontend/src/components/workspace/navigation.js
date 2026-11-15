import { AssistantMark } from "@/components/assistant/AssistantMark";
import { APP_SUITES, SUITE_MEMBER_PATHS, suiteOfPath, suiteHubFor } from "./suites";
import { Trash2, Bot, LayoutDashboard, FileText, Calculator, Ruler, Search, Users, HardHat, Building2, Receipt, Layers, Camera, Truck, Wand2, Radar, Contact, Library, Tag, Brain, KeyRound, Sparkles, Wrench, FileSearch, MessageSquare, Handshake, TrendingUp, Inbox, Shield, Globe, LifeBuoy, FileSpreadsheet, Footprints, Leaf, CalendarRange, Box, ClipboardCheck, Clock, Code2, CreditCard, DraftingCompass, Euro, FileCog, FilePlus2, Gauge, Gift, GraduationCap, Hammer, ImagePlus, Landmark, LayoutGrid, Lightbulb, MoveHorizontal, Newspaper, Package, PackageCheck, PenLine, Percent, Rocket, Scale, ScanEye, ScanText, ScrollText, Send, Sheet, SlidersHorizontal, Stamp, Star, UserCog, UserSearch, Zap, FileCheck2, MapPinned, Mountain, Building, Timer, Boxes, FilePen, Atom } from "lucide-react";

export const AssistantIcon = ({ size = 18, className = "" }) => (
  <AssistantMark size={size} className={className} />
);

// Escada (perfil de degraus).
export const StairsIcon = ({ size = 18, color = "currentColor", strokeWidth = 1.9, className = "", ...props }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth={strokeWidth}
    strokeLinecap="round" strokeLinejoin="round" className={className} aria-hidden="true" focusable="false" {...props}>
    <path d="M3 20h5v-4h4v-4h4V8h5" />
  </svg>
);

// Seis espaços de trabalho pela ordem de um projeto. Cor sólida (pastilhas) e gradiente vivo (mosaicos).
export const FAMILY_COLORS = {
  projets: "#16a34a",
  plans: "#3b82f6",
  devis: "#f59e0b",
  etudes: "#f43f5e",
  ia: "#8b5cf6",
  compte: "#0d9488",
};
export const FAMILY_GRADIENTS = {
  projets: "linear-gradient(135deg, #34d399 0%, #16a34a 55%, #0f766e 100%)",
  plans: "linear-gradient(135deg, #67e8f9 0%, #3b82f6 60%, #4f46e5 100%)",
  devis: "linear-gradient(135deg, #fde047 0%, #f59e0b 50%, #ea580c 100%)",
  etudes: "linear-gradient(135deg, #fda4af 0%, #f43f5e 55%, #db2777 100%)",
  ia: "linear-gradient(135deg, #c4b5fd 0%, #8b5cf6 50%, #d946ef 100%)",
  compte: "linear-gradient(135deg, #5eead4 0%, #14b8a6 50%, #0891b2 100%)",
};
export const FAMILY_LABELS = {
  projets: "Projetos e obras",
  plans: "Plantas e medições",
  devis: "Orçamentos e faturas",
  etudes: "Estudos e cálculos",
  ia: "Assistente e IA",
  compte: "Conta e rede",
};
export const FAMILY_I18N = {
  pt: { projets: ["Projetos e obras", "Clientes, planeamento, equipa, acompanhamento"], plans: ["Plantas e medições", "Do PDF / DXF / DWG às medições"],
        devis: ["Orçamentos e faturas", "Orçamentar, enviar, receber"], etudes: ["Estudos e cálculos", "O gabinete de projeto integrado"],
        ia: ["Assistente e IA", "A IA que conhece os seus projetos"], compte: ["Conta e rede", "Página, avaliações, definições, ajuda"] },
  en: { projets: ["Projects & sites", "Clients, planning, team, follow-up"], plans: ["Plans & take-offs", "From PDF / DXF / DWG to quantities"],
        devis: ["Quotes & invoices", "Price, send, get paid"], etudes: ["Studies & calculations", "Your built-in engineering office"],
        ia: ["Assistant & AI", "The AI that knows your projects"], compte: ["Account & network", "Page, reviews, settings, help"] },
  fr: { projets: ["Projets & chantiers", "Clients, planning, équipe, suivi"], plans: ["Plans & métrés", "Du PDF / DXF / DWG au métré"],
        devis: ["Devis & factures", "Chiffrer, envoyer, encaisser"], etudes: ["Études & calculs", "Le bureau d'études intégré"],
        ia: ["Assistant & IA", "L'IA qui connaît vos projets"], compte: ["Compte & réseau", "Ma page, avis, réglages, aide"] },
};
export const familyLabel = (f, lang = "pt") => ((FAMILY_I18N[lang] || FAMILY_I18N.pt)[f] || FAMILY_I18N.pt[f] || [FAMILY_LABELS[f] || f, ""])[0];
export const familySub = (f, lang = "pt") => ((FAMILY_I18N[lang] || FAMILY_I18N.pt)[f] || FAMILY_I18N.pt[f] || ["", ""])[1];
export const FAMILY_ORDER = ["projets", "plans", "devis", "etudes", "ia", "compte"];

// A single catalogue drives the sidebar, search and mobile navigation.
// These visibility rules complement the existing server/route permissions.
export const WORKSPACE_LINKS = [
  { to: "/dashboard", key: "nav.dashboard", label: "Painel", ui: "home", icon: LayoutDashboard, family: "compte", group: "today", pin: true },
  { to: "/assistant", key: "nav.assistant", label: "Assistente Construção", ui: "assistant", icon: AssistantIcon, family: "ia", group: "assistant", pin: true, min: "particulier_payant", upsell: true, words: "chat ajuda e-mail carta relatório aurora assistente construção" },
  { to: "/chantiers", key: "nav.chantiers", label: "Dossiers de obra", icon: HardHat, family: "projets", group: "chantiers", pro: true, pin: true, words: "processo obra cliente plantas orçamento fotografias dossier" },
  { to: "/devis", key: "nav.tracking", label: "Acompanhamento de orçamentos", ui: "quotes", icon: PenLine, family: "devis", group: "billing", pro: true, perm: "devis", pin: true },
  { to: "/devis-editeur", key: "nav.newquote", label: "Novo orçamento", ui: "newQuote", icon: FilePlus2, family: "devis", group: "billing", pro: true, perm: "devis", upsell: true, pin: true },
  { to: "/factures", key: "nav.invoices", label: "Faturas", icon: Receipt, family: "devis", group: "billing", pro: true, perm: "factures", pin: true },
  { to: "/clients", key: "nav.clients", label: "Clientes", icon: Contact, family: "projets", group: "clients", pro: true, pin: true },
  { to: "/corbeille", key: "nav.trash", label: "Lixo", icon: Trash2, family: "compte", group: "account", pro: true, words: "eliminado recuperar restaurar orçamento apagado" },
  { to: "/situations", key: "nav.situations", label: "Autos de medição", icon: Percent, family: "devis", group: "billing", min: "business", perm: "situations" },
  { to: "/dpgf", key: "nav.dpgf", label: "Mapa de quantidades do arquiteto → orçamento", icon: Sheet, family: "devis", group: "billing", pro: true, perm: "devis", pin: true, words: "mapa quantidades orçamento excel caderno encargos concurso subempreiteiro orçamentação arquiteto" },
  { to: "/analyse-documents", key: "nav.docintel", label: "Análise de documentos", icon: FileSearch, family: "ia", group: "billing", pro: true, pin: true, words: "mapa quantidades orçamento pdf excel proveniência verificação iva quantidades fórmula fonte caderno encargos fatura leitura" },
  { to: "/plan", key: "nav.plan2d", label: "Plantas e medições", ui: "plan", icon: DraftingCompass, family: "plans", group: "chantiers", pro: true, pin: true, upsell: true, words: "pdf dwg dxf áreas medição medições" },
  { to: "/agents", key: "nav.agents", label: "Piloto ConstruPilot", icon: Bot, family: "ia", group: "assistant", pin: true, personalPin: true, words: "agente automático processo orçamento medição deteção comparação segundo plano tarefa automatização" },
  { to: "/renovation", key: "nav.renovation", label: "Renovação energética", icon: Leaf, family: "etudes", group: "chantiers", pro: true, pin: true, words: "renopilot energia certificado energético auditoria isolamento térmico cenários remodelação" },
  { to: "/structuro", key: "nav.structuro", label: "StructuroPilot (estudo)", icon: Landmark, family: "etudes", group: "chantiers", pro: true, words: "estrutura viga parede resistente abertura sapata estudo descida de cargas ipe hea heb gabinete projeto eurocódigo" },
  { to: "/metodos-medicao", label: "Medições e dossier (CLT e tradicional)", icon: Ruler, family: "plans", group: "chantiers", pro: true, pin: true, words: "medição métré quantidades alvenaria tijolo bloco betão ossatura madeira lsf pladur clt dossier desenhos cotados orçamento origem verificação" },
  { to: "/estudo-moradia", key: "nav.house", label: "Estudo estrutural de moradia", icon: Hammer, family: "etudes", group: "chantiers", pro: true, pin: true, words: "laje armaduras cofragem sapata lintel cinta pilarete betão armado plano de execução gros oeuvre ferraillage moradia estrutura" },
  { to: "/missions", key: "nav.missions", label: "Programa IA de opções", icon: Sparkles, family: "ia", group: "assistant", pro: true, pin: true, words: "programa opções automático entregáveis térmica perdas de calor bomba de calor piso radiante estrutura moradia mapa de quantidades caderno de encargos pré-certificado reh eletricidade canalização planeamento partilha" },
  { to: "/planos-execucao", key: "nav.mep", label: "Planos de execução (eletricidade e canalização)", icon: Zap, family: "plans", group: "chantiers", pro: true, pin: true, words: "planta eletricidade canalização tomadas circuitos quadro unifilar rtiebt águas esgotos especialidades instalações execução" },
  { to: "/estudio-imagens", label: "Estúdio de imagens IA", icon: ImagePlus, family: "ia", group: "chantiers", pro: true, words: "imagem ilustração gerar fotomontagem inserção fotografia retoque fachada visual render nano banana gpt image não contratual" },
  { to: "/urbanismo", key: "nav.urbanismo", label: "Urbanismo (editor de volumes)", icon: ScrollText, family: "etudes", group: "chantiers", pro: true, pin: true, words: "urbanismo planta de implantação alçados cortes área de implantação área de construção cércea afastamentos índice de ocupação índice de utilização pdm rgeu pé-direito estacionamento volumes" },
  { to: "/structuro-bet", key: "nav.betdossier", label: "Análise de processo de engenharia", icon: FileCog, family: "etudes", group: "chantiers", pro: true, pin: true, words: "gabinete projeto engenharia memória cálculo revisão índice incoerência controlo planta comparar versões processo" },
  { to: "/btp-solver", key: "nav.solver", label: "Resolver um problema", icon: Lightbulb, family: "ia", group: "chantiers", pin: true, words: "fissura humidade patologia diagnóstico solução" },
  { to: "/plans-pro", key: "nav.plansPro", label: "Plantas BIM / Autodesk", icon: Box, family: "plans", group: "chantiers", min: "pro", pin: false, words: "autodesk revit ifc visão quantidades paredes portas janelas" },
  { to: "/controle-cotes", key: "nav.cotes", label: "Controlo das cotas", icon: MoveHorizontal, family: "plans", group: "chantiers", pro: true, pin: false, words: "paredes dimensões interior planta" },
  { to: "/escaliers", key: "nav.stairs", label: "Cálculo de escadas", icon: StairsIcon, family: "etudes", group: "chantiers", pro: true, pin: true, words: "escada degraus cobertor espelho blondel rgeu quarto de volta helicoidal betão armado lanço armaduras" },
  { to: "/suivi-chantier", key: "nav.site", label: "Acompanhamento de obra", icon: ClipboardCheck, family: "projets", group: "chantiers", pro: true, perm: "chantier", pin: true },
  { to: "/planning", label: "Planeamento de obra", icon: CalendarRange, family: "projets", group: "chantiers", pro: true, pin: true, words: "planeamento gantt caminho crítico equipas atraso replaneamento sequenciamento or-tools prazos" },
  { to: "/plan/compare", label: "Comparar plantas", icon: Layers, family: "plans", group: "chantiers", pro: true },
  { to: "/medicao-rapida", label: "Medição rápida", icon: Timer, family: "plans", group: "chantiers", words: "área perímetro volume divisão prompt" },
  { to: "/bim", label: "ConstruPilot BIM Studio", icon: Boxes, family: "plans", group: "chantiers", pro: true, words: "ifc ifcopenshell 3d bim medições orçamento" },
  { to: "/appro", key: "nav.appro", label: "Análise técnica & Aprovisionamento IA", icon: PackageCheck, family: "etudes", group: "chantiers", pro: true, words: "aço armaduras fornecedores encomenda" },
  { to: "/rendu-ia", key: "nav.render", label: "Renderização IA (antes/depois)", icon: Wand2, family: "ia", group: "chantiers", min: "particulier_payant" },
  { to: "/etudes-pc", key: "nav.studies", label: "Estudos de licença", icon: Stamp, family: "etudes", group: "chantiers", pro: true, words: "licença construção" },
  { to: "/mesure-photo", key: "nav.photomeasure", label: "Medir em fotografia", icon: Camera, family: "plans", group: "chantiers", min: "particulier_payant" },
  { to: "/estimation", key: "nav.estimator", label: "Estimador", ui: "estimate", icon: Euro, family: "devis", group: "today", personalPin: true },
  { to: "/smart-project", label: "Smart Project", ui: "smart", icon: Atom, family: "ia", group: "today" },
  { to: "/precos", key: "nav.prices", label: "Preços de materiais", icon: Package, family: "devis", group: "library", personalPin: true },
  { to: "/calculadoras", key: "nav.calculators", label: "Calculadoras", icon: Calculator, family: "etudes", group: "library", personalPin: true },
  { to: "/scanner-devis", key: "nav.scanner", label: "Scanner de orçamentos", icon: ScanText, family: "devis", group: "billing", subscriber: true },
  { to: "/entreprise", key: "nav.company", label: "Espaço Empresa", icon: Building2, family: "projets", group: "account", min: "business", perm: "entreprise" },
  { to: "/ma-page", key: "nav.myPage", label: "A minha página & documentos", icon: Globe, family: "compte", group: "clients", pro: true, pin: true, words: "site montra página pública cabeçalho rodapé pdf personalização fotografias obras realizadas" },
  { to: "/equipe", key: "nav.team", label: "Equipa", icon: Users, family: "projets", group: "account", min: "business" },
  { to: "/rh", key: "hr.nav", label: "RH — Ponto", icon: Clock, family: "projets", group: "account", min: "business", perm: "rh" },
  { to: "/mon-catalogue", key: "nav.catalog", label: "Catálogo de preços", icon: Tag, family: "devis", group: "library", pro: true, perm: "catalogue" },
  { to: "/bibliotheque", key: "nav.library", label: "Biblioteca", icon: Library, family: "devis", group: "library", pin: true, pro: true },
  { to: "/rentabilite", label: "Relatório de rentabilidade", icon: TrendingUp, family: "devis", group: "billing", pro: true, perm: "factures" },
  { to: "/factures-electroniques", label: "Faturação eletrónica", icon: Send, family: "devis", group: "billing", pro: true, perm: "factures" },
  { to: "/mes-demandes", key: "nav.myleads", label: "Os meus pedidos", icon: Inbox, family: "projets", group: "clients", pin: true, pro: true },
  { to: "/radar", key: "nav.radar", label: "Radar Obras", icon: Radar, family: "projets", group: "clients", pro: true },
  { to: "/mes-avis", key: "nav.reviews", label: "Opiniões de clientes", icon: Star, family: "compte", group: "clients", pro: true },
  { to: "/fournisseur", label: "Espaço fornecedor", icon: Truck, family: "compte", group: "account", pro: true },
  { to: "/photo", key: "nav.photo", label: "Análise de fotografia", icon: ScanEye, family: "ia", group: "discover" },
  { to: "/coach", key: "nav.coach", label: "Coach IA", icon: GraduationCap, family: "ia", group: "assistant" },
  { to: "/diy", key: "nav.diy", label: "Faço eu mesmo", icon: Wrench, family: "compte", group: "discover", personalPin: true },
  { to: "/licenciamento-automatico", label: "Licenciamento automático de moradia", icon: FileCheck2, family: "etudes", group: "chantiers", words: "licenciamento automático moradia terreno morada pdm ran ren caop implantação garagem 3d fachadas projeto de arquitetura estúdio de projeto" },
  { to: "/terrenos", label: "Terrenos (BUPi, PDM, RAN, REN)", icon: MapPinned, family: "etudes", group: "chantiers", words: "terreno prédio bupi rgg cadastro ortofoto ortosat pdm ran ren kml condicionantes" },
  { to: "/mdt", label: "MDT Portugal (LiDAR DGT)", icon: Mountain, family: "etudes", group: "chantiers", words: "mdt modelo digital terreno lidar dgt declives curvas de nível linhas de água copernicus" },
  { to: "/maquete-3d", label: "Maquete 3D Braga", icon: Building, family: "etudes", group: "chantiers", words: "maquete 3d braga guimarães edifícios ruas relevo pdm" },
  { to: "/particulares/autorizacao-obras", label: "Autorização de obras", icon: FilePen, family: "etudes", group: "discover", words: "licenciamento comunicação prévia escassa relevância rjue dl 555 obra licença câmara" },
  { to: "/marketplace", key: "nav.marketplace", label: "Encontrar um profissional", icon: UserSearch, family: "compte", group: "discover", personalPin: true },
  { to: "/blog", key: "nav.blog", label: "Blog", icon: Newspaper, family: "compte", group: "discover" },
  { to: "/fonctionnalites", key: "nav.features", label: "Funcionalidades", icon: LayoutGrid, family: "compte", group: "discover" },
  { to: "/comparatif", key: "nav.compare", label: "Comparativo", icon: Scale, family: "compte", group: "discover" },
  { to: "/docs", key: "nav.docs", label: "API e Programadores", icon: Code2, family: "compte", group: "discover", min: "business" },
  { to: "/developpeurs", label: "Chaves API", icon: KeyRound, family: "compte", group: "account", min: "business" },
  { to: "/preferences", key: "nav.preferences", label: "Memória e preferências", ui: "preferences", icon: SlidersHorizontal, family: "compte", group: "account" },
  { to: "/compte", key: "nav.account", label: "A minha conta", ui: "account", icon: UserCog, family: "compte", group: "account" },
  { to: "/planos", key: "nav.pricing", label: "Preços & subscrição", ui: "subscription", icon: CreditCard, family: "compte", group: "account" },
  { to: "/inviter", key: "nav.referral", label: "Recomendar", icon: Gift, family: "compte", group: "account" },
  { to: "/investisseurs", key: "nav.investors", label: "Investidores", icon: Handshake, family: "compte", group: "discover" },
  { to: "/aide", key: "nav.help", label: "Ajuda e assistência", icon: LifeBuoy, family: "compte", group: "discover", words: "aide support assistance contact faq help ajuda" },
  { to: "/admin", key: "nav.admin", label: "Administração", icon: Shield, family: "compte", group: "account", admin: true },
  { to: "/admin/despesas", label: "Despesas das APIs", icon: Gauge, family: "compte", group: "account", admin: true, pin: true, words: "despesas custos budget autodesk ctt correio" },
  { to: "/admin/growth", label: "Growth · SEO & IA", icon: Rocket, family: "compte", group: "account", admin: true, pin: true, words: "growth seo visibilidade ia referenciação conteúdos blogue auditoria" },
];
const _RANK0 = { particulier_gratuit: 0, particulier_payant: 1, pro: 2, business: 3 };
const _memberMin = (item) => item.min || (item.pro ? "pro" : item.subscriber ? "particulier_payant" : "particulier_gratuit");
// Uma entrada por suite (app fusionada). Os membros continuam no catálogo
// (permissões por rota, ligações diretas), mas o menu só mostra a suite.
for (const suite of APP_SUITES) {
  const members = suite.members.map(to => WORKSPACE_LINKS.find(l => l.to === to)).filter(Boolean);
  const min = members.map(_memberMin).sort((a, b) => _RANK0[a] - _RANK0[b])[0] || "particulier_gratuit";
  const entry = {
    to: suite.to, hub: suite.id, label: suite.label.pt, icon: suite.icon, family: suite.family, group: suite.group,
    pin: suite.pin, personalPin: suite.personalPin, min, upsell: members.some(m => m.upsell) || undefined,
    words: [suite.label.pt, suite.label.fr, suite.label.en, ...members.map(m => `${m.label} ${m.words || ""}`)].join(" "),
  };
  const existing = WORKSPACE_LINKS.findIndex(l => l.to === suite.to);
  if (existing >= 0) { WORKSPACE_LINKS[existing] = entry; continue; }
  const first = Math.min(...members.map(m => WORKSPACE_LINKS.indexOf(m)));
  WORKSPACE_LINKS.splice(Number.isFinite(first) ? first : WORKSPACE_LINKS.length, 0, entry);
}
export const WORKSPACE_GROUPS = ["favorites", "today", "chantiers", "billing", "clients", "library", "assistant", "discover", "account"];
// Keep every specialist tool available in the directory; only daily work is pinned.
export const workspaceEssentials = (links, professional) => {
  const paths = professional
    ? ["/dashboard", "/chantiers", "/estudos-engenharia", "/licenciamento", "/plantas-medicoes", "/agents", "/devis", "/faturacao", "/clients", "/assistant"]
    : ["/dashboard", "/estimar", "/assistant", "/agents", "/licenciamento", "/precos-biblioteca", "/marketplace"];
  const hubs = [...new Set(paths.map(suiteHubFor))];
  return hubs.map(path => links.find(item => item.to === path && !item.locked)).filter(Boolean);
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
  "/metodos-medicao": "Os mesmos métodos do motor CLT para qualquer construção: quantidades com origem, verificações cruzadas, orçamento e dossier com desenhos cotados.",
  "/estudo-moradia": "Pré-dimensionamento de moradia: lajes, sapatas, lintéis, escadas e dossier PDF com desenhos.",
  "/missions": "Assinale os entregáveis (plantas de execução, térmica, estrutura, pré-certificado REH, mapa de quantidades e caderno de encargos, orçamento, planeamento): a IA executa-os em segundo plano com os motores de cálculo.",
  "/planos-execucao": "Gere as plantas de eletricidade e canalização a partir da sua planta: pontos, circuitos, esquema unifilar, quantidades e PDF A3.",
  "/estudio-imagens": "Gere ilustrações IA a partir de um texto ou retoque uma fotografia (inserção de projeto, fachada): imagens marcadas «Ilustração IA não contratual».",
  "/urbanismo": "Gere planta de implantação, corte, alçado e quadro de áreas a partir de algumas dimensões e verifique os parâmetros do seu PDM.",
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
  "/developpeurs": "Crie e gira as chaves de acesso à API ConstruPilot.",
  "/licenciamento-automatico": "Da morada ao processo de licenciamento completo: terreno, PDM/RAN/REN, implantação, peças desenhadas e 3D.",
  "/terrenos": "Identifique o prédio sobre o ortofotomapa oficial: BUPi, cadastro, PDM, RAN, REN e KML.",
  "/mdt": "Terreno LiDAR da DGT: declives, curvas de nível e linhas de água.",
  "/maquete-3d": "Distrito de Braga em 3D: edifícios, ruas, rios, relevo e PDM.",
  "/particulares/autorizacao-obras": "Diagnóstico RJUE e processo para a Câmara Municipal (comunicação prévia, licença, isenção).",
  "/medicao-rapida": "Áreas, perímetro e volume de uma divisão — por prompt ou à mão.",
  "/bim": "Abra um IFC: modelo 3D, medições e orçamento (BIM Studio).",
  "/estimation": "Estime o custo de uma obra em poucos cliques.",
  "/smart-project": "Descreva o projeto: a IA prepara o plano de obra e o orçamento.",
  "/calculadoras": "Cálculos rápidos de construção: betão, armaduras, revestimentos, quantidades.",
  "/precos": "Pesquise preços de materiais atualizados.",
  "/btp-solver": "Descreva um problema (fissura, humidade, patologia): diagnóstico e soluções.",
  "/photo": "Analise uma fotografia da obra ou do defeito com IA.",
  "/coach": "Um orientador IA para tirar dúvidas de construção.",
  "/diy": "Guias passo a passo para fazer você mesmo.",
  "/mes-avis": "Recolha e mostre as opiniões dos seus clientes.",
  "/mes-demandes": "Os pedidos de clientes recebidos pelo ConstruPilot.",
  "/scanner-devis": "Analise um orçamento recebido: preços, quantidades e incoerências.",
  "/factures-electroniques": "Emissão e envio de faturas eletrónicas conformes.",
};
export const benefitFor = (to, level) => UPSELL_BENEFITS[to] || `Função incluída na oferta ${LEVEL_LABELS[level] || "payante"}.`;
export const visibleWorkspaceLinks = (user, can, tier) => {
  const level = _levelOf(user, tier);
  return WORKSPACE_LINKS.filter(item =>
    user && (!item.admin || user.role === "admin") &&
    (RANK[level] >= RANK[_minLevel(item)]) &&
    (!item.perm || can(item.perm)));
};
// Todas as ferramentas (membros de suites incluídos), com bloqueio por oferta.
export const allWorkspaceLinks = (user, can, tier) => {
  const level = _levelOf(user, tier);
  return WORKSPACE_LINKS
    .filter(item => !item.hub)
    .filter(item => user && (!item.admin || user.role === "admin"))
    .map(item => {
      const minLevel = _minLevel(item);
      const locked = RANK[level] < RANK[minLevel];
      return { ...item, locked, requiredLevel: locked ? minLevel : null };
    })
    .filter(item => item.locked ? !!item.upsell : (!item.perm || can(item.perm)));
};
// Ferramentas de uma suite acessíveis (ou em destaque bloqueado) para este utilizador.
export const suiteMemberLinks = (suiteId, user, can, tier) => {
  const suite = APP_SUITES.find(s => s.id === suiteId);
  if (!suite) return [];
  const all = allWorkspaceLinks(user, can, tier);
  return suite.members.map(to => all.find(l => l.to === to)).filter(Boolean);
};
// Menu: só as apps (suites fusionadas + ferramentas sem suite).
// Uma suite fica desbloqueada se pelo menos uma ferramenta for acessível;
// bloqueada (destaque) se só restarem ferramentas « upsell »; senão fica oculta.
export const workspaceLinks = (user, can, tier) => {
  const all = allWorkspaceLinks(user, can, tier);
  const out = [];
  for (const item of WORKSPACE_LINKS) {
    if (!user || (item.admin && user.role !== "admin")) continue;
    if (!item.hub) {
      if (SUITE_MEMBER_PATHS.has(item.to)) continue;
      const resolved = all.find(l => l.to === item.to);
      if (resolved) out.push(resolved);
      continue;
    }
    const suite = APP_SUITES.find(s => s.id === item.hub);
    const members = suite.members.map(to => all.find(l => l.to === to)).filter(Boolean);
    if (!members.length) continue;
    if (members.some(m => !m.locked)) out.push({ ...item, locked: false, requiredLevel: null });
    else {
      const required = members.map(m => m.requiredLevel).sort((x, y) => RANK[x] - RANK[y])[0];
      out.push({ ...item, locked: true, requiredLevel: required, upsell: true });
    }
  }
  return out;
};
export const routePermission = (pathname, search = "") => {
  if (pathname === "/pointage") return "pointage";
  if (pathname.startsWith("/devis-editeur") && new URLSearchParams(search).get("type") === "invoice") return "factures";
  return WORKSPACE_LINKS.filter(item => item.perm && routeMatches(pathname, item.to)).sort((a, b) => b.to.length - a.to.length)[0]?.perm;
};
export const routeMatches = (pathname, to) => pathname === to || pathname.startsWith(to + "/");
export const activeWorkspaceLink = (pathname, links) => {
  const suite = suiteOfPath(pathname);
  if (suite && links.some(l => l.to === suite.to)) return suite.to;
  return links.filter(l => routeMatches(pathname, l.to)).sort((a,b) => b.to.length - a.to.length)[0]?.to;
};
export const OPEN_WORKSPACE_MENU = "construpilot:open-tools";

