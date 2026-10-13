import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { usePostalCopy } from "./postalCopy";

export const postalKind = (price) => {
  const kind = price?.offer?.next_kind;
  if (!["demo", "credit", "checkout"].includes(kind)) return null;
  if (kind !== "checkout" && price.offer.customer_amount_cents !== 0) return null;
  return kind;
};

export const PostalPriceConsent = ({ price, error, loading, refresh, checked, onCheck, busy }) => {
  const ui = usePostalCopy();
  const kind = postalKind(price);
  const amount = { demo: "free", credit: "creditAmount", checkout: "paidAmount" }[kind];
  return <div className="space-y-3">
    <div className="flex items-center justify-between gap-2 text-xs" data-testid="postal-price">
      <span className="text-muted-foreground">{ui("amount")}</span>
      <span className="num font-bold" data-testid="postal-price-total">{kind ? ui(amount) : loading ? ui("calculating") : ui("unavailable")}</span>
    </div>
    {kind && <p className="text-xs text-muted-foreground" data-testid="postal-no-charge">{ui({ demo: "noCharge", credit: "creditCharge", checkout: "paidCharge" }[kind])}</p>}
    {error && <p role="alert" className="text-xs text-red-700" data-testid="postal-quote-error">{error}</p>}
    <Button variant="outline" size="sm" onClick={refresh} disabled={busy || loading} className="gap-1" data-testid="postal-price-retry"><RefreshCw className="h-3.5 w-3.5" />{ui("refresh")}</Button>
    <label className="flex items-start gap-2 text-xs" data-testid="postal-price-consent-label">
      <input type="checkbox" checked={checked && Boolean(kind)} onChange={(e) => onCheck(e.target.checked)} disabled={busy || !kind} className="shrink-0 mt-0.5" data-testid="postal-price-consent" />
      {ui(kind ? { demo: "consent", credit: "creditConsent", checkout: "paidConsent" }[kind] : "validRequired")}
    </label>
  </div>;
};
