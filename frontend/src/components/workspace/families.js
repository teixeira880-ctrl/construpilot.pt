import { Building2, Shield, Ruler, Sparkles, FileSearch, Wrench, Calculator, Library, Receipt, CalendarRange, Users, Radar, KeyRound } from "lucide-react";

// Apps fusionadas: cada família é UMA só app no menu. As ferramentas que a
// compõem mantêm as suas rotas (ligações diretas, Assistente BTP e Aurora
// continuam a funcionar), mas deixam de aparecer como apps separadas.
// `members` = rotas das ferramentas, na ordem dos separadores.
export const APP_FAMILIES = [
  {
    id: "engenharia", to: "/estudos-engenharia", icon: Building2, group: "chantiers", pin: true,
    label: { pt: "Estudos de Engenharia", en: "Engineering studies", fr: "Études d'ingénierie" },
    desc: {
      pt: "Estrutura, descida de cargas, aberturas e lintéis, escadas, térmica, eletricidade e canalização — tudo numa só app.",
      en: "Structure, load descent, openings and lintels, stairs, thermal, electrical and plumbing — all in one app.",
      fr: "Structure, descente de charges, ouvertures et linteaux, escaliers, thermique, électricité et plomberie — tout en une app.",
    },
    members: ["/estudo-moradia", "/structuro", "/escaliers", "/planos-execucao", "/renovation", "/structuro-bet", "/missions"],
  },
  {
    id: "licenciamento", to: "/licenciamento", icon: Shield, group: "chantiers", pin: true,
    label: { pt: "Licenciamento & Arquitetura", en: "Permits & architecture", fr: "Permis & architecture" },
    desc: {
      pt: "Licenciamento automático de moradias, estudo de arquitetura e urbanismo, processos de licença e autorização de obras.",
      en: "Automatic house permits, architecture and planning study, permit files and works authorisation.",
      fr: "Permis automatique de maisons, étude d'architecture et d'urbanisme, dossiers de permis et autorisation de travaux.",
    },
    members: ["/licenciamento-automatico", "/urbanismo", "/etudes-pc", "/particulares/autorizacao-obras"],
  },
  {
    id: "plantas", to: "/plantas-medicoes", icon: Ruler, group: "chantiers", pin: true,
    label: { pt: "Plantas, Medições & BIM", en: "Plans, take-off & BIM", fr: "Plans, métrés & BIM" },
    desc: {
      pt: "Medições em plantas PDF/DWG, BIM/IFC, controlo de cotas, comparação de plantas e medição em fotografia.",
      en: "Take-off on PDF/DWG plans, BIM/IFC, dimension checks, plan comparison and photo measuring.",
      fr: "Métrés sur plans PDF/DWG, BIM/IFC, contrôle des cotes, comparaison de plans et mesure sur photo.",
    },
    members: ["/plan", "/medicao-rapida", "/plans-pro", "/bim", "/controle-cotes", "/plan/compare", "/mesure-photo"],
  },
  {
    id: "imagens", to: "/imagens-3d", icon: Sparkles, group: "chantiers",
    label: { pt: "Imagens & Renders 3D", en: "Images & 3D renders", fr: "Images & rendus 3D" },
    desc: {
      pt: "Ilustrações IA, fotomontagens e renders antes/depois.",
      en: "AI illustrations, photomontages and before/after renders.",
      fr: "Illustrations IA, photomontages et rendus avant/après.",
    },
    members: ["/estudio-imagens", "/rendu-ia"],
  },
  {
    id: "documentos", to: "/documentos-orcamentos", icon: FileSearch, group: "billing", pin: true,
    label: { pt: "Análise de documentos & mapas", en: "Documents & bills of quantities", fr: "Analyse de documents & DPGF" },
    desc: {
      pt: "Mapa de quantidades do arquiteto → orçamento, leitura e verificação de documentos e scanner de orçamentos.",
      en: "Architect's bill of quantities → quote, document reading and checks, and quote scanner.",
      fr: "DPGF de l'architecte → devis, lecture et vérification de documents, scanner de devis.",
    },
    members: ["/dpgf", "/analyse-documents", "/scanner-devis"],
  },
  {
    id: "diagnostico", to: "/diagnostico", icon: Wrench, group: "discover", pin: true,
    label: { pt: "Diagnóstico & conselhos", en: "Diagnosis & advice", fr: "Diagnostic & conseils" },
    desc: {
      pt: "Resolver um problema (fissuras, humidade), analisar uma fotografia, orientador IA e faço eu mesmo.",
      en: "Solve a problem (cracks, damp), analyse a photo, AI coach and do it yourself.",
      fr: "Résoudre un problème (fissures, humidité), analyser une photo, coach IA et bricolage.",
    },
    members: ["/btp-solver", "/photo", "/coach", "/diy"],
  },
  {
    id: "estimar", to: "/estimar", icon: Calculator, group: "today", personalPin: true,
    label: { pt: "Estimar & calcular", en: "Estimate & calculate", fr: "Estimer & calculer" },
    desc: {
      pt: "Estimador de obras, Smart Project e calculadoras de construção.",
      en: "Works estimator, Smart Project and construction calculators.",
      fr: "Estimateur de travaux, Smart Project et calculateurs.",
    },
    members: ["/estimation", "/smart-project", "/calculadoras"],
  },
  {
    id: "precos", to: "/precos-biblioteca", icon: Library, group: "library", pin: true, personalPin: true,
    label: { pt: "Preços & biblioteca", en: "Prices & library", fr: "Prix & bibliothèque" },
    desc: {
      pt: "Preços de materiais, o seu catálogo de preços e a biblioteca de artigos.",
      en: "Material prices, your price catalogue and item library.",
      fr: "Prix des matériaux, votre catalogue et la bibliothèque d'ouvrages.",
    },
    members: ["/precos", "/mon-catalogue", "/bibliotheque"],
  },
  {
    id: "faturacao", to: "/faturacao", icon: Receipt, group: "billing", pin: true,
    label: { pt: "Faturação", en: "Invoicing", fr: "Facturation" },
    desc: {
      pt: "Faturas, faturação eletrónica e autos de medição.",
      en: "Invoices, e-invoicing and progress claims.",
      fr: "Factures, facturation électronique et situations de travaux.",
    },
    members: ["/factures", "/factures-electroniques", "/situations"],
  },
  {
    id: "obra", to: "/obra", icon: CalendarRange, group: "chantiers", pin: true,
    label: { pt: "Acompanhamento & planeamento", en: "Site tracking & planning", fr: "Suivi & planning de chantier" },
    desc: {
      pt: "Acompanhamento de obra (avanço, notas, fotografias) e planeamento Gantt.",
      en: "Site tracking (progress, notes, photos) and Gantt planning.",
      fr: "Suivi de chantier (avancement, notes, photos) et planning Gantt.",
    },
    members: ["/suivi-chantier", "/planning"],
  },
  {
    id: "empresa", to: "/empresa-equipa", icon: Users, group: "account",
    label: { pt: "Empresa & equipa", en: "Company & team", fr: "Entreprise & équipe" },
    desc: {
      pt: "Espaço empresa, equipa e funções, RH e registo de ponto.",
      en: "Company space, team and roles, HR and time tracking.",
      fr: "Espace entreprise, équipe et rôles, RH et pointage.",
    },
    members: ["/entreprise", "/equipe", "/rh"],
  },
  {
    id: "oportunidades", to: "/oportunidades", icon: Radar, group: "clients", pin: true,
    label: { pt: "Pedidos & oportunidades", en: "Leads & opportunities", fr: "Demandes & opportunités" },
    desc: {
      pt: "Os seus pedidos de clientes, radar de obras e opiniões de clientes.",
      en: "Your client enquiries, construction radar and customer reviews.",
      fr: "Vos demandes clients, radar de chantiers et avis clients.",
    },
    members: ["/mes-demandes", "/radar", "/mes-avis"],
  },
  {
    id: "api", to: "/api-integracoes", icon: KeyRound, group: "account",
    label: { pt: "API & integrações", en: "API & integrations", fr: "API & intégrations" },
    desc: {
      pt: "Documentação da API e chaves de acesso.",
      en: "API documentation and access keys.",
      fr: "Documentation de l'API et clés d'accès.",
    },
    members: ["/docs", "/developpeurs"],
  },
];

