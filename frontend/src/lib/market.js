// Marché commercial du déploiement : "fr" (construpilot.fr) ou "pt" (construpilot.pt).
// REACT_APP_MARKET force la valeur ; sinon domaine .pt/.fr ; sinon DEFAULT_MARKET du dépôt.
// Seule ligne qui diffère entre les dépôts .fr ("fr") et .pt ("pt") : les domaines de prévisualisation
// (ex. *.emergent.host) ne disent rien du marché.
const DEFAULT_MARKET = "pt";

export function currentMarket() {
  const forced = (process.env.REACT_APP_MARKET || "").toLowerCase();
  if (forced === "fr" || forced === "pt") return forced;
  try {
    const h = (window.location.hostname || "").toLowerCase();
    if (h.endsWith(".pt")) return "pt";
    if (h.endsWith(".fr")) return "fr";
  } catch { /* SSR / tests */ }
  return DEFAULT_MARKET;
}

export const PRICING_PATH = { fr: "/tarifs", pt: "/planos" };

// Format monétaire du marché : "1 009,80 €" (fr-FR) / "1009,80 €" (pt-PT).
export function formatEur(cents, lang, { decimals } = {}) {
  const v = Number(cents || 0) / 100;
  const d = decimals ?? (Number.isInteger(v) ? 0 : 2);
  return new Intl.NumberFormat(lang === "pt" ? "pt-PT" : "fr-FR", {
    style: "currency", currency: "EUR", minimumFractionDigits: d, maximumFractionDigits: d,
  }).format(v);
}

export function formatStorage(bytes, lang) {
  const gb = Number(bytes || 0) / 1024 ** 3;
  if (gb >= 1024) return `${(gb / 1024).toLocaleString(lang === "pt" ? "pt-PT" : "fr-FR")} TB`;
  return `${Math.round(gb).toLocaleString(lang === "pt" ? "pt-PT" : "fr-FR")} GB`;
}

export function formatInt(n, lang) {
  return Number(n || 0).toLocaleString(lang === "pt" ? "pt-PT" : "fr-FR");
}
