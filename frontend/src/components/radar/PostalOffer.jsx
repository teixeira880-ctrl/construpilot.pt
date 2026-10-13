import { useCallback, useEffect, useRef, useState } from "react";
import { CreditCard, Gift, Loader2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { usePostalCopy } from "./postalCopy";

export const usePostalOffer = (open, identity) => {
  const [state, setState] = useState({ offer: null, loading: true, error: false });
  const generation = useRef(0);
  const refresh = useCallback(async () => {
    const version = ++generation.current;
    if (!open || !identity) return;
    setState({ offer: null, loading: true, error: false, identity });
    try {
      const { data } = await api.get("/radar/postal/status", { timeout: 15000 });
      if (typeof data.offer?.eligible !== "boolean" || !["demo", "credit", "checkout"].includes(data.offer.next_kind)) throw new Error("Invalid offer");
      if (generation.current === version) setState({ offer: data.offer, loading: false, error: false, identity });
    } catch {
      if (generation.current === version) setState({ offer: null, loading: false, error: true, identity });
    }
  }, [open, identity]);
  useEffect(() => { refresh(); return () => { generation.current += 1; }; }, [refresh]);
  return { ...(state.identity === identity ? state : { offer: null, loading: true, error: false }), refresh };
};

export const euros = (cents) => `${(cents / 100).toFixed(2).replace(".", ",")} €`;

export const PostalPacks = ({ packs = [], disabled }) => {
  const ui = usePostalCopy();
  const [buying, setBuying] = useState(null);
  const buy = async (pack) => {
    setBuying(pack.pack_id);
    try {
      const { data } = await api.post("/radar/postal/credits/checkout", { pack_id: pack.pack_id, origin_url: window.location.origin }, { timeout: 30000 });
      window.location.assign(data.url);
    } catch (e) {
      toast.error(e?.response?.data?.detail?.message || e?.response?.data?.detail || "Paiement indisponible");
      setBuying(null);
    }
  };
  return <div className="flex flex-wrap gap-2" data-testid="postal-packs">
    {packs.map((p) => <Button key={p.pack_id} size="sm" variant="outline" className="h-8 gap-1 text-xs" disabled={disabled || Boolean(buying)} onClick={() => buy(p)} data-testid={`postal-pack-${p.pack_id}`}>
      {buying === p.pack_id ? <Loader2 size={13} className="animate-spin" /> : <CreditCard size={13} />}
      {ui("buyPack")} {p.letters} · {euros(p.amount_net_cents)} HT
    </Button>)}
  </div>;
};

export const PostalOffer = ({ offer, loading, error, refresh }) => {
  const ui = usePostalCopy();
  const demo = offer?.phase === "demo";
  return <section className="space-y-2 border-y py-3 text-xs" data-testid="postal-offer">
    <p className="flex gap-2 items-center font-semibold" data-testid="postal-offer-title"><Gift size={17} className="shrink-0 text-primary" />{ui(demo || !offer ? "trialOffer" : "paidPhase")}</p>
    {loading ? <p role="status" className="flex gap-2" data-testid="postal-offer-loading"><Loader2 size={14} className="animate-spin" />{ui("checking")}</p>
      : error ? <div role="alert" data-testid="postal-offer-error">{ui("offerError")}<Button variant="outline" size="sm" onClick={refresh} data-testid="postal-offer-retry">{ui("retry")}</Button></div>
      : <>
        <p role="status" data-testid="postal-offer-remaining">{ui(demo ? "available" : offer?.status === "used" ? "used" : offer?.next_kind === "credit" ? "available" : "pending")}
          {demo && <b className="ml-1" data-testid="postal-offer-remaining-count">{offer.demo_remaining} / {offer.demo_limit}</b>}</p>
        <p data-testid="postal-offer-credits">{ui("credits")} <b data-testid="postal-offer-credits-count">{offer?.credits ?? 0}</b></p>
        <PostalPacks packs={offer?.packs} />
      </>}
    <p className="text-muted-foreground" data-testid="postal-future-price">{ui("future")}</p>
  </section>;
};
