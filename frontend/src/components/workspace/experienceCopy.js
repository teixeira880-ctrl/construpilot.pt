import { useI18n } from "@/context/I18nContext";

const copy = {
  fr: {
    animatedBackground: "Fundo animado", motionReduced: "Reduzido no dispositivo", motionPaused: "En pause", motionOn: "Ativo",
    hello: "Bonjour", overview: "Vue d’ensemble", intro: "Os seus projetos, documentos e próximas ações.",
    essentials: "L’essentiel", shortcuts: "Acessos rápidos", category: "Categoria", all: "Todas as ferramentas",
    explore: "Explorar ferramentas", exploreHint: "O essencial à mão. Encontre as outras ferramentas por categoria ou pesquisa.",
    current: "Page actuelle", help: "Precisa de ajuda?", helpHint: "Guias e assistência", moreFavorites: "Todos os favoritos",
    pin: "Manter o menu aberto", unpin: "Recolher o menu", showMenu: "Abrir a navegação",
    newSite: "Nova obra", sitesDesc: "Clientes, plantas e documentos juntos.",
    assistantShort: "Assistant", quoteShort: "Novo orçamento", planShort: "Plantas e medições", estimateShort: "Estimar um projeto",
    progress: "Progresso dos trabalhos", noLots: "Progresso por preencher", today: "A acompanhar hoje", next: "Prochaine action",
    otherActions: "Autres actions", running: "analyses en cours", clear: "Sem ações pendentes de momento.",
    edit: "Editar", privacy: "Privacidade", legal: "Informação legal", settings: "Conta e definições", upgrade: "Conhecer os planos",
  },
  pt: {
    animatedBackground: "Fundo animado", motionReduced: "Reduzido no dispositivo", motionPaused: "Em pausa", motionOn: "Ativo",
    hello: "Olá", overview: "Visão geral", intro: "Os seus projetos, documentos e próximas ações.",
    essentials: "O essencial", shortcuts: "Acessos rápidos", category: "Categoria", all: "Todas as ferramentas",
    explore: "Explorar ferramentas", exploreHint: "O essencial à mão. Encontre as outras ferramentas por categoria ou pesquisa.",
    current: "Página atual", help: "Precisa de ajuda?", helpHint: "Guias e assistência", moreFavorites: "Todos os favoritos",
    pin: "Manter o menu aberto", unpin: "Recolher o menu", showMenu: "Abrir a navegação",
    newSite: "Nova obra", sitesDesc: "Clientes, plantas e documentos juntos.",
    assistantShort: "Assistente", quoteShort: "Novo orçamento", planShort: "Plantas e medições", estimateShort: "Estimar um projeto",
    progress: "Progresso dos trabalhos", noLots: "Progresso por preencher", today: "A acompanhar hoje", next: "Próxima ação",
    otherActions: "Outras ações", running: "análises em curso", clear: "Sem ações pendentes de momento.",
    edit: "Editar", privacy: "Privacidade", legal: "Informação legal", settings: "Conta e definições", upgrade: "Conhecer os planos",
  },
  en: {
    animatedBackground: "Animated background", motionReduced: "Reduced on device", motionPaused: "Paused", motionOn: "On",
    hello: "Hello", overview: "Overview", intro: "Your projects, documents and next steps.",
    essentials: "Essentials", shortcuts: "Quick access", category: "Category", all: "All tools",
    explore: "Explore tools", exploreHint: "Keep essentials close. Find other tools by category or search.",
    current: "Current page", help: "Need help?", helpHint: "Guides and support", moreFavorites: "All my favourites",
    pin: "Keep navigation open", unpin: "Collapse navigation", showMenu: "Open navigation",
    newSite: "New site", sitesDesc: "Clients, plans and documents together.",
    assistantShort: "Assistant", quoteShort: "New quote", planShort: "Plans & takeoffs", estimateShort: "Estimate a project",
    progress: "Work progress", noLots: "Progress not recorded", today: "Today’s priorities", next: "Next action",
    otherActions: "Other actions", running: "analyses in progress", clear: "No pending actions at the moment.",
    edit: "Edit", privacy: "Privacy", legal: "Legal information", settings: "Account and settings", upgrade: "Explore plans",
  },
};

export function useExperienceCopy() {
  const { lang } = useI18n();
  return key => copy[lang]?.[key] || copy.fr[key] || key;
}
