import { createContext, useContext, useEffect, useMemo, useState } from "react";
import { useLocation } from "react-router-dom";

const BASE = "https://construpilot.fr";
const PT_BASE = "https://construpilot.pt";
const SUFFIX = " · ConstruPilot";
const DEFAULT_TITLE = "ConstruPilot — Orçamentos de obras com IA e estimativa de remodelação";
const DEFAULT_DESC = "Orçamentos detalhados, estimativa de remodelação, comparador de preços de materiais e análise de plantas: o assistente IA da construção para profissionais e particulares.";

let overridesPromise = null;
const loadOverrides = () => {
  if (!overridesPromise) {
    overridesPromise = fetch(`${process.env.REACT_APP_BACKEND_URL}/api/growth/seo-overrides`)
      .then((r) => (r.ok ? r.json() : {}))
      .then((d) => d.overrides || {})
      .catch(() => ({}));
  }
  return overridesPromise;
};

export const clampTitle = (t) => {
  if (!t) return DEFAULT_TITLE;
  if (/construpilot/i.test(t)) return t.length <= 60 ? t : t.slice(0, 57).trimEnd() + "…";
  return t.length + SUFFIX.length <= 60 ? t + SUFFIX : (t.length <= 60 ? t : t.slice(0, 57).trimEnd() + "…");
};

export const clampDesc = (d) => {
  const s = (d || DEFAULT_DESC).replace(/\s+/g, " ").trim();
  return s.length <= 160 ? s : s.slice(0, 157).replace(/[ ,;:]+\S*$/, "").trimEnd() + "…";
};

const Ctx = createContext({ page: null, setPage: () => {} });

export function SeoProvider({ children }) {
  const [page, setPage] = useState(null);
  const value = useMemo(() => ({ page, setPage }), [page]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

/** Une page déclare ses balises ; un seul émetteur (HeadTags, à la racine) les rend → jamais de doublon. */
export function SEO(props) {
  const { setPage } = useContext(Ctx);
  const key = JSON.stringify(props);
  useEffect(() => { setPage(JSON.parse(key)); return () => setPage(null); }, [key, setPage]);
  return null;
}

/** Émetteur unique des balises <head> (React 19 les hisse dans <head>) : page > défauts de route > repli noindex. */
export function HeadTags({ routeDefaults }) {
  const { page } = useContext(Ctx);
  const { pathname } = useLocation();
  const key = pathname !== "/" && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
  const rd = routeDefaults[key];
  // Une page peut fournir son propre <SEO> ; on hérite alors du ptPath (hreflang pt-PT) du défaut de route si la page ne l'a pas précisé.
  const cfg = page
    ? (rd && rd.ptPath && page.ptPath === undefined ? { ...page, ptPath: rd.ptPath } : page)
    : (rd ? { canonical: key, ...rd } : { canonical: key, noindex: true });
  const path = cfg.canonical || key;
  const [ov, setOv] = useState(null);
  useEffect(() => { let on = true; loadOverrides().then((o) => on && setOv(o[path] || null)); return () => { on = false; }; }, [path]);
  const lang = cfg.lang || "fr";
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);

  const canonicalPath = ov?.canonical || path;
  const url = canonicalPath === "/" ? `${BASE}/` : `${BASE}${canonicalPath}`;
  const fullTitle = clampTitle(ov?.title || cfg.title);
  const desc = clampDesc(ov?.description || cfg.description);
  const ogImg = cfg.image || `${BASE}/og-cover.jpg`;
  return (
    <>
      <title>{fullTitle}</title>
      <meta name="description" content={desc} />
      {cfg.keywords && <meta name="keywords" content={cfg.keywords} />}
      <link rel="canonical" href={url} />
      <meta name="robots" content={cfg.noindex ? "noindex, follow" : "index, follow, max-image-preview:large, max-snippet:-1"} />
      <link rel="alternate" hrefLang={lang === "pt" ? "pt-PT" : "fr-FR"} href={url} />
      {cfg.ptPath && <link rel="alternate" hrefLang="pt-PT" href={`${PT_BASE}${cfg.ptPath}`} />}
      <link rel="alternate" hrefLang="x-default" href={url} />
      <meta property="og:type" content={cfg.type || "website"} />
      <meta property="og:url" content={url} />
      <meta property="og:title" content={fullTitle} />
      <meta property="og:description" content={desc} />
      <meta property="og:image" content={ogImg} />
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      <meta name="twitter:description" content={desc} />
      <meta name="twitter:image" content={ogImg} />
      {cfg.jsonLd && <script type="application/ld+json">{JSON.stringify(cfg.jsonLd)}</script>}
    </>
  );
}
