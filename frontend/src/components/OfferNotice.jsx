import { useEffect, useState } from "react";
import { Sparkles } from "lucide-react";
import { api } from "@/lib/api";

let cache = null;

/** Offre réellement appliquée (source : GET /api/offer). Aucune valeur commerciale en dur. */
export const useOffer = () => {
  const [offer, setOffer] = useState(cache);
  useEffect(() => {
    if (cache) return;
    api.get("/offer").then(({ data }) => { cache = data; setOffer(data); }).catch(() => {});
  }, []);
  return offer;
};

export const offerSentence = (offer, lang = "fr") => {
  if (!offer) return "";
  const pro = offer.entry_price_eur?.pro;
  const part = offer.entry_price_eur?.particulier;
  if (lang === "pt") {
    const after = [part && `${part}€/mês para particulares`, pro && `${pro}€/mês para profissionais`]
      .filter(Boolean).join(" · ");
    return offer.free_promo
      ? `Durante a fase de lançamento, todas as funções estão acessíveis sem cartão. Os planos publicados (${after}) só se aplicam no fim desta fase, e será avisado antes de qualquer pagamento.`
      : `Existe um plano gratuito. Planos pagos: ${after}${offer.trial_days ? `, com ${offer.trial_days}dias de experiência` : ""}.`;
  }
  const after = [part && `${part}€/mês para particulares`, pro && `${pro}€/mês para profissionais`]
    .filter(Boolean).join(" · ");
  return offer.free_promo
    ? `Durante a fase de lançamento, todas as funções estão acessíveis sem cartão bancário. Os preços publicados (${after}) serão aplicados no fim desta fase, e será avisado antes de qualquer pagamento.`
    : `Existe uma oferta gratuita. Subscrições:${after}${offer.trial_days ? `, com${offer.trial_days} jours d'essai` : ""}.`;
};

/** Bandeau à afficher partout où l'offre est évoquée — jamais de texte de prix en dur. */
export const OfferNotice = ({ lang = "fr", className = "" }) => {
  const offer = useOffer();
  if (!offer) return null;
  return (
    <div
      className={`surface rounded-md border-primary/40 p-4 flex items-start gap-3 ${className}`}
      data-testid="offer-notice"
    >
      <Sparkles className="h-4 w-4 text-primary shrink-0 mt-0.5" />
      <div className="min-w-0">
        <p className="text-sm font-semibold" data-testid="offer-notice-title">
          {offer.free_promo
            ? (lang === "pt" ? "Fase de lançamento — acesso completo grátis" : "Fase de lançamento — acesso completo grátis")
            : (lang === "pt" ? "Planos e preços" : "Oferta e preços")}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5" data-testid="offer-notice-text">
          {offerSentence(offer, lang)}
        </p>
      </div>
    </div>
  );
};
