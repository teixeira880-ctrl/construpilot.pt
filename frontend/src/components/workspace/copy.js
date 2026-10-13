import { useI18n } from "@/context/I18nContext";
import { WORKSPACE_EXTRA } from "./translations";

const FR = {
  latest: "Dernière réponse", workspace: "Mon espace de travail", home: "Accueil", assistant: "Assistant BTP",
  search: "Rechercher un outil…", allTools: "Tous les outils", searchHint: "Trouvez une fonction par son nom ou votre besoin.",
  noResults: "Aucun outil trouvé. Essayez un autre mot.", clear: "Effacer", menu: "Menu", close: "Fermer",
  daily: "Au quotidien", measure: "Plans et chantier", manage: "Gestion", discover: "Ressources", account: "Entreprise & compte",
  favorites: "Favoris", today: "Aujourd’hui", chantiers: "Chantiers", billing: "Devis & factures", clients: "Clients", library: "Bibliothèque",
  addFavorite: "Ajouter aux favoris", removeFavorite: "Retirer des favoris", favoritesHint: "Cliquez sur l’étoile d’un outil pour l’épingler ici.",
  skip: "Aller au contenu", new: "Créer", newQuote: "Créer un devis", estimate: "Estimer des travaux",
  plan: "Plans & métrés", quotes: "Devis", calculators: "Calculs", theme: "Changer de thème", logout: "Se déconnecter",
  personal: "Espace particulier", professional: "Espace professionnel", settings: "Réglages", subscription: "Mon abonnement",
  welcome: "Que souhaitez-vous faire aujourd’hui ?", subtitle: "Vos projets, vos documents et votre assistant, au même endroit.",
  ask: "Demander à l’assistant", askDesc: "Une question, un courrier ou un compte rendu.",
  planDesc: "Importez votre PDF, DXF ou DWG.", quoteDesc: "Préparez un document pour votre client.",
  estimateDesc: "Décrivez votre projet et son budget.", prices: "Comparer les matériaux", pricesDesc: "Retrouvez des produits et leurs prix.",
  activity: "Retrouver mon travail", projectSearch: "Rechercher un projet…", noProjectsFound: "Aucun projet ne correspond à votre recherche.",
  projectEmpty: "Votre premier projet commence ici", projectEmptyDesc: "Créez une estimation pour retrouver ici votre budget et l’avancement des travaux.",
  loading: "Chargement de votre espace…", loadError: "Certaines données n’ont pas pu être chargées.", retry: "Réessayer",
  deleteTitle: "Supprimer ce projet ?", deleteDesc: "Ce projet sera supprimé. Cette action ne peut pas être annulée.",
  delete: "Supprimer", cancel: "Annuler", deleteError: "La suppression a échoué. Réessayez.",
  moreTools: "Aller plus loin", moreDesc: "Analyse technique, rentabilité, bibliothèque de prix et import DPGF.",
  getStarted: "Prendre en main ConstruPilot", newInvoice: "Créer une facture", smart: "Décrire un projet à l’IA",
  history: "Conversations", newChat: "Nouvelle conversation", historySearch: "Rechercher une conversation…", noHistory: "Vos conversations apparaîtront ici.",
  noHistoryMatch: "Aucune conversation trouvée.", chatTitle: "Comment puis-je vous aider ?", chatIntro: "Expliquez votre besoin avec vos mots. Ajoutez un plan, un devis ou vos notes pour commencer.",
  mail: "Répondre à un mail", report: "Faire un compte rendu", solve: "Résoudre un problème", analyse: "Analyser un plan",
  message: "Décrivez votre besoin, ou précisez ce qu’il faut vérifier…", send: "Envoyer", stop: "Interrompre",
  attach: "Joindre un fichier", mic: "Dicter ma demande", stopMic: "Arrêter la dictée", recording: "Dictée en cours…",
  files: "Documents et options", options: "Options", preferences: "Mémoire et préférences", thorough: "Approfondie", fast: "Rapide",
  response: "Réponse", web: "Recherche Internet", choosePlan: "Ajouter un plan déjà importé", chooseDoc: "Ajouter un document déjà importé",
  appliedPrefs: "Préférences appliquées", removeFile: "Retirer du contexte", addAs: "Ajouter ce fichier comme", docKind: "Devis, facture ou document",
  planKind: "Plan à mesurer", chatError: "Impossible de charger cette conversation.", historyError: "L’historique n’a pas pu être chargé.",
  keyboard: "Entrée pour envoyer · Maj + Entrée pour une nouvelle ligne", copied: "Réponse copiée", copy: "Copier", correct: "Corriger / préciser",
};
const PT = {
  latest: "Última resposta", workspace: "O meu espaço de trabalho", home: "Início", assistant: "Assistant BTP",
  search: "Procurar uma ferramenta…", allTools: "Todas as ferramentas", searchHint: "Encontre uma função pelo nome ou pela sua necessidade.",
  noResults: "Nenhuma ferramenta encontrada. Experimente outra palavra.", clear: "Limpar", menu: "Menu", close: "Fechar",
  daily: "Dia a dia", measure: "Plantas e obra", manage: "Gestão", discover: "Recursos", account: "Empresa e conta",
  favorites: "Favoritos", today: "Hoje", chantiers: "Obras", billing: "Orçamentos e faturas", clients: "Clientes", library: "Biblioteca",
  addFavorite: "Adicionar aos favoritos", removeFavorite: "Retirar dos favoritos", favoritesHint: "Clique na estrela de uma ferramenta para a fixar aqui.",
  skip: "Ir para o conteúdo", new: "Criar", newQuote: "Criar orçamento", estimate: "Estimar uma obra", plan: "Plantas e medições", quotes: "Orçamentos", calculators: "Cálculos",
  theme: "Mudar de tema", logout: "Terminar sessão", personal: "Espaço particular", professional: "Espaço profissional", settings: "Definições", subscription: "A minha subscrição",
  welcome: "O que pretende fazer hoje?", subtitle: "Os seus projetos, documentos e assistente, no mesmo lugar.",
  ask: "Perguntar ao assistente", askDesc: "Uma dúvida, uma mensagem ou um relatório.", planDesc: "Importe um PDF, DXF ou DWG.", quoteDesc: "Prepare um documento para o seu cliente.",
  estimateDesc: "Descreva o seu projeto e o orçamento previsto.", prices: "Comparar materiais", pricesDesc: "Encontre produtos e os seus preços.",
  activity: "Retomar o meu trabalho", projectSearch: "Procurar um projeto…", noProjectsFound: "Nenhum projeto corresponde à pesquisa.",
  projectEmpty: "O seu primeiro projeto começa aqui", projectEmptyDesc: "Crie uma estimativa para acompanhar aqui o orçamento e o avanço da obra.",
  loading: "A carregar o seu espaço…", loadError: "Não foi possível carregar alguns dados.", retry: "Tentar novamente",
  deleteTitle: "Eliminar este projeto?", deleteDesc: "O projeto será eliminado. Esta ação não pode ser anulada.", delete: "Eliminar", cancel: "Cancelar", deleteError: "Não foi possível eliminar. Tente novamente.",
  moreTools: "Ir mais longe", moreDesc: "Análise técnica, rentabilidade, biblioteca de preços e importação DPGF.", getStarted: "Começar com o ConstruPilot", newInvoice: "Criar fatura", smart: "Descrever um projeto à IA",
  history: "Conversas", newChat: "Nova conversa", historySearch: "Procurar uma conversa…", noHistory: "As suas conversas aparecerão aqui.", noHistoryMatch: "Nenhuma conversa encontrada.",
  chatTitle: "Como posso ajudar?", chatIntro: "Explique o que precisa por palavras suas. Junte uma planta, um orçamento ou as suas notas.",
  mail: "Responder a um email", report: "Fazer um relatório", solve: "Resolver um problema", analyse: "Analisar uma planta",
  message: "Descreva o que precisa ou o que devemos verificar…", send: "Enviar", stop: "Interromper", attach: "Anexar um ficheiro", mic: "Ditar o meu pedido", stopMic: "Parar o ditado", recording: "Ditado em curso…",
  files: "Documentos e opções", options: "Opções", preferences: "Memória e preferências", thorough: "Aprofundada", fast: "Rápida", response: "Resposta", web: "Pesquisa na Internet",
  choosePlan: "Juntar uma planta já importada", chooseDoc: "Juntar um documento já importado", appliedPrefs: "Preferências aplicadas", removeFile: "Retirar do contexto", addAs: "Juntar este ficheiro como",
  docKind: "Orçamento, fatura ou documento", planKind: "Planta a medir", chatError: "Não foi possível carregar esta conversa.", historyError: "Não foi possível carregar o histórico.",
  keyboard: "Enter para enviar · Shift + Enter para uma nova linha", copied: "Resposta copiada", copy: "Copiar", correct: "Corrigir / esclarecer",
};
const EN = {
  latest: "Latest reply", workspace: "My workspace", home: "Home", assistant: "Assistant BTP", search: "Find a tool…", allTools: "All tools", searchHint: "Find a feature by name or task.", noResults: "No tools found. Try another word.",
  clear: "Clear", menu: "Menu", close: "Close", daily: "Everyday work", measure: "Plans and site", manage: "Management", discover: "Resources", account: "Company & account", skip: "Skip to content",
  favorites: "Favourites", today: "Today", chantiers: "Sites", billing: "Quotes & invoices", clients: "Clients", library: "Library",
  addFavorite: "Add to favourites", removeFavorite: "Remove from favourites", favoritesHint: "Click a tool’s star to pin it here.",
  new: "Create", newQuote: "Create a quote", estimate: "Estimate a project", plan: "Plans & takeoffs", quotes: "Quotes", calculators: "Calculators", theme: "Switch theme", logout: "Sign out", personal: "Homeowner workspace", professional: "Professional workspace",
  settings: "Settings", subscription: "My subscription", welcome: "What would you like to do today?", subtitle: "Your projects, documents and assistant, in one place.", ask: "Ask the assistant", askDesc: "A question, an email or a site report.", planDesc: "Import a PDF, DXF or DWG.", quoteDesc: "Prepare a document for your client.", estimateDesc: "Describe your project and budget.", prices: "Compare materials", pricesDesc: "Find products and prices.",
  activity: "Continue my work", projectSearch: "Search projects…", noProjectsFound: "No projects match your search.", projectEmpty: "Your first project starts here", projectEmptyDesc: "Create an estimate to track your budget and progress here.", loading: "Loading your workspace…", loadError: "Some data could not be loaded.", retry: "Retry", deleteTitle: "Delete this project?", deleteDesc: "The project will be deleted. This action cannot be undone.", delete: "Delete", cancel: "Cancel", deleteError: "Deletion failed. Please try again.",
  moreTools: "Explore more", moreDesc: "Technical analysis, profitability, price library and DPGF import.", getStarted: "Get started with ConstruPilot", newInvoice: "Create an invoice", smart: "Describe a project to AI", history: "Conversations", newChat: "New conversation", historySearch: "Search conversations…", noHistory: "Your conversations will appear here.", noHistoryMatch: "No conversations found.", chatTitle: "How can I help?", chatIntro: "Describe what you need. Add a plan, a quote or your notes to get started.",
  mail: "Reply to an email", report: "Write a site report", solve: "Solve a problem", analyse: "Analyse a plan", message: "Describe what you need or what should be checked…", send: "Send", stop: "Stop", attach: "Attach a file", mic: "Dictate my request", stopMic: "Stop dictation", recording: "Recording…", files: "Documents and options", options: "Options", preferences: "Memory and preferences", thorough: "Thorough", fast: "Fast", response: "Response", web: "Web search", choosePlan: "Add an imported plan", chooseDoc: "Add an imported document", appliedPrefs: "Applied preferences", removeFile: "Remove from context", addAs: "Add this file as", docKind: "Quote, invoice or document", planKind: "Plan to measure", chatError: "Could not load this conversation.", historyError: "Could not load conversation history.", keyboard: "Enter to send · Shift + Enter for a new line", copied: "Response copied", copy: "Copy", correct: "Correct / clarify",
};

export const normalizeSearch = (text) => String(text || "").normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLocaleLowerCase().trim();
export function useWorkspaceCopy() {
  const { lang, t } = useI18n();
  const translations = lang === "pt" ? PT : lang === "en" ? EN : lang === "fr" ? FR : null;
  // Reuse existing translations for established controls in the other languages.
  const aliases = { home: "nav.dashboard", assistant: "nav.assistant", account: "nav.account", newQuote: "nav.newquote", estimate: "nav.estimator", plan: "nav.plan2d", quotes: "nav.tracking", calculators: "nav.calculators", preferences: "nav.preferences", subscription: "nav.pricing", logout: "nav.logout", prices: "nav.prices" };
  return (key) => WORKSPACE_EXTRA[lang]?.[key] || translations?.[key] || (!translations && aliases[key] ? t(aliases[key], FR[key]) : null) || WORKSPACE_EXTRA.fr[key] || FR[key] || key;
}