const _matches = (pathname, to) => pathname === to || pathname.startsWith(to + "/");

export const familyLabel = (family, lang) => family.label[lang] || family.label.pt;
export const familyDesc = (family, lang) => family.desc[lang] || family.desc.pt;
export const familyById = (id) => APP_FAMILIES.find(f => f.id === id);
export const familyByHub = (to) => APP_FAMILIES.find(f => f.to === to);

// Família de uma rota: a correspondência mais longa ganha
// (ex.: /plan/compare → plantas, /structuro/calcul → engenharia).
export const familyOfPath = (pathname) => {
  let best = null; let bestLen = -1;
  for (const family of APP_FAMILIES) {
    if (_matches(pathname, family.to) && family.to.length > bestLen) { best = family; bestLen = family.to.length; }
    for (const member of family.members) {
      if (_matches(pathname, member) && member.length > bestLen) { best = family; bestLen = member.length; }
    }
  }
  return best;
};

// Rota membro (exata ou sub-rota) → rota do hub da família; senão a própria rota.
export const familyHubFor = (to) => {
  const family = APP_FAMILIES.find(f => f.members.includes(to));
  return family ? family.to : to;
};

export const FAMILY_MEMBER_PATHS = new Set(APP_FAMILIES.flatMap(f => f.members));
