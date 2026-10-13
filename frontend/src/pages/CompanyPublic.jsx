import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import axios from "axios";
import { Phone, Mail, Globe, MapPin, ShieldCheck, Star } from "lucide-react";
import { QuoteRequestForm } from "@/components/company/QuoteRequestForm";

const BASE = process.env.REACT_APP_BACKEND_URL;

export default function CompanyPublic() {
  const { slug } = useParams();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);

  useEffect(() => {
    axios.get(`${BASE}/api/public/company/${slug}`).then(({ data }) => { setData(data); document.title = `${data.company_name} — ConstruPilot`; })
      .catch((e) => setError(e?.response?.status === 404 ? "Esta página não existe ou não está publicada." : "Página indisponível de momento."));
  }, [slug]);

  if (error) return <div className="min-h-screen grid place-items-center p-8 text-center text-slate-600" data-testid="company-public-error">{error}</div>;
  if (!data) return <div className="min-h-screen grid place-items-center text-slate-500">A carregar…</div>;
  const accent = data.accent_color || "#0F766E";
  const reviews = data.reviews?.items || data.reviews?.reviews || [];

  return (
    <div className="min-h-screen bg-white text-slate-900" data-testid="company-public-page" style={{ "--accent": accent }}>
      <header className="border-b" style={{ borderColor: accent }}>
        <div className="max-w-5xl mx-auto px-5 py-8 flex flex-col md:flex-row md:items-center gap-6">
          {data.has_logo && <img src={`${BASE}/api/branding/${data.user_id}/logo`} alt={`Logótipo ${data.company_name}`} className="h-20 w-20 object-contain rounded-lg border bg-white" />}
          <div className="flex-1">
            <h1 className="text-3xl md:text-4xl font-semibold" data-testid="company-public-name">{data.company_name}</h1>
            {data.tagline && <p className="text-lg text-slate-600 mt-1" data-testid="company-public-tagline">{data.tagline}</p>}
            <div className="flex flex-wrap gap-2 mt-3">
              {(data.certifications || []).map((c, i) => <span key={i} className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded-full border" style={{ borderColor: accent, color: accent }}><ShieldCheck className="h-3 w-3" /> {typeof c === "string" ? c : c.label || c.name}</span>)}
            </div>
          </div>
          <div className="flex flex-col gap-2">
            {data.phone && <a href={`tel:${data.phone}`} className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-white font-medium" style={{ background: accent }} data-testid="company-public-call"><Phone className="h-4 w-4" /> {data.phone}</a>}
            <a href="#demande-devis" className="inline-flex items-center justify-center gap-2 px-4 py-2 rounded-lg border font-medium" style={{ borderColor: accent, color: accent }} data-testid="company-public-quote"><Mail className="h-4 w-4" /> Pedir um orçamento</a>
          </div>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-5 py-10 space-y-12">
        {data.description && <section><h2 className="text-lg font-semibold mb-3">L'entreprise</h2><p className="whitespace-pre-wrap text-slate-700 leading-relaxed" data-testid="company-public-description">{data.description}</p></section>}
        <section className="grid md:grid-cols-3 gap-4 text-sm">
          {data.address && <div className="flex items-start gap-2"><MapPin className="h-4 w-4 mt-0.5" style={{ color: accent }} /><span>{data.address}</span></div>}
          {data.website && <a href={data.website} target="_blank" rel="noreferrer" className="flex items-start gap-2 underline"><Globe className="h-4 w-4 mt-0.5" style={{ color: accent }} />{data.website}</a>}
          {(data.service_zones || []).length > 0 && <div><span className="font-medium">Zones d'intervention : </span>{data.service_zones.map((z) => (typeof z === "string" ? z : z.label || z.name)).join(", ")}</div>}
        </section>

        {data.photos.length > 0 && (
          <section data-testid="company-public-gallery">
            <h2 className="text-lg font-semibold mb-4">Obras realizadas</h2>
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {data.photos.map((p) => (
                <figure key={p.photo_id} className="rounded-xl overflow-hidden border cursor-pointer group" onClick={() => setOpen(p)} data-testid={`company-public-photo-${p.photo_id}`}>
                  <img src={`${BASE}/api/public/company/${slug}/photo/${p.photo_id}`} alt={p.title || "Obra realizada"} loading="lazy" className="w-full h-52 object-cover group-hover:scale-[1.02] transition-transform duration-200" />
                  {(p.title || p.description) && <figcaption className="p-3"><div className="font-medium">{p.title}</div>{p.description && <p className="text-sm text-slate-600 line-clamp-2">{p.description}</p>}</figcaption>}
                </figure>
              ))}
            </div>
          </section>
        )}

        <section id="demande-devis" data-testid="company-public-quote-section">
          <QuoteRequestForm slug={slug} companyName={data.company_name} accent={accent} />
        </section>

        {data.show_reviews && reviews.length > 0 && (
          <section data-testid="company-public-reviews">
            <h2 className="text-lg font-semibold mb-4">Opiniões de clientes</h2>
            <div className="grid md:grid-cols-2 gap-4">
              {reviews.map((r, i) => (
                <blockquote key={i} className="rounded-xl border p-4 text-sm">
                  <div className="flex gap-0.5 mb-2">{Array.from({ length: Math.round(r.rating || r.stars || 5) }).map((_, j) => <Star key={j} className="h-4 w-4 fill-current" style={{ color: accent }} />)}</div>
                  <p className="text-slate-700">{r.comment || r.text}</p>
                  <footer className="text-xs text-slate-500 mt-2">{r.author || r.client_name || "Cliente"}</footer>
                </blockquote>
              ))}
            </div>
          </section>
        )}
      </main>

      <footer className="border-t py-6 text-center text-xs text-slate-500">
        {data.footer_text && <p className="whitespace-pre-wrap max-w-3xl mx-auto px-4 mb-2">{data.footer_text}</p>}
        Página de empresa com tecnologia <a href="/" className="underline">ConstruPilot</a>
      </footer>

      {open && (
        <div className="fixed inset-0 bg-black/80 grid place-items-center p-4 z-50" onClick={() => setOpen(null)} data-testid="company-public-lightbox">
          <figure className="max-w-4xl w-full">
            <img src={`${BASE}/api/public/company/${slug}/photo/${open.photo_id}`} alt={open.title || ""} className="w-full max-h-[80vh] object-contain rounded-lg" />
            <figcaption className="text-white text-center mt-3"><div className="font-medium">{open.title}</div><p className="text-sm text-slate-300">{open.description}</p></figcaption>
          </figure>
        </div>
      )}
    </div>
  );
}
