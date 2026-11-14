import { Construction, FileBadge, Map, Images, Files, Stethoscope, Sigma, BookOpen, Wallet, ListChecks, Briefcase, Target, Plug } from "lucide-react";

// Apps fusionadas: cada « suite » é UMA só app no menu. As ferramentas que a
// compõem mantêm as suas rotas (ligações diretas, Assistente BTP e Aurora
// continuam a funcionar), mas deixam de aparecer como apps separadas.
// `members` = rotas das ferramentas, pela ordem dos separadores.
// `family` = espaço de cor existente (FAMILY_COLORS).
export const APP_SUITES = [
  {
    id: "engenharia", to: "/estudos-engenharia", icon: Construction, family: "etudes", group: "chantiers", pin: true,
    label: { pt: "Estudos de Engenharia", fr: "Études d'ingénierie", en: "Engineering studies" },
    desc: {
      pt: "Estrutura, descida de cargas, aberturas e lintéis, escadas, térmica, eletricidade e canalização — tudo numa só app.",
      fr: "Structure, descente de charges, ouvertures et linteaux, escaliers, thermique, électricité et plomberie — tout en une app.",
      en: "Structure, load descent, openings and lintels, stairs, thermal, electrical and plumbing — all in one app.",
    },
    members: ["/estudo-moradia", "/structuro", "/escaliers", "/planos-execucao", "/renovation", "/structuro-bet", "/missions"],
  },
  {
    id: "licenciamento", to: "/licenciamento", icon: FileBadge, family: "etudes", group: "chantiers", pin: true, personalPin: true,
    label: { pt: "Licenciamento & Arquitetura", fr: "Permis & architecture", en: "Permits & architecture" },
    desc: {
      pt: "Licenciamento automático de moradias, terrenos (BUPi, PDM, RAN, REN), MDT, maquete 3D, urbanismo, estudos de licença e autorização de obras.",
      fr: "Permis automatique de maisons, terrains (BUPi, PDM, RAN, REN), MNT, maquette 3D, urbanisme, études de permis et autorisation de travaux.",
      en: "Automatic house permits, land plots (BUPi, PDM, RAN, REN), terrain model, 3D model, planning, permit studies and works authorisation.",
    },
    members: ["/licenciamento-automatico", "/terrenos", "/mdt", "/maquete-3d", "/urbanismo", "/etudes-pc", "/particulares/autorizacao-obras"],
  },
  {
    id: "plantas", to: "/plantas-medicoes", icon: Map, family: "plans", group: "chantiers", pin: true,
    label: { pt: "Plantas, Medições & BIM", fr: "Plans, métrés & BIM", en: "Plans, take-off & BIM" },
    desc: {
      pt: "Medições em plantas PDF/DXF/DWG, métodos de medição e dossier, medição rápida, BIM / Autodesk, BIM Studio, controlo de cotas, comparação de plantas e medição em fotografia.",
      fr: "Métré sur plans PDF/DXF/DWG, méthodes de métré et dossier, métré rapide, BIM / Autodesk, BIM Studio, contrôle des cotes, comparaison de plans et mesure sur photo.",
      en: "Take-off on PDF/DXF/DWG plans, take-off methods and file, quick measure, BIM / Autodesk, BIM Studio, dimension checks, plan comparison and photo measuring.",
    },
    members: ["/plan", "/metodos-medicao", "/medicao-rapida", "/plans-pro", "/bim", "/controle-cotes", "/plan/compare", "/mesure-photo"],
  },
  {
    id: "imagens", to: "/imagens-3d", icon: Images, family: "ia", group: "chantiers",
    label: { pt: "Imagens & Renders 3D", fr: "Images & rendus 3D", en: "Images & 3D renders" },
    desc: {
      pt: "Ilustrações IA, fotomontagens e renders antes/depois.",
      fr: "Illustrations IA, photomontages et rendus avant/après.",
      en: "AI illustrations, photomontages and before/after renders.",
    },
    members: ["/estudio-imagens", "/rendu-ia"],
  },
  {
    id: "documentos", to: "/documentos-orcamentos", icon: Files, family: "devis", group: "billing", pin: true,
    label: { pt: "Análise de documentos & mapas", fr: "Analyse de documents & DPGF", en: "Documents & bills of quantities" },
    desc: {
      pt: "Mapa de quantidades do arquiteto → orçamento, leitura e verificação de documentos e scanner de orçamentos.",
      fr: "DPGF de l'architecte → devis, lecture et vérification de documents, scanner de devis.",
      en: "Architect's bill of quantities → quote, document reading and checks, and quote scanner.",
    },
    members: ["/dpgf", "/analyse-documents", "/scanner-devis"],
  },
  {
    id: "diagnostico", to: "/diagnostico", icon: Stethoscope, family: "ia", group: "discover", pin: true,
    label: { pt: "Diagnóstico & conselhos", fr: "Diagnostic & conseils", en: "Diagnosis & advice" },
    desc: {
      pt: "Resolver um problema (fissuras, humidade), analisar uma fotografia, orientador IA e faço eu mesmo.",
      fr: "Résoudre un problème (fissures, humidité), analyser une photo, coach IA et bricolage.",
      en: "Solve a problem (cracks, damp), analyse a photo, AI coach and do it yourself.",
    },
    members: ["/btp-solver", "/photo", "/coach", "/diy"],
  },
  {
    id: "estimar", to: "/estimar", icon: Sigma, family: "devis", group: "today", personalPin: true,
    label: { pt: "Estimar & calcular", fr: "Estimer & calculer", en: "Estimate & calculate" },
    desc: {
      pt: "Estimador de obras, Smart Project e calculadoras de construção.",
      fr: "Estimateur de travaux, Smart Project et calculateurs.",
      en: "Works estimator, Smart Project and construction calculators.",
    },
    members: ["/estimation", "/smart-project", "/calculadoras"],
  },
  {
    id: "precos", to: "/precos-biblioteca", icon: BookOpen, family: "devis", group: "library", pin: true, personalPin: true,
    label: { pt: "Preços & biblioteca", fr: "Prix & bibliothèque", en: "Prices & library" },
    desc: {
      pt: "Preços de materiais, o seu catálogo de preços e a biblioteca de artigos.",
      fr: "Prix des matériaux, votre catalogue et la bibliothèque d'ouvrages.",
      en: "Material prices, your price catalogue and item library.",
    },
    members: ["/precos", "/mon-catalogue", "/bibliotheque"],
  },
  {
    id: "faturacao", to: "/faturacao", icon: Wallet, family: "devis", group: "billing", pin: true,
    label: { pt: "Faturação", fr: "Facturation", en: "Invoicing" },
    desc: {
      pt: "Faturas, faturação eletrónica e autos de medição.",
      fr: "Factures, facturation électronique et situations de travaux.",
      en: "Invoices, e-invoicing and progress claims.",
    },
    members: ["/factures", "/factures-electroniques", "/situations"],
  },
  {
    id: "obra", to: "/obra", icon: ListChecks, family: "projets", group: "chantiers", pin: true,
    label: { pt: "Acompanhamento & planeamento", fr: "Suivi & planning de chantier", en: "Site tracking & planning" },
    desc: {
      pt: "Acompanhamento de obra (avanço, notas, fotografias) e planeamento Gantt.",
      fr: "Suivi de chantier (avancement, notes, photos) et planning Gantt.",
      en: "Site tracking (progress, notes, photos) and Gantt planning.",
    },
    members: ["/suivi-chantier", "/planning"],
  },
  {
    id: "empresa", to: "/empresa-equipa", icon: Briefcase, family: "projets", group: "account",
    label: { pt: "Empresa & equipa", fr: "Entreprise & équipe", en: "Company & team" },
    desc: {
      pt: "Espaço empresa, equipa e funções, RH e registo de ponto.",
      fr: "Espace entreprise, équipe et rôles, RH et pointage.",
      en: "Company space, team and roles, HR and time tracking.",
    },
    members: ["/entreprise", "/equipe", "/rh"],
  },
  {
    id: "oportunidades", to: "/oportunidades", icon: Target, family: "projets", group: "clients", pin: true,
    label: { pt: "Pedidos & oportunidades", fr: "Demandes & opportunités", en: "Leads & opportunities" },
    desc: {
      pt: "Os seus pedidos de clientes, radar de obras e opiniões de clientes.",
      fr: "Vos demandes clients, radar de chantiers et avis clients.",
      en: "Your client enquiries, construction radar and customer reviews.",
    },
    members: ["/mes-demandes", "/radar", "/mes-avis"],
  },
  {
    id: "api", to: "/api-integracoes", icon: Plug, family: "compte", group: "account",
    label: { pt: "API & integrações", fr: "API & intégrations", en: "API & integrations" },
    desc: {
      pt: "Documentação da API e chaves de acesso.",
      fr: "Documentation de l'API et clés d'accès.",
      en: "API documentation and access keys.",
    },
    members: ["/docs", "/developpeurs"],
  },
];

