import { useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { Clock, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { BLOG_ARTICLES } from "@/lib/blogArticles";
import { BLOG_ARTICLES_PT } from "@/lib/blogPortugal";
import { useI18n } from "@/context/I18nContext";

const SORO_SRC = "https://app.trysoro.com/api/embed/5160a050-06b9-473f-aa12-4cd9a5150663";

export function SoroBlog() {
  const holder = useRef(null);
  const { lang } = useI18n();
  const source = lang === "pt" ? BLOG_ARTICLES_PT : BLOG_ARTICLES;
  const latest = source.slice(0, 3);

  useEffect(() => {
    // Ne charge le script Soro qu'en contexte non-PT (feed remote FR, indisponible en PT).
    if (lang === "pt") return;
    // Charge le script Soro une seule fois (compatible SPA React) — silencieux tant qu'il est désactivé
    let script = document.querySelector(`script[data-soro="1"]`);
    if (!script) {
      script = document.createElement("script");
      script.src = SORO_SRC;
      script.defer = true;
      script.setAttribute("data-soro", "1");
      document.body.appendChild(script);
    }
  }, [lang]);

  return (
    <section className="border-t border-border bg-secondary/20" id="blog" data-testid="blog-section">
      <div className="mx-auto max-w-[1500px] px-6 lg:px-10 py-24 lg:py-32">
        <div className="flex items-end justify-between gap-6 flex-wrap mb-12">
          <div>
            <p className="overline">O blogue ConstruPilot</p>
            <h2 className="mt-4 font-display text-3xl lg:text-4xl font-bold tracking-tight">
              Conselhos, medições e actualidades da construção
            </h2>
          </div>
          <Link to="/blog">
            <Button variant="outline" className="rounded-lg gap-2" data-testid="blog-see-all">
              Ver todos os artigos <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>

        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6" data-testid="blog-home-list">
          {latest.map((a) => (
            <Link
              key={a.slug}
              to={`/blog/${a.slug}`}
              data-testid={`blog-home-card-${a.slug}`}
              className="surface overflow-hidden group hover:-translate-y-1 transition-transform"
            >
              <div className="aspect-[16/9] overflow-hidden">
                <img src={a.cover} alt={a.title} loading="lazy"
                     className="h-full w-full object-cover group-hover:scale-105 transition-transform duration-500" />
              </div>
              <div className="p-5 grid gap-3">
                <div className="flex items-center gap-2 text-[10px] uppercase tracking-widest">
                  <span className="text-primary font-bold">{a.category}</span>
                  <span className="text-muted-foreground">·</span>
                  <span className="text-muted-foreground inline-flex items-center gap-1">
                    <Clock className="h-3 w-3" /> {a.readingMinutes} min
                  </span>
                </div>
                <h3 className="font-display text-lg font-bold leading-snug group-hover:text-primary transition-colors">
                  {a.title}
                </h3>
                <p className="text-sm text-muted-foreground line-clamp-3">{a.excerpt}</p>
                <span className="text-primary text-sm font-semibold inline-flex items-center gap-1 mt-1">
                  Ler o artigo <ArrowRight className="h-3 w-3" />
                </span>
              </div>
            </Link>
          ))}
        </div>

        {/* Embed Soro — só carregado em contexto não-PT (conteúdo remoto FR não traduzível). */}
        {lang !== "pt" && (
          <div id="soro-blog" ref={holder} data-testid="soro-blog" className="mt-8" />
        )}
      </div>
    </section>
  );
}
