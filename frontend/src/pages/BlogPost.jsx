import { Link, useParams } from "react-router-dom";
import { Clock, Calendar, ArrowLeft, ArrowRight } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { BLOG_ARTICLES, getArticle } from "@/lib/blogArticles";
import { ARTICLE_BODIES } from "@/lib/blogBodies";
import { BLOG_ARTICLES_PT, getArticlePT, ARTICLE_BODIES_PT } from "@/lib/blogPortugal";
import { useI18n } from "@/context/I18nContext";
import AutoSeoBlogPost from "@/components/AutoSeoBlogPost";
import NewsletterForm from "@/components/NewsletterForm";

export default function BlogPost() {
  const { slug } = useParams();
  const { lang } = useI18n();
  const isPT = lang === "pt";
  const article = isPT ? getArticlePT(slug) : getArticle(slug);
  if (!article) return <AutoSeoBlogPost slug={slug} />;

  const body = (isPT ? ARTICLE_BODIES_PT : ARTICLE_BODIES)[slug];
  const list = isPT ? BLOG_ARTICLES_PT : BLOG_ARTICLES;
  const idx = list.findIndex((a) => a.slug === slug);
  const prev = list[idx - 1];
  const next = list[idx + 1];

  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "BlogPosting",
        "headline": article.title,
        "description": article.excerpt,
        "image": article.cover,
        "datePublished": article.published,
        "dateModified": article.updated,
        "author": { "@type": "Organization", "name": "ConstruPilot" },
        "publisher": {
          "@type": "Organization",
          "name": "ConstruPilot",
          "logo": {
            "@type": "ImageObject",
            "url": "https://construpilot.fr/logo512.png",
          },
        },
        "mainEntityOfPage": `https://construpilot.fr/blog/${slug}`,
        "articleSection": article.category,
        "keywords": article.keywords,
      },
      {
        "@type": "BreadcrumbList",
        "itemListElement": [
          { "@type": "ListItem", "position": 1, "name": "Accueil", "item": "https://construpilot.fr/" },
          { "@type": "ListItem", "position": 2, "name": "Blog", "item": "https://construpilot.fr/blog" },
          { "@type": "ListItem", "position": 3, "name": article.title, "item": `https://construpilot.fr/blog/${slug}` },
        ],
      },
    ],
  };

  return (
    <>
      <SEO
        title={article.title}
        description={article.excerpt}
        keywords={article.keywords}
        canonical={`/blog/${slug}`}
        image={article.cover}
        type="article"
        jsonLd={jsonLd}
      />

      <article className="mx-auto max-w-3xl px-5 lg:px-8 py-12 lg:py-16">
        <nav aria-label="Fil d'Ariane" className="mb-6" data-testid="breadcrumb">
          <ol className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <li><Link to="/" className="hover:text-primary" data-testid="breadcrumb-home">{isPT ? "Início" : "Accueil"}</Link></li>
            <li aria-hidden="true" className="opacity-50">/</li>
            <li><Link to="/blog" className="hover:text-primary" data-testid="breadcrumb-blog">Blog</Link></li>
            <li aria-hidden="true" className="opacity-50">/</li>
            <li className="text-foreground font-medium truncate max-w-[60vw] sm:max-w-md" aria-current="page">
              {article.title}
            </li>
          </ol>
        </nav>

        <p className="overline">{article.category}</p>
        <h1 className="mt-3 font-display text-3xl lg:text-5xl font-extrabold tracking-tighter">
          {article.title}
        </h1>
        <div className="mt-5 flex items-center gap-4 text-xs text-muted-foreground">
          <span className="inline-flex items-center gap-1">
            <Calendar className="h-3 w-3" />
            {new Date(article.published).toLocaleDateString("fr-FR", { day:"numeric", month:"long", year:"numeric" })}
          </span>
          <span className="inline-flex items-center gap-1">
            <Clock className="h-3 w-3" /> {article.readingMinutes} {isPT ? "min de leitura" : "min de lecture"}
          </span>
        </div>

        <img src={article.cover} alt={article.title}
             className="mt-8 rounded-sm border border-border w-full aspect-[16/9] object-cover" />

        <div className="mt-10 prose-blog space-y-4 text-[15px] leading-relaxed" data-testid="blog-body">
          {body}
        </div>

        {/* CTA in-article */}
        <div className="mt-12 surface p-6 grid md:grid-cols-[1fr_auto] gap-4 items-center border-primary/40">
          <div>
            <p className="font-display font-bold text-lg">Prêt à chiffrer votre chantier ?</p>
            <p className="text-sm text-muted-foreground mt-1">
              Décrivez votre projet — ConstruPilot vous rend un devis chiffré en 30 secondes, gratuit.
            </p>
          </div>
          <Link to="/smart-project">
            <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white" data-testid="blog-cta-smart">
              Essayer maintenant <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>

        {/* Prev / Next */}
        <nav className="mt-12 grid md:grid-cols-2 gap-3" aria-label="Autres articles">
          {prev ? (
            <Link to={`/blog/${prev.slug}`}
                  data-testid="blog-prev-link"
                  className="surface p-4 hover:border-primary transition-colors group">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">← {isPT ? "Anterior" : "Précédent"}</span>
              <p className="mt-1 font-display font-semibold group-hover:text-primary transition-colors">
                {prev.title}
              </p>
            </Link>
          ) : <div />}
          {next && (
            <Link to={`/blog/${next.slug}`}
                  data-testid="blog-next-link"
                  className="surface p-4 hover:border-primary transition-colors group text-right">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">{isPT ? "Seguinte" : "Suivant"} →</span>
              <p className="mt-1 font-display font-semibold group-hover:text-primary transition-colors">
                {next.title}
              </p>
            </Link>
          )}
        </nav>
        <div className="mt-10"><NewsletterForm source={`article:${slug}`} /></div>
      </article>
    </>
  );
}
