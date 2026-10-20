import {
  LayoutDashboard, LayoutGrid, Calculator, Users, Building2, Receipt, Layers, Camera, Wand2, Contact, Library, Tag,
  KeyRound, Sparkles, Wrench, Handshake, Inbox, Shield, DraftingCompass, FilePlus2, ScanText, Package, PenLine, Send,
  Percent, Stamp, GraduationCap, ScanEye, PackageCheck, ClipboardCheck, Clock, Star, UserSearch, Euro, Gift, Code2,
  CreditCard, UserCog, Newspaper, Scale, Truck, HardHat,
} from "lucide-react";

// Seis espaços de trabalho, pela ordem de um projeto (+ conta e rede).
// Cor sólida (pastilhas) e degradé vivo (mosaicos de ícones) por espaço.
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
export const FAMILY_I18N = {
  projets: ["Projetos e obras", "Clientes, pedidos, equipa, acompanhamento"],
  plans: ["Plantas e medições", "Do PDF / DXF / DWG às medições"],
  devis: ["Orçamentos e faturas", "Orçamentar, enviar, receber"],
  etudes: ["Estudos e cálculos", "O gabinete de projeto integrado"],
  ia: ["Assistente e IA", "A IA que conhece os seus projetos"],
  compte: ["Conta e rede", "Conta, avaliações, subscrição, ajuda"],
};
export const FAMILY_ICONS = { projets: HardHat, plans: DraftingCompass, devis: Receipt, etudes: Calculator, ia: Sparkles, compte: UserCog };
export const familyLabel = (f) => (FAMILY_I18N[f] || ["", ""])[0];
export const familySub = (f) => (FAMILY_I18N[f] || ["", ""])[1];
export const FAMILY_ORDER = ["projets", "plans", "devis", "etudes", "ia", "compte"];

// Catálogo único: alimenta a barra lateral, a pesquisa (Ctrl K), o menu móvel e "Todas as ferramentas".
// Só rotas existentes em App.js. `alias` = caminhos antigos (FR) que apontam para a mesma página.
// pro: reservado a profissionais · perm: permissão de equipa · subscriber: profissional ou subscrição paga.
export const WORKSPACE_LINKS = [
  { to: "/dashboard", label: "Início", icon: LayoutDashboard, family: "compte", home: true },
  // Projetos e obras
  { to: "/obra", alias: ["/suivi-chantier"], label: "Acompanhamento de obra", icon: ClipboardCheck, family: "projets", pro: true, perm: "chantier", words: "obra estaleiro fotos notas reservas avanço" },
  { to: "/clients", label: "Clientes", icon: Contact, family: "projets", pro: true, words: "cliente contactos crm histórico" },
  { to: "/mes-demandes", label: "Os meus pedidos", icon: Inbox, family: "projets", pro: true, words: "pedidos leads oportunidades contactos" },
  { to: "/empresa", alias: ["/entreprise"], label: "Espaço Empresa", icon: Building2, family: "projets", pro: true, perm: "entreprise", words: "empresa indicadores membros caixa de correio" },
  { to: "/equipa", alias: ["/equipe"], label: "Equipa", icon: Users, family: "projets", pro: true, words: "equipa convidar funções acessos" },
  { to: "/rh", label: "RH — Registo de horas", icon: Clock, family: "projets", pro: true, perm: "rh", words: "horas ponto presenças trabalhadores" },
  // Plantas e medições
  { to: "/planta", alias: ["/plan", "/plans"], label: "Medição em planta", icon: DraftingCompass, family: "plans", pro: true, words: "pdf dwg dxf áreas medições planta" },
  { to: "/plan/compare", label: "Comparar plantas", icon: Layers, family: "plans", pro: true, words: "versões diferenças plantas" },
  { to: "/mesure-photo", label: "Medir numa foto", icon: Camera, family: "plans", pro: true, words: "foto medida dimensões" },
  // Orçamentos e faturas
  { to: "/orcamentos", alias: ["/devis"], label: "Orçamentos enviados", icon: PenLine, family: "devis", pro: true, perm: "devis", words: "orçamentos enviados assinados abertos" },
  { to: "/orcamento-editor", alias: ["/devis-editeur"], label: "Novo orçamento", icon: FilePlus2, family: "devis", pro: true, words: "criar orçamento proposta" },
  { to: "/faturas", alias: ["/factures", "/invoices"], label: "Faturas", icon: Receipt, family: "devis", pro: true, perm: "factures", words: "fatura recebimentos saf-t iva" },
  { to: "/faturacao-eletronica", alias: ["/factures-electroniques", "/e-invoicing"], label: "Faturação eletrónica", icon: Send, family: "devis", pro: true, perm: "factures", words: "fatura eletrónica ciu qr atcud" },
  { to: "/situacoes", alias: ["/situations"], label: "Autos de medição", icon: Percent, family: "devis", pro: true, perm: "situations", words: "autos medição faturação avanço adiantamento" },
  { to: "/estimativa", alias: ["/estimation"], label: "Estimativa de obras", icon: Euro, family: "devis", words: "estimar preço obra remodelação" },
  { to: "/precos", alias: ["/prix"], label: "Preços de materiais", icon: Package, family: "devis", words: "materiais preços mercado alertas" },
  { to: "/scanner-devis", label: "Analisar um orçamento", icon: ScanText, family: "devis", subscriber: true, words: "verificar orçamento recebido análise" },
  { to: "/mon-catalogue", label: "Catálogo de preços", icon: Tag, family: "devis", pro: true, perm: "catalogue", words: "catálogo preços artigos" },
  { to: "/biblioteca", alias: ["/bibliotheque"], label: "Biblioteca", icon: Library, family: "devis", pro: true, words: "modelos artigos reutilizar" },
  // Estudos e cálculos
  { to: "/calculadoras", alias: ["/calculateurs"], label: "Calculadoras", icon: Calculator, family: "etudes", words: "cálculo áreas volumes betão viga armadura" },
  { to: "/etudes-pc", alias: ["/pc"], label: "Estudos de licenciamento", icon: Stamp, family: "etudes", pro: true, words: "licenciamento estudos estrutura notas de cálculo" },
  { to: "/appro", label: "Análise técnica e aprovisionamento IA", icon: PackageCheck, family: "etudes", pro: true, words: "aço armadura encomenda fornecedores" },
  // Assistente e IA
  { to: "/coach", label: "Assistente ConstruPilot", icon: GraduationCap, family: "ia", words: "assistente chat ia perguntas voz" },
  { to: "/smart-project", label: "Smart Project", icon: Sparkles, family: "ia", words: "projeto inteligente ia" },
  { to: "/photo", label: "Análise de fotos", icon: ScanEye, family: "ia", words: "foto diagnóstico patologia" },
  { to: "/render-ia", alias: ["/rendu-ia", "/render-studio"], label: "Render IA (antes/depois)", icon: Wand2, family: "ia", pro: true, words: "render imagem antes depois" },
  // Conta e rede
  { to: "/conta", alias: ["/compte"], label: "A minha conta", icon: UserCog, family: "compte", words: "conta perfil definições" },
  { to: "/tarifs", label: "Preços e subscrição", icon: CreditCard, family: "compte", words: "plano subscrição pagamento" },
  { to: "/inviter", label: "Convidar e ganhar", icon: Gift, family: "compte", words: "convidar indicar recompensa" },
  { to: "/mes-avis", label: "Avaliações de clientes", icon: Star, family: "compte", pro: true, words: "avaliações opiniões estrelas" },
  { to: "/fournisseur", label: "Espaço fornecedor", icon: Truck, family: "compte", pro: true, words: "fornecedor catálogo" },
  { to: "/marketplace", label: "Encontrar um profissional", icon: UserSearch, family: "compte", words: "profissional empreiteiro" },
  { to: "/diy", label: "Faço eu mesmo", icon: Wrench, family: "compte", words: "bricolage tutorial" },
  { to: "/blog", label: "Blogue", icon: Newspaper, family: "compte" },
  { to: "/funcionalidades", label: "Funcionalidades", icon: LayoutGrid, family: "compte" },
  { to: "/comparatif", label: "Comparativo", icon: Scale, family: "compte" },
  { to: "/docs", label: "API e programadores", icon: Code2, family: "compte" },
  { to: "/developpeurs", label: "Chaves API", icon: KeyRound, family: "compte", pro: true },
  { to: "/investidores", label: "Investidores", icon: Handshake, family: "compte" },
  { to: "/admin", label: "Administração", icon: Shield, family: "compte", admin: true },
];

