import { Helmet } from "react-helmet-async";

/**
 * SEO — Reusable per-page meta / structured-data component.
 *
 * Usage:
 *   <SEO title="Estimation Rénovation" description="..." canonical="/estimation" />
 *
 * Falls back to global defaults defined in /public/index.html when props are omitted.
 */
export function SEO({
  title,
  description,
  canonical,
  image,
  keywords,
  type = "website",
  noindex = false,
  jsonLd,
}) {
  const base = "https://construpilot.pt";
  const url = canonical ? `${base}${canonical}` : base;
  const fullTitle = title
    ? `${title} · ConstruPilot`
    : "ConstruPilot — Orçamentos de Obras com IA | Portugal";
  const ogImg = image || `${base}/og-cover.jpg`;

  return (
    <Helmet>
      <title>{fullTitle}</title>
      {description && <meta name="description" content={description} />}
      {keywords && <meta name="keywords" content={keywords} />}
      <link rel="canonical" href={url} />
      {noindex && <meta name="robots" content="noindex, follow" />}

      {/* OpenGraph */}
      <meta property="og:type" content={type} />
      <meta property="og:url" content={url} />
      <meta property="og:title" content={fullTitle} />
      {description && <meta property="og:description" content={description} />}
      <meta property="og:image" content={ogImg} />

      {/* Twitter */}
      <meta name="twitter:card" content="summary_large_image" />
      <meta name="twitter:title" content={fullTitle} />
      {description && <meta name="twitter:description" content={description} />}
      <meta name="twitter:image" content={ogImg} />

      {/* Optional JSON-LD (BreadcrumbList, FAQPage, HowTo…) */}
      {jsonLd && (
        <script type="application/ld+json">{JSON.stringify(jsonLd)}</script>
      )}
    </Helmet>
  );
}
