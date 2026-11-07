// Auditoria de site (D3.1 / D3.2) : prova social real, entre as ofertas e as perguntas frequentes.
// Só mostra números lidos na base de dados (/api/reviews/site/usage) e opiniões validadas pelo admin
// (/api/reviews/site) — nada inventado. Sem opiniões validadas, convida os utilizadores beta a deixar a sua.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { MessageSquarePlus, Users, FolderKanban } from "lucide-react";
import { api } from "@/lib/api";
import { useOffer } from "@/components/OfferNotice";
import { ReviewDialog } from "@/components/TrustSection";
import { LandingHeading } from "@/components/landing/LandingLayout";

const MIN_USERS = 10;     // abaixo disto, o contador não é mostrado (não reforça a confiança)

const initials = (name = "") => name.trim().split(/\s+/).slice(0, 2).map((w) => w[0]?.toUpperCase() || "").join("");

export function LandingProof() {
  const [usage, setUsage] = useState(null);
  const [reviews, setReviews] = useState([]);
  const [open, setOpen] = useState(false);
  const loadReviews = () => api.get("/reviews/site", { params: { limit: 6 } }).then(({ data }) => setReviews(data.reviews || [])).catch(() => {});
  useEffect(() => {
    api.get("/reviews/site/usage").then(({ data }) => setUsage(data)).catch(() => {});
    loadReviews();
  }, []);
  const showCounter = usage && usage.beta_users >= MIN_USERS;
  return <section className="landing-section landing-proof" id="landing-proof" data-testid="pro-proof">
    <ReviewDialog open={open} onOpenChange={(v) => { setOpen(v); if (!v) loadReviews(); }} />
    <LandingHeading eyebrow="Programa beta em Portugal" title="Quem já está a orçamentar com o ConstruPilot." />
    {showCounter && <div className="landing-proof-counters" data-testid="pro-proof-counter">
      <div><Users size={22} /><strong>{usage.beta_users}</strong><span>profissionais e particulares a testar o ConstruPilot em Portugal</span></div>
      {usage.projects > 0 && <div><FolderKanban size={22} /><strong>{usage.projects}</strong><span>projetos de obra criados durante a beta</span></div>}
    </div>}
    {reviews.length > 0 ? <div className="landing-proof-grid" data-testid="pro-proof-testimonials">
      {reviews.map((r) => <figure key={r.review_id} className="landing-proof-card" data-testid={`pro-proof-${r.review_id}`}>
        <blockquote>«&nbsp;{r.comment}&nbsp;»</blockquote>
        <figcaption>{r.photo_url ? <img src={r.photo_url} alt={`Fotografia de ${r.name}`} width="44" height="44" /> : <span className="landing-proof-avatar" aria-hidden="true">{initials(r.name)}</span>}
          <span><strong>{r.name}</strong>{r.role && <small>{r.role}</small>}</span></figcaption>
      </figure>)}
    </div> : <div className="landing-proof-empty" data-testid="pro-proof-empty">
      <p>Está a testar o ConstruPilot na sua obra? Conte-nos o que mudou: as primeiras opiniões, com nome e profissão, aparecem aqui depois de validadas.</p>
    </div>}
    <div className="landing-proof-actions">
      <button type="button" className="landing-button landing-button-outline" onClick={() => setOpen(true)} data-testid="pro-proof-leave-review"><MessageSquarePlus size={16} />Deixar a minha opinião</button>
      <Link to="/sobre" className="landing-text-link" data-testid="pro-proof-about">Quem somos</Link>
    </div>
  </section>;
}

/** Auditoria D2.4 / brief : a versão gratuita fica visível por baixo do título das ofertas (só fora da fase de lançamento). */
export function PricingFreeLine() {
  const offer = useOffer();
  if (!offer || offer.free_promo) return null;
  return <p className="landing-pricing-free" data-testid="pro-pricing-free">Versão gratuita disponível para começar.</p>;
}
