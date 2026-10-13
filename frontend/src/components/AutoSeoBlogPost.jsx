import { useEffect, useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { Calendar, ArrowLeft, ArrowRight } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import NewsletterForm from "@/components/NewsletterForm";

// Rendu d'un article publié via le webhook AutoSEO (contenu dynamique en base).
export default function AutoSeoBlogPost({ slug }) {
  const [state, setState] = useState({ loading: true, article: null, notFound: false });
  const [related, setRelated] = useState([]);

  useEffect(() => {
    let alive = true;
    setState({ loading: true, article: null, notFound: false });
    api.get(`/blog/autoseo/${slug}`)
      .then(({ data }) => {
        if (!alive) return;
        setState({ loading: false, article: data, notFound: false });
        api.get(`/blog/autoseo?lang=${data.language_code || "fr"}`).then(({ data: l }) => {
          if (!alive) return;
          const kw = new Set([...(data.keywords || []), data.seed_keyword].filter(Boolean).map((k) => String(k).toLowerCase()));
          const score = (x) => (x.keywords || []).filter((k) => kw.has(String(k).toLowerCase())).length + (x.seed_keyword && kw.has(String(x.seed_keyword).toLowerCase()) ? 2 : 0);
          setRelated((l.articles || []).filter((x) => x.slug !== slug).sort((a, b) => score(b) - score(a)).slice(0, 3));
        }).catch(() => {});
      })
      .catch((e) => alive && setState({
        loading: false, article: null, notFound: e?.response?.status === 404,
      }));
    return () => { alive = false; };
  }, [slug]);

  if (state.loading) {
    return (
      <div className="min-h-[50vh] grid place-items-center" data-testid="autoseo-loading">
        <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }
  if (state.notFound || !state.article) return <Navigate to="/blog" replace />;

  const a = state.article;
  const published = a.published_at || a.created_at;

  const heroAbs = a.hero_image_url?.startsWith("/") ? `https://construpilot.pt${a.hero_image_url}` : a.hero_image_url;
  const jsonLd = [{
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    "headline": a.title,
    "description": a.meta_description,
    "image": heroAbs || undefined,
    "datePublished": a.published_at,
    "dateModified": a.updated_at || a.published_at,
    "inLanguage": a.language_code,
    "author": { "@type": "Organization", "name": "ConstruPilot" },
    "publisher": {
      "@type": "Organization",
      "name": "ConstruPilot",
      "logo": { "@type": "ImageObject", "url": "https://construpilot.pt/logo512.png" },
    },
    "mainEntityOfPage": `https://construpilot.pt/blog/${a.slug}`,
    "keywords": Array.isArray(a.keywords) ? a.keywords.join(", ") : a.meta_keywords,
  }];

  if (Array.isArray(a.faq_schema) && a.faq_schema.length) {
    jsonLd.push({
      "@context": "https://schema.org",
      "@type": "FAQPage",
      "mainEntity": a.faq_schema.map((f) => ({
        "@type": "Question",
        "name": f.question,
        "acceptedAnswer": { "@type": "Answer", "text": f.answer },
      })),
    });
  }

  jsonLd.push({
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    "itemListElement": [
      { "@type": "ListItem", "position": 1, "name": "Início", "item": "https://construpilot.pt/" },
      { "@type": "ListItem", "position": 2, "name": "Blog", "item": "https://construpilot.pt/blog" },
      { "@type": "ListItem", "position": 3, "name": a.title, "item": `https://construpilot.pt/blog/${a.slug}` },
    ],
  });

  return (
    <>
      <SEO
        title={a.title}
        description={a.meta_description}
        keywords={a.meta_keywords || (Array.isArray(a.keywords) ? a.keywords.join(", ") : "")}
        canonical={`/blog/${a.slug}`}
        image={heroAbs}
        type="article"
        jsonLd={jsonLd}
      />

      <article className="mx-auto max-w-3xl px-5 lg:px-8 py-12 lg:py-16">
        <nav aria-label="Caminho de navegação" className="mb-6" data-testid="breadcrumb">
          <ol className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <li><Link to="/" className="hover:text-primary" data-testid="breadcrumb-home">Início</Link></li>
            <li aria-hidden="true" className="opacity-50">/</li>
            <li><Link to="/blog" className="hover:text-primary" data-testid="breadcrumb-blog">Blog</Link></li>
            <li aria-hidden="true" className="opacity-50">/</li>
            <li className="text-foreground font-medium truncate max-w-[60vw] sm:max-w-md" aria-current="page">
              {a.title}
            </li>
          </ol>
        </nav>

        <h1 className="mt-3 font-display text-3xl lg:text-5xl font-extrabold tracking-tighter" data-testid="autoseo-title">
          {a.title}
        </h1>
        {published && (
          <div className="mt-5 flex items-center gap-4 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-1">
              <Calendar className="h-3 w-3" />
              {new Date(published).toLocaleDateString("pt-PT", { day: "numeric", month: "long", year: "numeric" })}
            </span>
          </div>
        )}

        {a.hero_image_url && (
          <img src={a.hero_image_url} alt={a.hero_image_alt || a.title}
               className="mt-8 rounded-sm border border-border w-full aspect-[16/9] object-cover" />
        )}

        <div
          className="mt-10 prose-blog space-y-4 text-[15px] leading-relaxed"
          data-testid="autoseo-body"
          dangerouslySetInnerHTML={{ __html: (a.content_html || "").replace(/<h1[^>]*>[\s\S]*?<\/h1>/i, "") }}
        />

        {a.infographic_image_url && (
          <img src={a.infographic_image_url} alt={`Infographie — ${a.title}`}
               className="mt-10 rounded-sm border border-border w-full" data-testid="autoseo-infographic" />
        )}

        <div className="mt-12 surface p-6 grid md:grid-cols-[1fr_auto] gap-4 items-center border-primary/40">
          <div>
            <p className="font-display font-bold text-lg">Pronto para orçamentar a sua obra?</p>
            <p className="text-sm text-muted-foreground mt-1">
              Descreva o seu projeto — ConstruPilot devolve-lhe um orçamento calculado em 30 segundos, gratuito.
            </p>
          </div>
          <Link to="/smart-project">
            <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white" data-testid="blog-cta-smart">
              Experimentar agora <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>

        <nav className="mt-8 flex flex-wrap gap-2 text-xs" data-testid="blog-internal-links" aria-label="Ferramentas ConstruPilot">
          {[["/estimation", "Estimador de obras"], ["/calculadoras", "Calculadoras de construção"], ["/precos", "Preços de materiais"], ["/medicoes", "Medições IA para os profissionais"]].map(([to, l]) => (
            <Link key={to} to={to} className="px-3 py-1.5 rounded-full border border-border hover:border-primary hover:text-primary transition-colors">{l}</Link>
          ))}
        </nav>

        <div className="mt-8"><NewsletterForm source={`article:${a.slug}`} /></div>

        {related.length > 0 && (
          <section className="mt-12" data-testid="blog-related">
            <p className="overline text-[10px] mb-3">Ler também</p>
            <div className="grid sm:grid-cols-3 gap-4">
              {related.map((r) => (
                <Link key={r.slug} to={`/blog/${r.slug}`} className="surface overflow-hidden group hover:-translate-y-0.5 transition-transform" data-testid={`blog-related-${r.slug}`}>
                  {r.hero_image_url && <img src={r.hero_image_url} alt={r.title} loading="lazy" className="aspect-[16/9] w-full object-cover" />}
                  <div className="p-4">
                    <p className="font-display font-bold text-sm leading-snug group-hover:text-primary transition-colors">{r.title}</p>
                    <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{r.excerpt || r.meta_description}</p>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        )}
      </article>
    </>
  );
}
