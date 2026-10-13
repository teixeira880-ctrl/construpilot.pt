import { HeadTags } from "@/components/SEO";

// Défauts par route publique — une page peut les surcharger avec son propre <SEO>.
export const ROUTE_SEO = {
  "/": { title: "Devis travaux IA & estimation rénovation", description: "Chiffrez un devis, comparez les prix matériaux et estimez votre rénovation avec l'assistant IA du BTP.", ptPath: "/" },
  "/particuliers": { title: "Estimer ses travaux : devis clair et détaillé", description: "Particuliers : estimez votre rénovation, comparez les devis reçus et suivez votre chantier avec ConstruPilot.", ptPath: "/particuliers" },
  "/metre": { title: "Éditeur de plans IA : du plan au devis", description: "Importez un plan DWG ou PDF, obtenez les quantités et un devis à vos prix. Traçabilité complète des hypothèses.", ptPath: "/metre" },
  "/portugal": { title: "Orçamentos de obra com IA em Portugal", description: "Estime a sua obra, compare preços de materiais e prepare orçamentos profissionais com IVA e NIF.", lang: "pt", ptPath: "/" },
  "/investisseurs": { title: "Investisseurs : la plateforme IA du BTP", description: "Chiffres clés, vision et feuille de route de ConstruPilot, la plateforme IA des devis et chantiers." },
  "/fonctionnalites": { title: "Fonctionnalités ConstruPilot", description: "Estimation IA, analyse de plans DWG, métré, devis PDF, approvisionnement et suivi de chantier : tout ConstruPilot.", ptPath: "/fonctionnalites" },
  "/login": { title: "Connexion", description: "Connectez-vous à votre espace ConstruPilot pour retrouver vos projets, estimations et devis.", noindex: true },
  "/inscription": { title: "Créer un compte", description: "Créez votre compte ConstruPilot gratuit : estimations, devis et suivi de chantier en un seul endroit.", noindex: true },
  "/smart-project": { title: "Smart Project : estimation IA détaillée", description: "Décrivez votre projet, l'IA propose un chiffrage lot par lot avec quantités et fourchettes de prix.", ptPath: "/smart-project" },
  "/estimation": { title: "Estimateur travaux gratuit", description: "Chiffrez votre chantier en 3 étapes : type de travaux, surface, niveau de finition. Estimation immédiate et gratuite.", ptPath: "/estimation" },
  "/calculateurs": { title: "Calculateurs BTP : béton, placo, carrelage", description: "Calculez vos quantités de matériaux (béton, parpaings, placo, carrelage, peinture) avec les pertes incluses.", ptPath: "/calculateurs" },
  "/prix": { title: "Comparateur prix matériaux BTP", description: "Comparez les prix des matériaux chez Point.P, Leroy Merlin, Castorama, Brico Dépôt et d'autres enseignes.", ptPath: "/prix" },
  "/diy": { title: "Guides travaux pas à pas", description: "Tutoriels et guides pratiques pour réaliser vos travaux, avec conseils de sécurité et matériaux nécessaires.", ptPath: "/diy" },
  "/coach": { title: "Coach travaux IA", description: "Posez vos questions travaux à l'IA : ordre des lots, prix, réglementation, choix des matériaux.", ptPath: "/coach" },
  "/photo": { title: "Analyse photo de travaux par IA", description: "Envoyez une photo de votre pièce ou façade : l'IA identifie les travaux et propose une estimation.", ptPath: "/photo" },
  "/tarifs": { title: "Tarifs et abonnements", description: "Offre gratuite, Pro et Pro Business : choisissez le plan ConstruPilot adapté à votre activité.", ptPath: "/tarifs" },
  "/aide": { title: "Aide & assistance ConstruPilot", description: "Centre d'aide : questions fréquentes, assistant en ligne, espace client et formulaire de contact avec réponse sous 1 jour ouvré.", ptPath: "/aide" },
  "/comparatif": { title: "Comparatif logiciels devis BTP", description: "Comparez ConstruPilot aux autres logiciels de devis et de gestion de chantier, fonction par fonction." },
  "/blog": { title: "Blog travaux, devis et BTP", description: "Guides, prix et actualités du bâtiment : rénovation, devis, matériaux, réglementation et outils IA.", ptPath: "/blog" },
  "/marketplace": { title: "Marketplace pros du bâtiment", description: "Trouvez un professionnel vérifié pour vos travaux ou recevez des demandes qualifiées près de chez vous.", ptPath: "/marketplace" },
  "/docs": { title: "Documentation et guides d'utilisation", description: "Prise en main de ConstruPilot : estimation, plans, devis, factures et intégrations, expliqués pas à pas.", ptPath: "/docs" },
  "/developpeurs": { title: "API développeurs", description: "Intégrez les estimations et devis ConstruPilot dans vos outils grâce à l'API et aux webhooks.", ptPath: "/developpeurs" },
  "/enterprise": { title: "Offre Entreprise et marque blanche", description: "Déployez ConstruPilot pour vos équipes ou vos clients : marque blanche, SSO et accompagnement dédié.", ptPath: "/enterprise" },
  "/mentions-legales": { title: "Mentions légales", description: "Éditeur, hébergeur et informations légales du site ConstruPilot." },
  "/confidentialite": { title: "Politique de confidentialité", description: "Comment ConstruPilot collecte, utilise et protège vos données personnelles." },
  "/scanner-devis": { title: "Scanner de devis travaux IA", description: "Envoyez un devis PDF : chaque ligne est comparée aux prix du marché pour savoir s'il est correct ou trop cher.", noindex: true },
  "/cgv": { title: "Conditions générales d'utilisation et de vente", description: "Conditions d'accès, abonnements, résiliation et responsabilités du service ConstruPilot." },
  "/privacy": { title: "Politique de confidentialité des applications", description: "Données collectées, autorisations demandées par les applications mobiles, sous-traitants, conservation et suppression de compte. Version française et anglaise." },
  "/app-privacy": { title: "Politique de confidentialité des applications", description: "Données collectées, autorisations demandées par les applications mobiles, sous-traitants, conservation et suppression de compte.", canonical: "/privacy" },
  "/confidentialite-apps": { title: "Politique de confidentialité des applications", description: "Données collectées, autorisations demandées par les applications mobiles, sous-traitants, conservation et suppression de compte.", canonical: "/privacy" },
  "/reinitialiser": { title: "Réinitialiser mon mot de passe", description: "Recevez un lien pour définir un nouveau mot de passe ConstruPilot.", noindex: true },
  "/radar": { title: "Radar chantiers : permis de construire", description: "Repérez les permis de construire publiés près de votre entreprise et estimez leur potentiel de chantier." },
};

export function DefaultSEO() {
  return <HeadTags routeDefaults={ROUTE_SEO} />;
}
