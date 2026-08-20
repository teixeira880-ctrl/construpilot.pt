import { Link, useParams } from "react-router-dom";
import { Clock, Calendar, ArrowLeft, ArrowRight } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { BLOG_ARTICLES, getArticle } from "@/lib/blogArticles";
import { ARTICLE_BODIES } from "@/lib/blogBodies";
import AutoSeoBlogPost from "@/components/AutoSeoBlogPost";

export default function BlogPost() {
  const { slug } = useParams();
  const article = getArticle(slug);
  if (!article) return <AutoSeoBlogPost slug={slug} />;

  const body = ARTICLE_BODIES[slug];
  const idx = BLOG_ARTICLES.findIndex((a) => a.slug === slug);
  const prev = BLOG_ARTICLES[idx - 1];
  const next = BLOG_ARTICLES[idx + 1];

  const jsonLd = {
    "@context": "https://schema.org",
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
        <Link to="/blog" className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-primary mb-6"
              data-testid="back-to-blog">
          <ArrowLeft className="h-3 w-3" /> Retour au blog
        </Link>

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
            <Clock className="h-3 w-3" /> {article.readingMinutes} min de lecture
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
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">← Précédent</span>
              <p className="mt-1 font-display font-semibold group-hover:text-primary transition-colors">
                {prev.title}
              </p>
            </Link>
          ) : <div />}
          {next && (
            <Link to={`/blog/${next.slug}`}
                  data-testid="blog-next-link"
                  className="surface p-4 hover:border-primary transition-colors group text-right">
              <span className="text-[10px] uppercase tracking-widest text-muted-foreground">Suivant →</span>
              <p className="mt-1 font-display font-semibold group-hover:text-primary transition-colors">
                {next.title}
              </p>
            </Link>
          )}
        </nav>
      </article>
    </>
  );
}
