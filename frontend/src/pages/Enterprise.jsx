// Page Enterprise : même formulaire commercial que la page tarifs (aucun prix, contact uniquement).
import { useI18n } from "@/context/I18nContext";
import { SEO } from "@/components/SEO";
import EnterpriseLeadForm from "@/components/pricing/EnterpriseLeadForm";
import { copyFor } from "@/lib/commercialCopy";
import { currentMarket } from "@/lib/market";

export default function Enterprise() {
  const { lang } = useI18n();
  const l = lang === "fr" || lang === "pt" ? lang : currentMarket();
  const c = copyFor(l);
  return (
    <div className="grid gap-10">
      <SEO title={`ConstruPilot Enterprise — ${c.taglines.enterprise}`} description={c.ent.intro} canonical="/enterprise" />
      <EnterpriseLeadForm lang={l} />
    </div>
  );
}
