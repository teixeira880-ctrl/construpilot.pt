// Artigo do blog HeyCatch (/blog/:slug) — lido em direto via /api/blog/heycatch/:slug (HTML já limpo no servidor).
// Ordem do guia HeyCatch : pontos-chave → índice gerado (h2 com id, sem a FAQ) → corpo → FAQ. Mesmo design dos artigos do blog.
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Calendar, Clock, ArrowRight } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import NewsletterForm from "@/components/NewsletterForm";

const SITE = "https://construpilot.pt";
const RTL = /^(ar|he|fa|ur)/i;
const FAQ_RE = /^(faq|perguntas frequentes|questions fr[ée]quentes|frequently asked)/i;

export const fmtDate = (d) => {
  if (!d) return "";
  const t = new Date(d);
  return Number.isNaN(t.getTime()) ? "" : t.toLocaleDateString("pt-PT", { day: "numeric", month: "long", year: "numeric" });
};

/** Separa o HTML em [antes do 1.º h2 (pontos-chave), resto] e lista os h2 com id para o índice (FAQ excluída). */
export function splitArticle(html) {
  const doc = new DOMParser().parseFromString(`<div>${html || ""}</div>`, "text/html");
  const root = doc.body.firstChild;
  // 2.ª barreira (o servidor já limpa) : nada de script/style/iframe, atributos on* nem URLs javascript:
  root.querySelectorAll("script,style,iframe,object,embed,form,link,meta,base").forEach((n) => n.remove());
  root.querySelectorAll("*").forEach((el) => {
    [...el.attributes].forEach((at) => {
      if (/^on/i.test(at.name) || (/^(href|src|xlink:href)$/i.test(at.name) && /^\s*(javascript|vbscript|data):/i.test(at.value))) el.removeAttribute(at.name);
    });
  });
  root.querySelectorAll("h1").forEach((h) => h.remove());    // o título já é o único <h1> da página
  const toc = [...root.querySelectorAll("h2[id]")]
    .filter((h) => !/faq/i.test(h.id) && !FAQ_RE.test((h.textContent || "").trim()))
    .map((h) => ({ id: h.id, text: (h.textContent || "").trim() }));
  const first = root.querySelector("h2");
  if (!first || first.parentNode !== root) return { head: "", rest: root.innerHTML, toc };
  let head = "";
  while (root.firstChild && root.firstChild !== first) {
    const n = root.firstChild;
    head += n.outerHTML ?? n.textContent ?? "";
    root.removeChild(n);
  }
  return { head, rest: root.innerHTML, toc };
}

export default function HeyCatchBlogPost({ slug, fallback }) {
  const [st, setSt] = useState({ loading: true, a: null, miss: false });
  useEffect(() => {
    let alive = true;
    setSt({ loading: true, a: null, miss: false });
    api.get(`/blog/heycatch/${encodeURIComponent(slug)}`)
      .then(({ data }) => alive && setSt({ loading: false, a: data, miss: false }))
      .catch(() => alive && setSt({ loading: false, a: null, miss: true }));
    return () => { alive = false; };
  }, [slug]);
  const parts = useMemo(() => (st.a ? splitArticle(st.a.content_html) : null), [st.a]);
  const lang = (st.a?.language || "pt").toLowerCase();
  useEffect(() => {
    if (!st.a) return undefined;
    const el = document.documentElement;
    const prev = el.getAttribute("dir");
    el.setAttribute("dir", RTL.test(lang) ? "rtl" : "ltr");
    return () => { if (prev) el.setAttribute("dir", prev); else el.removeAttribute("dir"); };
  }, [st.a, lang]);

  if (st.loading) {
    return <div className="min-h-[50vh] grid place-items-center" data-testid="heycatch-loading">
      <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>;
  }
  if (st.miss || !st.a) return fallback;          // artigo AutoSEO, ou página 404

  const a = st.a;
  const image = a.hero_image_url || a.featured_image || "";
  const date = a.published || a.published_at;
  const ld = a.jsonLd && Object.keys(a.jsonLd).length ? a.jsonLd : null;
  return (
    <>
      <SEO title={a.title} description={a.meta_description || ""} canonical={`/blog/${slug}`} type="article"
        lang={lang} keywords={(a.keywords || []).join(", ") || undefined}
        image={image ? (image.startsWith("/") ? SITE + image : image) : undefined}
        jsonLd={ld || undefined} />
      <article className="mx-auto max-w-3xl px-5 lg:px-8 py-12 lg:py-16" lang={lang} dir={RTL.test(lang) ? "rtl" : "ltr"} data-testid="heycatch-article">
        <nav aria-label="Caminho de navegação" className="mb-6" data-testid="breadcrumb">
          <ol className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <li><Link to="/" className="hover:text-primary">Início</Link></li>
            <li aria-hidden="true" className="opacity-50">/</li>
            <li><Link to="/blog" className="hover:text-primary" data-testid="breadcrumb-blog">Blog</Link></li>
            <li aria-hidden="true" className="opacity-50">/</li>
            <li className="text-foreground font-medium truncate max-w-[60vw] sm:max-w-md" aria-current="page">{a.title}</li>
          </ol>
        </nav>
        <h1 className="font-display text-3xl lg:text-5xl font-extrabold tracking-tighter">{a.title}</h1>
        <div className="mt-5 flex items-center gap-4 text-xs text-muted-foreground">
          {date && <span className="inline-flex items-center gap-1"><Calendar className="h-3 w-3" /><time dateTime={date}>{fmtDate(date)}</time></span>}
          {a.read_time ? <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" /> {a.read_time} min de leitura</span> : null}
        </div>
        {image && <img src={image} alt={a.title} className="mt-8 rounded-sm border border-border w-full aspect-[16/9] object-cover" />}

        {parts.head && <div className="mt-10 prose-blog space-y-4 text-[15px] leading-relaxed" data-testid="heycatch-takeaways" dangerouslySetInnerHTML={{ __html: parts.head }} />}
        {parts.toc.length > 1 && <nav className="mt-8 surface p-5" aria-label="Índice do artigo" data-testid="heycatch-toc">
          <p className="overline">Neste artigo</p>
          <ol className="mt-3 grid gap-2 text-sm list-decimal ps-5">
            {parts.toc.map((t) => <li key={t.id}><a href={`#${t.id}`} className="hover:text-primary">{t.text}</a></li>)}
          </ol>
        </nav>}
        <div className="mt-10 prose-blog space-y-4 text-[15px] leading-relaxed" data-testid="blog-body" dangerouslySetInnerHTML={{ __html: parts.rest }} />

        <div className="mt-12 surface p-6 grid md:grid-cols-[1fr_auto] gap-4 items-center border-primary/40">
          <div>
            <p className="font-display font-bold text-lg">Pronto para orçamentar a sua obra?</p>
            <p className="text-sm text-muted-foreground mt-1">Meça na planta e prepare o seu orçamento com o ConstruPilot.</p>
          </div>
          <Link to="/inscription"><Button className="rounded-sm gap-2" data-testid="heycatch-cta">Experimentar o ConstruPilot <ArrowRight className="h-4 w-4" /></Button></Link>
        </div>
        <div className="mt-10"><NewsletterForm source={`article:${slug}`} /></div>
      </article>
    </>
  );
}