export const isProfessional = (user) => Boolean(user) && (user.account_type !== "particulier" || user.role === "admin");

// Itens visíveis para o utilizador; os reservados a subscritores aparecem com cadeado.
export const workspaceLinks = (user, can, tier) => {
  const pro = isProfessional(user);
  const subscribed = tier && tier !== "free";
  return WORKSPACE_LINKS
    .filter((l) => (!l.admin || user?.role === "admin") && (!l.pro || pro) && (!l.perm || !can || can(l.perm)))
    .map((l) => ({ ...l, locked: Boolean(l.subscriber && !pro && !subscribed) }));
};

export const workspaceEssentials = (links, professional) => {
  const paths = professional
    ? ["/dashboard", "/obra", "/planta", "/orcamentos", "/orcamento-editor", "/faturas", "/clients", "/coach"]
    : ["/dashboard", "/estimativa", "/coach", "/calculadoras", "/precos", "/marketplace"];
  return paths.map((p) => links.find((l) => l.to === p)).filter(Boolean);
};

const matches = (pathname, to) => pathname === to || pathname.startsWith(to + "/");
// Rota ativa = correspondência mais longa (inclui os aliases FR).
export const activeWorkspaceLink = (pathname, links) => {
  let best = null; let len = -1;
  for (const l of links) {
    for (const p of [l.to, ...(l.alias || [])]) {
      if (matches(pathname, p) && p.length > len) { best = l.to; len = p.length; }
    }
  }
  return best;
};

export const linkTarget = (l) => (l.locked ? "/passez-pro?feature=analyse" : l.to);

// Favoritos guardados localmente (por navegador).
const FAV_KEY = "cp_nav_favorites";
export const readFavorites = () => { try { return JSON.parse(localStorage.getItem(FAV_KEY) || "[]"); } catch { return []; } };
export const writeFavorites = (list) => {
  try { localStorage.setItem(FAV_KEY, JSON.stringify(list)); } catch { /* armazenamento indisponível */ }
  window.dispatchEvent(new Event("cp-favorites"));
};

export const normText = (s) => String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
