import { useEffect, useRef, useState } from "react";
import { Loader2, Send, Mail, Truck, RefreshCw, CreditCard } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { completePostalAddress, defaultPostalDestination, postalRecipient } from "./postalRecipient";
import { PostalDestination } from "./PostalDestination";
import { PostalPriceConsent, postalKind } from "./PostalPriceConsent";
import { PostalSendRow } from "./PostalTracking";
import { postalError, usePostalQuote } from "./usePostalQuote";
import { toast } from "sonner";
import { Link } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { PostalOffer, usePostalOffer } from "./PostalOffer";
import { usePostalCopy } from "./postalCopy";
import { BrandingDialog } from "@/components/BrandingDialog";

const MODES = [
  { v: "normal", label: "Lettre simple" },
  { v: "suivi", label: "Lettre suivie" },
  { v: "lrar", label: "Recommandé (LRAR)" },
];

export default function PostalSendDialog({ open, onClose, campaign, opp }) {
  const { user } = useAuth();
  const ui = usePostalCopy();
  const offerState = usePostalOffer(open, user ? `${user.user_id}:${user.organization_id || "solo"}:${campaign?.token || ""}` : null);
  const [form, setForm] = useState(() => postalRecipient(opp));
  const [destination, setDestination] = useState(() => defaultPostalDestination(opp));
  const [edited, setEdited] = useState(false);
  const [mode, setMode] = useState("normal");
  const [approvedQuote, setApprovedQuote] = useState(null);
  const [sendError, setSendError] = useState("");
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [locked, setLocked] = useState(false);
  const submitting = useRef(false);
  const [busy, setBusy] = useState(false);
  const [sends, setSends] = useState([]);
  const valid = completePostalAddress(form) && Boolean(form.nom.trim()) && !opp?.is_demo && Boolean(offerState.offer);
  const { price, error, errorCode, loading, refresh: refreshPrice } = usePostalQuote({ open, token: campaign?.token, form, mode,
    addressSource: edited ? "manual" : destination, valid });
  const kind = postalKind(price);
  const consent = Boolean(kind && approvedQuote === price.quote_id);

  useEffect(() => {
    if (!open || !campaign?.token) return;
    let active = true;
    setForm(postalRecipient(opp));
    setDestination(defaultPostalDestination(opp)); setEdited(false);
    setApprovedQuote(null); setSendError(""); setHistoryError(""); setHistoryLoaded(false); setLocked(false);
    setSends([]);
    api.get(`/radar/prospection/${campaign.token}/postal`).then(({ data }) => {
      if (active) { setSends(data.sends || []); setHistoryLoaded(true); }
    }).catch(() => { if (active) setHistoryError("Impossible de vérifier l'historique. Actualisez le suivi avant l'envoi."); });
    return () => { active = false; };
  }, [open, campaign?.token, opp]);

  const set = (k) => (e) => { setForm((f) => ({ ...f, [k]: e.target.value })); setEdited(true); };
  const changeDestination = (value) => { setDestination(value); setEdited(false); setForm(postalRecipient(opp, value)); };

  const send = async () => {
    if (submitting.current || busy || locked || !valid || !consent || !historyLoaded || !price) return;
    if (!form.nom.trim() || !form.adresse1.trim() || !form.cp.trim() || !form.ville.trim()) {
      toast.error("Nom, adresse, code postal et ville sont requis"); return;
    }
    submitting.current = true; setBusy(true); setSendError("");
    const payload = { recipient: form, mode, address_source: edited ? "manual" : destination, quote_id: price.quote_id, confirmed: true };
    if (kind === "checkout") {
      try {
        const { data } = await api.post(`/radar/prospection/${campaign.token}/postal/checkout`, { ...payload, origin_url: window.location.origin }, { timeout: 30000 });
        toast.message(ui("redirecting"));
        window.location.assign(data.url);
        return;
      } catch (e) { setSendError(postalError(e)); setApprovedQuote(null); submitting.current = false; setBusy(false); return; }
    }
    try {
      const { data } = await api.post(`/radar/prospection/${campaign.token}/postal`, payload, { timeout: 55000 });
      setSends((s) => [data, ...s]);
      setApprovedQuote(null);
      if (data.status === "submitted") { setLocked(true); toast.success(`Courrier accepté par Merci Facteur (n° ${data.envoi_id})`); }
      else { setLocked(true); setSendError(data.error_message || "Envoi à vérifier avant toute nouvelle tentative."); }
    } catch (e) {
      setSendError(postalError(e)); setApprovedQuote(null);
      // A gateway failure does not establish whether postage was accepted; never auto-resend.
      if (!e.response || e.response.status >= 500 || e.response.status === 409) setLocked(true);
    } finally { submitting.current = false; setBusy(false); offerState.refresh(); }
  };

  const refresh = async () => {
    try {
      const { data } = await api.get(`/radar/prospection/${campaign.token}/postal?refresh=true`);
      setSends(data.sends || []);
      setHistoryLoaded(true); setHistoryError(data.refresh_error || "");
      const needsCheck = (data.sends || []).some(s => ["submitting", "unknown", "submitted"].includes(s.status));
      setLocked(needsCheck);
      if (!needsCheck) { setApprovedQuote(null); setSendError(""); refreshPrice(); }
      offerState.refresh();
    } catch { toast.error("Suivi indisponible"); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && !busy && onClose()}>
      <DialogContent className="z-[121] w-[calc(100%-2rem)] max-w-lg max-h-[calc(100dvh-2rem)] overflow-y-auto" overlayClassName="z-[120]" data-testid="postal-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 pr-4" data-testid="postal-dialog-title"><Truck className="h-5 w-5 shrink-0 text-primary" /> Envoyer par la poste</DialogTitle>
        </DialogHeader>
        <DialogDescription className="text-xs -mt-2" data-testid="postal-billing-notice">{ui(offerState.offer?.phase === "paid" ? "packHint" : "costCovered")}</DialogDescription>
        <p className="text-xs border-l-2 border-primary pl-3" data-testid="postal-real-delivery-notice">{ui(offerState.offer?.next_kind === "checkout" ? "paidNotice" : "liveNotice")}</p>
        <PostalOffer {...offerState} />
        <fieldset disabled={busy} className="space-y-3 min-w-0">
        <PostalDestination destination={destination} edited={edited} onChange={changeDestination} complete={completePostalAddress(form)} />
        <div className="grid grid-cols-2 gap-2 text-xs">
          <label className="col-span-2">Destinataire *
            <Input value={form.nom} onChange={set("nom")} className="h-9 mt-1" data-testid="postal-nom" /></label>
          <label className="col-span-2">Société (optionnel)
            <Input value={form.societe} onChange={set("societe")} className="h-9 mt-1" data-testid="postal-societe" /></label>
          <label className="col-span-2">Adresse *
            <Input value={form.adresse1} onChange={set("adresse1")} placeholder="N° et voie" className="h-9 mt-1" data-testid="postal-adresse1" /></label>
          <label className="col-span-2">Complément
            <Input value={form.adresse2} onChange={set("adresse2")} className="h-9 mt-1" data-testid="postal-adresse2" /></label>
          <label>Code postal *
            <Input value={form.cp} onChange={set("cp")} className="h-9 mt-1 num" data-testid="postal-cp" /></label>
          <label>Ville *
            <Input value={form.ville} onChange={set("ville")} className="h-9 mt-1" data-testid="postal-ville" /></label>
          <label className="col-span-2">Mode d'envoi
            <select value={mode} onChange={(e) => setMode(e.target.value)} data-testid="postal-mode"
              className="h-9 mt-1 w-full rounded-md border border-border bg-background px-2 text-sm">
              {MODES.map((m) => <option key={m.v} value={m.v}>{m.label}</option>)}
            </select></label>
        </div>
        </fieldset>
        <PostalPriceConsent price={price} error={error} loading={loading} refresh={() => { setApprovedQuote(null); refreshPrice(); }}
          checked={consent} onCheck={(checked) => setApprovedQuote(checked ? price?.quote_id : null)} busy={busy || locked} />
        {errorCode === "sender_address_required" && <BrandingDialog
          contentClassName="z-[131] w-[calc(100%-2rem)]" overlayClassName="z-[130]"
          onSaved={() => { setApprovedQuote(null); refreshPrice(); }}
          trigger={<Button variant="outline" data-testid="postal-complete-sender">{ui("completeSender")}</Button>} />}
        {user?.role === "admin" && errorCode === "INVALID_TOKEN_FOR_IP" && <Link to="/admin?tab=postal" onClick={onClose} className="text-xs underline text-primary" data-testid="postal-admin-diagnostics-link">{ui("diagnosis")}</Link>}
        {sendError && <p role="alert" className="text-xs text-red-700" data-testid="postal-send-error">{sendError}</p>}
        {historyError && <p role="alert" className="text-xs text-red-700" data-testid="postal-history-error">{historyError}</p>}
        {(historyError || locked) && <Button size="sm" variant="outline" disabled={busy} onClick={refresh} data-testid="postal-history-retry">Vérifier le suivi</Button>}
        <Button onClick={send} disabled={busy || locked || !valid || !consent || !historyLoaded} className="rounded-sm gap-2 w-full" data-testid="postal-send-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : kind === "checkout" ? <CreditCard className="h-4 w-4" /> : <Send className="h-4 w-4" />} {ui({ credit: "sendCredit", checkout: "sendPaid" }[kind] || "send")}
        </Button>
        {sends.length > 0 && (
          <div className="border-t border-border pt-3" data-testid="postal-history">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-bold flex items-center gap-1"><Mail className="h-3.5 w-3.5" /> Envois postaux ({sends.length})</p>
              <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={refresh} data-testid="postal-refresh">
                <RefreshCw className="h-3 w-3" /> Suivi
              </Button>
            </div>
            <ul className="text-xs max-h-48 overflow-y-auto">
              {sends.map((s) => <PostalSendRow key={s.postal_id} send={s} />)}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
