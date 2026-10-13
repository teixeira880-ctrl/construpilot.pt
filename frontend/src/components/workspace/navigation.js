import { AssistantMark } from "@/components/assistant/AssistantMark";
import { Trash2, Bot, LayoutDashboard, FileText, Calculator, Ruler, Search, Users, HardHat, Building2, Receipt, Layers, Camera, Truck, Wand2, Radar, Contact, Library, Tag, Brain, KeyRound, Sparkles, Wrench, FileSearch, MessageSquare, Handshake, TrendingUp, Inbox, Shield, Globe, LifeBuoy, FileSpreadsheet, Footprints, Leaf, CalendarRange } from "lucide-react";

export const AssistantIcon = ({ size = 18, className = "" }) => (
  <AssistantMark size={size} className={className} />
);

// A single catalogue drives the sidebar, search and mobile navigation.
// These visibility rules complement the existing server/route permissions.
export const WORKSPACE_LINKS = [
  { to: "/dashboard", key: "nav.dashboard", label: "Tableau de bord", ui: "home", icon: LayoutDashboard, group: "today", pin: true },
  { to: "/assistant", key: "nav.assistant", label: "Assistant BTP", ui: "assistant", icon: AssistantIcon, group: "assistant", pin: true, min: "particulier_payant", upsell: true, words: "chat aide mail courrier compte rendu aurora assistant btp" },
  { to: "/chantiers", key: "nav.chantiers", label: "Dossiers chantier", icon: HardHat, group: "chantiers", pro: true, pin: true, words: "dossier chantier client plans devis photos affaire" },
  { to: "/devis", key: "nav.tracking", label: "Suivi devis", ui: "quotes", icon: FileText, group: "billing", pro: true, perm: "devis", pin: true },
  { to: "/devis-editeur", key: "nav.newquote", label: "Nouveau devis", ui: "newQuote", icon: FileText, group: "billing", pro: true, perm: "devis", upsell: true, pin: true },
  { to: "/factures", key: "nav.invoices", label: "Factures", icon: Receipt, group: "billing", pro: true, perm: "factures", pin: true },
  { to: "/clients", key: "nav.clients", label: "Clients", icon: Contact, group: "clients", pro: true, pin: true },
  { to: "/corbeille", key: "nav.trash", label: "Corbeille", icon: Trash2, group: "account", pro: true, words: "supprimé récupérer restaurer devis effacé" },
  { to: "/situations", key: "nav.situations", label: "Situations de travaux", icon: Layers, group: "billing", min: "business", perm: "situations" },
  { to: "/dpgf", key: "nav.dpgf", label: "DPGF architecte → devis", icon: FileSpreadsheet, group: "billing", pro: true, perm: "devis", pin: true, words: "dpgf bpu dqe bordereau excel cctp appel offres sous-traitant chiffrage architecte" },
  { to: "/analyse-documents", key: "nav.docintel", label: "Analyse de documents", icon: FileSearch, group: "billing", pro: true, pin: true, words: "dpgf devis pdf excel provenance vérification tva quantités formule source cctp facture lecture" },
  { to: "/plan", key: "nav.plan2d", label: "Plans & métrés", ui: "plan", icon: Ruler, group: "chantiers", pro: true, pin: true, upsell: true, words: "pdf dwg dxf surfaces metré métré" },
  { to: "/agents", key: "nav.agents", label: "Pilote ConstruPilot", icon: Bot, group: "assistant", pin: true, personalPin: true, words: "agent automatique dossier devis métré détection comparaison arrière-plan tâche fond automatisation" },
  { to: "/renovation", key: "nav.renovation", label: "Rénovation énergétique", icon: Leaf, group: "chantiers", pro: true, pin: true, words: "renopilot énergie dpe audit isolation thermique scénarios rénovation passoire" },
  { to: "/structuro", key: "nav.structuro", label: "StructuroPilot (étude)", icon: Building2, group: "chantiers", pro: true, words: "structure poutre mur porteur ouverture semelle étude descente charges ipn ipe hea heb bet eurocode" },
  { to: "/structuro-bet", key: "nav.betdossier", label: "Analyse de dossier BET", icon: FileSearch, group: "chantiers", pro: true, pin: true, words: "bet bureau études note calcul révision indice incohérence contrôle plan comparer versions dossier" },
  { to: "/btp-solver", key: "nav.solver", label: "Résoudre un problème", icon: Wrench, group: "chantiers", pin: true, words: "fissure humidité pathologie diagnostic solution dtu" },
  { to: "/plans-pro", key: "nav.plansPro", label: "Plans BIM / Autodesk", icon: Layers, group: "chantiers", min: "pro", pin: false, words: "autodesk revit ifc vision quantités murs portes fenêtres" },
  { to: "/controle-cotes", key: "nav.cotes", label: "Contrôle des cotes", icon: Ruler, group: "chantiers", pro: true, pin: false, words: "murs dimensions interieur plan" },
  { to: "/escaliers", key: "nav.stairs", label: "Calcul d'escaliers", icon: Footprints, group: "chantiers", pro: true, pin: true, words: "escalier marches giron contremarche blondel dtu 36.3 quart tournant hélicoïdal béton armé paillasse ferraillage" },
  { to: "/suivi-chantier", key: "nav.site", label: "Suivi de chantier", icon: HardHat, group: "chantiers", pro: true, perm: "chantier", pin: true },
  { to: "/planning", label: "Planning de chantier", icon: CalendarRange, group: "chantiers", pro: true, pin: true, words: "planning gantt chemin critique équipes retard replanification ordonnancement or-tools délais" },
  { to: "/plan/compare", label: "Comparer des plans", icon: Layers, group: "chantiers", pro: true },
  { to: "/appro", key: "nav.appro", label: "Analyse technique & Appro IA", icon: Truck, group: "chantiers", pro: true, words: "acier ferraillage fournisseurs commande" },
  { to: "/rendu-ia", key: "nav.render", label: "Rendu IA (avant/après)", icon: Wand2, group: "chantiers", min: "particulier_payant" },
  { to: "/etudes-pc", key: "nav.studies", label: "Études PC", icon: FileSearch, group: "chantiers", pro: true, words: "permis construire" },
  { to: "/mesure-photo", key: "nav.photomeasure", label: "Mesurer sur photo", icon: Camera, group: "chantiers", min: "particulier_payant" },
  { to: "/estimation", key: "nav.estimator", label: "Estimateur", ui: "estimate", icon: Calculator, group: "today", personalPin: true },
  { to: "/smart-project", label: "Smart Project", ui: "smart", icon: Sparkles, group: "today" },
  { to: "/prix", key: "nav.prices", label: "Prix matériaux", icon: Search, group: "library", personalPin: true },
  { to: "/calculateurs", key: "nav.calculators", label: "Calculateurs", icon: Calculator, group: "library", personalPin: true },
  { to: "/scanner-devis", key: "nav.scanner", label: "Scanner de devis", icon: FileSearch, group: "billing", subscriber: true },
  { to: "/entreprise", key: "nav.company", label: "Espace Entreprise", icon: Building2, group: "account", min: "business", perm: "entreprise" },
  { to: "/ma-page", key: "nav.myPage", label: "Ma page & mes documents", icon: Globe, group: "clients", pro: true, pin: true, words: "site vitrine page publique en-tête pied de page pdf personnalisation photos réalisations" },
  { to: "/equipe", key: "nav.team", label: "Équipe", icon: Users, group: "account", min: "business" },
  { to: "/rh", key: "hr.nav", label: "RH — Pointage", icon: Users, group: "account", min: "business", perm: "rh" },
  { to: "/mon-catalogue", key: "nav.catalog", label: "Catalogue prix", icon: Tag, group: "library", pro: true, perm: "catalogue" },
  { to: "/bibliotheque", key: "nav.library", label: "Bibliothèque", icon: Library, group: "library", pin: true, pro: true },
  { to: "/rentabilite", label: "Rapport de rentabilité", icon: TrendingUp, group: "billing", pro: true, perm: "factures" },
  { to: "/factures-electroniques", label: "Facturation électronique", icon: Receipt, group: "billing", pro: true, perm: "factures" },
  { to: "/mes-demandes", key: "nav.myleads", label: "Mes demandes", icon: Inbox, group: "clients", pin: true, pro: true },
  { to: "/radar", key: "nav.radar", label: "Radar Chantiers", icon: Radar, group: "clients", pro: true },
  { to: "/mes-avis", key: "nav.reviews", label: "Avis clients", icon: MessageSquare, group: "clients", pro: true },
  { to: "/fournisseur", label: "Espace fournisseur", icon: Truck, group: "account", pro: true },
  { to: "/photo", key: "nav.photo", label: "Analyse photo", icon: Camera, group: "discover" },
  { to: "/coach", key: "nav.coach", label: "Coach IA", icon: MessageSquare, group: "assistant" },
  { to: "/diy", key: "nav.diy", label: "Je le fais moi-même", icon: Wrench, group: "discover", personalPin: true },
  { to: "/marketplace", key: "nav.marketplace", label: "Trouver un pro", icon: Wrench, group: "discover", personalPin: true },
  { to: "/blog", key: "nav.blog", label: "Blog", icon: FileSearch, group: "discover" },
  { to: "/fonctionnalites", key: "nav.features", label: "Fonctionnalités", icon: Sparkles, group: "discover" },
  { to: "/comparatif", key: "nav.compare", label: "Comparatif", icon: Tag, group: "discover" },
  { to: "/docs", key: "nav.docs", label: "API & Développeurs", icon: FileSearch, group: "discover", min: "business" },
  { to: "/developpeurs", label: "Clés API", icon: KeyRound, group: "account", min: "business" },
  { to: "/preferences", key: "nav.preferences", label: "Mémoire et préférences", ui: "preferences", icon: Brain, group: "account" },
  { to: "/compte", key: "nav.account", label: "Mon compte", ui: "account", icon: KeyRound, group: "account" },
  { to: "/tarifs", key: "nav.pricing", label: "Tarifs & abonnement", ui: "subscription", icon: Sparkles, group: "account" },
  { to: "/inviter", key: "nav.referral", label: "Parrainer", icon: Handshake, group: "account" },
  { to: "/investisseurs", key: "nav.investors", label: "Investisseurs", icon: Handshake, group: "discover" },
  { to: "/aide", key: "nav.help", label: "Aide & assistance", icon: LifeBuoy, group: "discover", words: "aide support assistance contact faq help ajuda" },
  { to: "/admin", key: "nav.admin", label: "Administration", icon: Shield, group: "account", admin: true },
  { to: "/admin/despesas", label: "Dépenses des API", icon: Receipt, group: "account", admin: true, pin: true, words: "despesas coûts costs budget autodesk merci facteur" },
  { to: "/admin/growth", label: "Growth · SEO & IA", icon: TrendingUp, group: "account", admin: true, pin: true, words: "growth seo visibilité ia référencement contenus blog audit" },
];
export const WORKSPACE_GROUPS = ["favorites", "today", "chantiers", "billing", "clients", "library", "assistant", "discover", "account"];
// Keep every specialist tool available in the directory; only daily work is pinned.
export const workspaceEssentials = (links, professional) => {
  const paths = professional
    ? ["/dashboard", "/chantiers", "/plan", "/agents", "/devis", "/factures", "/clients", "/assistant"]
    : ["/dashboard", "/estimation", "/assistant", "/agents", "/calculateurs", "/prix", "/marketplace"];
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
export const LEVEL_LABELS = { particulier_payant: "Particulier Payant", pro: "Pro", business: "Business" };
export const UPSELL_BENEFITS = {
  "/assistant": "Rédigez devis, courriers et comptes-rendus en quelques secondes avec l'IA BTP.",
  "/devis-editeur": "Créez des devis et factures professionnels, chiffrés et conformes.",
  "/devis": "Suivez l'état de vos devis : envoyés, acceptés, relancés.",
  "/factures": "Éditez vos factures et suivez les paiements, TVA incluse.",
  "/clients": "Centralisez vos clients, leur historique et leurs documents.",
  "/chantiers": "Regroupez plans, photos, devis et suivi par affaire.",
  "/plan": "Mesurez surfaces et métrés directement sur vos plans PDF/DWG.",
  "/agents": "Lancez des agents qui regroupent plans, métré, chiffrage et PDF en arrière-plan.",
  "/renovation": "Audit énergétique, scénarios de rénovation et aides.",
  "/structuro": "Structurez une étude : collecte guidée, traçabilité des sources.",
  "/structuro-bet": "Contrôlez un dossier BET : révisions, incohérences et rapport de contrôle.",
  "/plans-pro": "Analyse de plans Pro : quantités murs/portes/fenêtres par IA.",
  "/controle-cotes": "Vérifiez automatiquement les cotes et dimensions des plans.",
  "/escaliers": "Calcul d'escaliers conforme DTU 36.3 (loi de Blondel).",
  "/suivi-chantier": "Pilotez l'avancement, les notes et photos de chantier.",
  "/planning": "Gantt déterministe : chemin critique, équipes, replanification et propositions de réorganisation.",
  "/dpgf": "Transformez un DPGF architecte en devis chiffré automatiquement.",
  "/analyse-documents": "Vérifiez provenance, TVA et quantités de vos documents.",
  "/situations": "Facturation à l'avancement avec déduction d'acompte.",
  "/appro": "Analyse technique et commande d'approvisionnement assistée.",
  "/rendu-ia": "Générez un rendu avant/après réaliste de vos travaux.",
  "/mesure-photo": "Mesurez des éléments directement sur une photo.",
  "/etudes-pc": "Montez vos dossiers de permis de construire plus vite.",
  "/entreprise": "Pilotez votre entreprise : KPIs, membres, rôles.",
  "/equipe": "Invitez votre équipe et gérez les accès par rôle.",
  "/rh": "Pointage chantier, feuilles d'heures et présence.",
  "/mon-catalogue": "Votre bibliothèque de prix et d'ouvrages réutilisables.",
  "/bibliotheque": "Modèles et ouvrages prêts à réutiliser dans vos devis.",
  "/ma-page": "Votre page vitrine publique et vos documents personnalisés.",
  "/radar": "Détectez les chantiers et opportunités près de vous.",
  "/docs": "API & intégrations pour connecter vos outils.",
};
export const benefitFor = (to, level) => UPSELL_BENEFITS[to] || `Fonction incluse dans l'offre ${LEVEL_LABELS[level] || "payante"}.`;
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