const _matches = (pathname, to) => pathname === to || pathname.startsWith(to + "/");

export const suiteLabel = (suite, lang) => suite.label[lang] || suite.label.pt;
export const suiteDesc = (suite, lang) => suite.desc[lang] || suite.desc.pt;
export const suiteById = (id) => APP_SUITES.find(s => s.id === id);
export const suiteByHub = (to) => APP_SUITES.find(s => s.to === to);

// Suite de uma rota: ganha a correspondência mais longa
// (ex.: /plan/compare → plantas, /structuro/calcul → engenharia).
export const suiteOfPath = (pathname) => {
  let best = null; let bestLen = -1;
  for (const suite of APP_SUITES) {
    if (_matches(pathname, suite.to) && suite.to.length > bestLen) { best = suite; bestLen = suite.to.length; }
    for (const member of suite.members) {
      if (_matches(pathname, member) && member.length > bestLen) { best = suite; bestLen = member.length; }
    }
  }
  return best;
};

// Rota membro → rota do hub da sua suite; senão a própria rota.
export const suiteHubFor = (to) => {
  const suite = APP_SUITES.find(s => s.members.includes(to));
  return suite ? suite.to : to;
};

export const SUITE_MEMBER_PATHS = new Set(APP_SUITES.flatMap(s => s.members));
