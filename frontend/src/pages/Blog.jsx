import { Link } from "react-router-dom";
import { useEffect, useState } from "react";
import { Clock, ArrowRight } from "lucide-react";
import { SEO } from "@/components/SEO";
import { BLOG_ARTICLES } from "@/lib/blogArticles";
import { BLOG_ARTICLES_PT } from "@/lib/blogPortugal";
import { useI18n } from "@/context/I18nContext";
import { api } from "@/lib/api";
import NewsletterForm from "@/components/NewsletterForm";

const dynToCard = (a) => ({
  slug: a.slug, title: a.title, excerpt: a.excerpt || a.meta_description || "",
  cover: a.hero_image_url || "/og-image.jpg", category: a.seed_keyword || "Guide",
  readingMinutes: a.reading_minutes || 4, publishedAt: a.published_at,
});

const JSON_LD = {
  "@context": "https://schema.org",
  "@type": "Blog",
  "name": "Blog ConstruPilot — Orçamentos de obras, renovação e construção",
  "url": "https://construpilot.fr/blog",
  "blogPost": BLOG_ARTICLES.map((a) => ({
    "@type": "BlogPosting",
    "headline": a.title,
    "url": `https://construpilot.fr/blog/${a.slug}`,
    "datePublished": a.published,
    "dateModified": a.updated,
    "image": a.cover,
  })),
};

export default function Blog() {
  const { lang } = useI18n();
  const isPT = lang === "pt";
  const [dyn, setDyn] = useState([]);
  useEffect(() => {
    api.get(`/blog/autoseo?lang=${isPT ? "pt" : "fr"}`)
      .then(({ data }) => setDyn((data.articles || []).map(dynToCard)))
      .catch(() => setDyn([]));
  }, [isPT]);
  const staticArticles = isPT ? BLOG_ARTICLES_PT : BLOG_ARTICLES;
  const staticSlugs = new Set(staticArticles.map((a) => a.slug));
  const articles = [...dyn.filter((a) => !staticSlugs.has(a.slug)), ...staticArticles];
  return (
    <>
      <SEO
        title="Blog"
        description={isPT
          ? "Guias e atualidades da construção por ConstruPilot: custo de renovação 2026 por distrito, IVA das obras (6%/23%), como estimar uma obra em minutos."
          : "Guias, dicas e atualidades da construção por ConstruPilot: custo renovação 2026, IVA a 10%, medições 2D, comparador de preços materiais, orçamento cliente, plantas 3D."}
        keywords={isPT
          ? "blog construção Portugal, custo renovação, IVA obras 6, estimar obra, orçamento obras"
          : "blog construção, custo renovação, IVA 10 porcento, medições 2D, orçamento obras, preço materiais"}
        canonical="/blog"
        jsonLd={JSON_LD}
      />
      <section className="border-b border-border">
        <div className="mx-auto max-w-[1500px] px-5 lg:px-8 py-16 lg:py-20">
          <p className="overline">{isPT ? "O jornal" : "O jornal"}</p>
          <h1 className="mt-3 font-display text-4xl lg:text-5xl font-extrabold tracking-tighter">
            {isPT ? <>Guias & atualidades <span className="text-primary">Construção 2026</span></>
                  : <>Guias & atualidades <span className="text-primary">BTP 2026</span></>}
          </h1>
          <p className="mt-4 text-sm md:text-base text-muted-foreground max-w-2xl">
            {isPT
              ? "Preços de obras, IVA na reabilitação, métodos e orçamentos: o jornal do ConstruPilot com respostas concretas para o mercado português."
              : "Preços de obras, métodos de medições, fiscalidade de renovação, comparativos de materiais: o jornal de ConstruPilot dá-lhe as respostas concretas do terreno, atualizadas todas as semanas."}
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-[1500px] px-5 lg:px-8 py-16">
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="blog-list">
          {articles.map((a) => (
            <Link
              key={a.slug}
              to={`/blog/${a.slug}`}
              data-testid={`blog-card-${a.slug}`}
              className="surface overflow-hidden group hover:-translate-y-1 transition-transform"
            >
              <div className="aspect-[16/9] overflow-hidden">
                <img
                  src={a.cover} alt={a.title}
                  loading="lazy"
                  className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-500"
                />
              </div>
              <div className="p-5 grid gap-3">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest">
                  <span className="text-primary font-bold">{a.category}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className="text-muted-foreground inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {a.readingMinutes} min
                  </span>
                </div>
                <h2 className="font-display text-lg font-bold leading-snug group-hover:text-primary transition-colors">
                  {a.title}
                </h2>
                <p className="text-sm text-muted-foreground line-clamp-3">{a.excerpt}</p>
                <span className="text-primary text-sm font-semibold inline-flex items-center gap-1 mt-1">
                  {isPT ? "Ler o artigo" : "Lire l'article"} <ArrowRight className="h-3 w-3" />
                </span>
              </div>
            </Link>
          ))}
        </div>
        <div className="mt-12 max-w-2xl"><NewsletterForm source="blog-list" /></div>
      </section>
    </>
  );
}
