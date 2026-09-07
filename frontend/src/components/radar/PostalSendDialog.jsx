import { useEffect, useState } from "react";
import { Loader2, Send, Mail, Truck, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";

const MODES = [
  { v: "normal", label: "Lettre simple" },
  { v: "suivi", label: "Lettre suivie" },
  { v: "lrar", label: "Recommandé (LRAR)" },
];

export default function PostalSendDialog({ open, onClose, campaign, opp }) {
  const [form, setForm] = useState({ nom: "Le maître d'ouvrage", societe: "", adresse1: "", adresse2: "", cp: "", ville: "" });
  const [mode, setMode] = useState("normal");
  const [price, setPrice] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sends, setSends] = useState([]);

  useEffect(() => {
    if (!open) return;
    setForm((f) => ({ ...f, adresse1: opp?.adresse || "", cp: opp?.cp || "", ville: opp?.commune || "" }));
    api.get(`/radar/prospection/${campaign.token}/postal`).then(({ data }) => setSends(data.sends || [])).catch(() => {});
  }, [open, campaign?.token, opp]);

  useEffect(() => {
    if (!open) return;
    setPrice(null);
    api.get(`/radar/postal/price?mode=${mode}`).then(({ data }) => setPrice(data)).catch(() => setPrice(false));
  }, [open, mode]);

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const send = async () => {
    if (!form.nom.trim() || !form.adresse1.trim() || !form.cp.trim() || !form.ville.trim()) {
      toast.error("Nom, adresse, code postal et ville sont requis"); return;
    }
    setBusy(true);
    try {
      const { data } = await api.post(`/radar/prospection/${campaign.token}/postal`, { recipient: form, mode });
      setSends((s) => [data, ...s]);
      toast.success(`Courrier posté (n° ${data.envoi_id || "—"})`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envoi postal impossible");
    } finally { setBusy(false); }
  };

  const refresh = async () => {
    try {
      const { data } = await api.get(`/radar/prospection/${campaign.token}/postal?refresh=true`);
      setSends(data.sends || []);
    } catch { toast.error("Suivi indisponible"); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="postal-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Truck className="h-5 w-5 text-primary" /> Envoyer par la poste</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground -mt-2">Le courrier PDF (avec QR) est imprimé et posté par Merci Facteur. L'envoi est facturé sur votre compte Merci Facteur.</p>
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
        <div className="flex items-center justify-between text-xs" data-testid="postal-price">
          <span className="text-muted-foreground">Tarif indicatif (1 page, France)</span>
          <span className="num font-bold">
            {price === null ? "…" : price === false ? "n.d." : `${price.total_ttc.toFixed(2)} € TTC`}
          </span>
        </div>
        <Button onClick={send} disabled={busy} className="rounded-sm gap-2 w-full" data-testid="postal-send-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Poster le courrier
        </Button>
        {sends.length > 0 && (
          <div className="border-t border-border pt-3" data-testid="postal-history">
            <div className="flex items-center justify-between mb-1">
              <p className="text-xs font-bold flex items-center gap-1"><Mail className="h-3.5 w-3.5" /> Envois postaux ({sends.length})</p>
              <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={refresh} data-testid="postal-refresh">
                <RefreshCw className="h-3 w-3" /> Suivi
              </Button>
            </div>
            <ul className="text-xs space-y-1 max-h-32 overflow-y-auto">
              {sends.map((s) => (
                <li key={s.postal_id} className="flex justify-between gap-2 border-b border-border/40 py-1">
                  <span className="truncate">{s.recipient?.nom} · {s.recipient?.ville} · {MODES.find((m) => m.v === s.mode)?.label}</span>
                  <span className="text-muted-foreground shrink-0">{s.status || "submitted"}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
