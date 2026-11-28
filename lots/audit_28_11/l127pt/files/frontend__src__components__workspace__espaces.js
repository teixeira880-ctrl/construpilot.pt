// Ergonomie phase 2-3 : navigation par OBJECTIF (5 espaces) et menu par MÉTIER.
// Aucune route n'est supprimée : les espaces regroupent les suites existantes ; le reste
// (assistant, compte…) apparaît sous « Autres ». Le métier ne fait que choisir les entrées
// épinglées dans « L'essentiel » ; tout reste accessible par « Tous les outils » et Ctrl K.

export const SPACES = [
  { id: "orcamentar", label: { fr: "Chiffrer", pt: "Orçamentar", en: "Price" }, question: { fr: "Combien ça coûte ?", pt: "Quanto custa?", en: "How much will it cost?" } },
  { id: "projetar", label: { fr: "Concevoir", pt: "Projetar", en: "Design" }, question: { fr: "À quoi ça va ressembler ?", pt: "Como vai ficar?", en: "What will it look like?" } },
  { id: "calcular", label: { fr: "Calculer", pt: "Calcular", en: "Engineer" }, question: { fr: "Est-ce que ça tient ?", pt: "É seguro?", en: "Will it stand?" } },
  { id: "medir", label: { fr: "Mesurer", pt: "Medir", en: "Measure" }, question: { fr: "Quelles quantités ?", pt: "Que quantidades?", en: "What quantities?" } },
  { id: "gerir", label: { fr: "Gérer le chantier", pt: "Gerir a obra", en: "Run the job" }, question: { fr: "Où en est le chantier ?", pt: "Como corre a obra?", en: "How is the job going?" } },
];
export const OTHER_SPACE = { id: "outros", label: { fr: "Autres", pt: "Outros", en: "Other" }, question: { fr: "", pt: "", en: "" } };

// Suite (id du hub) → espace.
const BY_SUITE = {
  estimar: "orcamentar", documentos: "orcamentar", precos: "orcamentar",
  arquiteto: "projetar", licenciamento: "projetar", imagens: "projetar",
  engenharia: "calcular",
  plantas: "medir",
  obra: "gerir", faturacao: "gerir", empresa: "gerir", oportunidades: "gerir", diagnostico: "gerir",
};
// Outils hors suite : par route, puis par famille.
const BY_PATH = {
  "/devis": "orcamentar", "/devis-editeur": "orcamentar", "/estimation": "orcamentar", "/calculateurs": "orcamentar", "/dpgf": "orcamentar", "/cctp": "projetar",
  "/chantiers": "gerir", "/clients": "gerir", "/planning": "gerir", "/factures": "gerir", "/marketplace": "gerir",
};
// No .pt as ligações não têm « family » : último recurso pela rubrica.
const BY_GROUP = { billing: "orcamentar", library: "orcamentar", chantiers: "gerir", clients: "gerir" };

export const spaceOf = (item) => (item && (BY_SUITE[item.hub] || BY_PATH[item.to] || BY_GROUP[item.group])) || OTHER_SPACE.id;
export const spaceLabel = (id, lang = "pt") => {
  const s = SPACES.find(x => x.id === id) || OTHER_SPACE;
  return s.label[lang] || s.label.pt;
};
export const spaceQuestion = (id, lang = "pt") => {
  const s = SPACES.find(x => x.id === id) || OTHER_SPACE;
  return s.question[lang] || s.question.pt;
};
export const SPACE_ORDER = [...SPACES.map(s => s.id), OTHER_SPACE.id];

// ── Métier (phase 3) ────────────────────────────────────────────────────────
export const METIERS = [
  { id: "", label: { fr: "Tous les métiers", pt: "Todas as profissões", en: "All trades" } },
  { id: "entreprise", label: { fr: "Entreprise du bâtiment", pt: "Empresa de construção", en: "Building contractor" } },
  { id: "grande", label: { fr: "Grande entreprise", pt: "Grande empresa", en: "Large company" } },
  { id: "ingenieur", label: { fr: "Ingénieur / BET", pt: "Engenheiro / gabinete", en: "Engineer" } },
  { id: "architecte", label: { fr: "Architecte", pt: "Arquiteto", en: "Architect" } },
];
export const metierLabel = (id, lang = "pt") => {
  const m = METIERS.find(x => x.id === id) || METIERS[0];
  return m.label[lang] || m.label.pt;
};
const METIER_KEY = "cp_metier";
export const readMetier = () => {
  try { const v = localStorage.getItem(METIER_KEY) || ""; return METIERS.some(m => m.id === v) ? v : ""; } catch { return ""; }
};
export const saveMetier = (v) => { try { localStorage.setItem(METIER_KEY, v || ""); } catch { /* stockage indisponible : choix non mémorisé */ } };

// Entrées épinglées par métier (routes de hub ; une route absente pour l'utilisateur est ignorée).
export const METIER_ESSENTIALS = {
  entreprise: ["/dashboard", "/devis", "/chantiers", "/clients", "/faturacao", "/precos-biblioteca", "/assistant"],
  grande: ["/dashboard", "/chantiers", "/obra", "/devis", "/documentos-orcamentos", "/empresa-equipa", "/faturacao", "/assistant"],
  ingenieur: ["/dashboard", "/estudos-engenharia", "/plantas-medicoes", "/precos-biblioteca", "/chantiers", "/assistant"],
  architecte: ["/dashboard", "/arquiteto-bim", "/licenciamento", "/plantas-medicoes", "/imagens-3d", "/assistant"],
};
