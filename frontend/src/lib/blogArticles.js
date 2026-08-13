/**
 * SEO Blog articles — served under /blog/:slug
 *
 * Each article is a plain object with:
 *   slug, title, excerpt, published, updated, cover, category, readingMinutes,
 *   body (JSX)  ← rendered by BlogPost.jsx
 *
 * Add new articles here — they are auto-listed on /blog and included in the
 * dynamic Article JSON-LD injected by BlogPost.jsx.
 */

export const BLOG_ARTICLES = [
  {
    slug: "cout-renovation-2026",
    title: "Coût d'une rénovation en 2026 : prix au m² par région et par lot",
    excerpt: "Combien coûte réellement une rénovation en France en 2026 ? Fourchettes actualisées par région, par gamme de finition et par lot (plomberie, électricité, cuisine, salle de bain, isolation).",
    published: "2026-02-10",
    updated: "2026-02-13",
    cover: "https://images.unsplash.com/photo-1600585154340-be6161a56a0c?w=1200&q=80",
    category: "Rénovation",
    readingMinutes: 7,
    keywords: "coût rénovation 2026, prix rénovation m², prix rénovation appartement, tarif rénovation maison, prix travaux région",
  },
  {
    slug: "devis-tva-10-mode-emploi",
    title: "Devis avec TVA à 10 % : mode d'emploi + attestation prête à envoyer",
    excerpt: "Comment appliquer la TVA à 10 % sur vos devis de rénovation ? Conditions art. 279-0 bis CGI, attestation client obligatoire, et modèle prêt à télécharger. Le guide 2026 pour artisans.",
    published: "2026-02-11",
    updated: "2026-02-13",
    cover: "https://images.unsplash.com/photo-1554224155-6726b3ff858f?w=1200&q=80",
    category: "Fiscalité",
    readingMinutes: 5,
    keywords: "devis TVA 10, attestation TVA rénovation, TVA travaux logement, art 279-0 bis CGI, taux TVA rénovation",
  },
  {
    slug: "guide-metre-2d",
    title: "Guide du métré 2D : mesurer un plan et chiffrer un chantier en 5 minutes",
    excerpt: "Métrer un plan papier ou PDF sans logiciel coûteux ? Voici la méthode complète 2026 : calibrage à l'échelle, détection des murs, calcul des surfaces au m² et export vers devis chiffré.",
    published: "2026-02-12",
    updated: "2026-02-13",
    cover: "https://images.unsplash.com/photo-1503387762-592deb58ef4e?w=1200&q=80",
    category: "Méthode",
    readingMinutes: 6,
    keywords: "métré 2D, mesurer un plan, calcul surface plan, logiciel métré gratuit, chiffrer un devis rapidement",
  },
  {
    slug: "abattre-mur-porteur-reglementation",
    title: "Abattre un mur porteur en 2026 : réglementation, coûts et pièges à éviter",
    excerpt: "Vous voulez ouvrir un mur porteur ? Voici les 5 étapes légales obligatoires, le prix moyen d'une ouverture avec IPN, et les pièges qui font capoter 1 chantier sur 4 en copropriété.",
    published: "2026-02-14",
    updated: "2026-02-14",
    cover: "https://images.unsplash.com/photo-1581094794329-c8112a89af12?w=1200&q=80",
    category: "Structure",
    readingMinutes: 8,
    keywords: "mur porteur, abattre mur porteur, réglementation mur porteur, prix ouverture mur porteur, IPN, bureau d'études, copropriété travaux",
  },
  {
    slug: "permis-construire-2026",
    title: "Permis de construire 2026 : ce qui change, délais réels et cas d'obligation",
    excerpt: "Extension, surélévation, garage, piscine : quand faut-il un permis de construire en 2026 vs une déclaration préalable ? Délais mairie, pièces à fournir, et coût moyen de constitution du dossier.",
    published: "2026-02-15",
    updated: "2026-02-15",
    cover: "https://images.unsplash.com/photo-1600607687939-ce8a6c25118c?w=1200&q=80",
    category: "Administratif",
    readingMinutes: 7,
    keywords: "permis de construire 2026, déclaration préalable travaux, extension maison permis, surélévation permis, délai permis construire, dossier permis",
  },
  {
    slug: "re2020-renovation-guide",
    title: "RE2020 et rénovation : ce que les artisans doivent absolument savoir",
    excerpt: "La Réglementation Environnementale 2020 s'invite dans la rénovation. Bbio, Cep, gaz à effet de serre : quels seuils respecter en travaux d'ampleur, et comment ConstruPilot vous alerte automatiquement.",
    published: "2026-02-16",
    updated: "2026-02-16",
    cover: "https://images.unsplash.com/photo-1518005020951-eccb494ad742?w=1200&q=80",
    category: "Énergie",
    readingMinutes: 6,
    keywords: "RE2020 rénovation, réglementation environnementale 2020, Bbio rénovation, Cep travaux, isolation RE2020, artisan RE2020",
  },
];

export const getArticle = (slug) =>
  BLOG_ARTICLES.find((a) => a.slug === slug);
