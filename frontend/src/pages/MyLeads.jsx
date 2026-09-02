import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import {
  Inbox, Mail, Phone, MapPin, Check, X, FileText, Loader2, Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, eur } from "@/lib/api";
import { SEO } from "@/components/SEO";

const HANDLING = {
  acceptee: { label: "Prise en charge", cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30" },
  refusee: { label: "Refusée", cls: "bg-red-500/15 text-red-600 border-red-500/30" },
  en_cours: { label: "En cours", cls: "bg-amber-500/15 text-amber-600 border-amber-500/30" },
};

export default function MyLeads() {
  const navigate = useNavigate();
  const [leads, setLeads] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  const load = useCallback(async () => {
    try { const { data } = await api.get("/leads/assigned"); setLeads(data || []); }
    catch { /* */ } finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const setHandling = async (lead, status) => {
    setBusy(lead.lead_id + status);
    try {
      await api.put(`/leads/${lead.lead_id}/handling`, { handling_status: status });
      toast.success(status === "acceptee" ? "Demande prise en charge" : status === "refusee" ? "Demande refusée" : "Mise à jour");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Action impossible"); }
    finally { setBusy(""); }
  };

  const createQuote = async (l) => {
    try {
      const parts = (l.name || "").trim().split(" ").filter(Boolean);
      const first = parts.length > 1 ? parts.slice(0, -1).join(" ") : (parts[0] || "");
      const last = parts.length > 1 ? parts[parts.length - 1] : "";
      const { data } = await api.post("/clients", {
        first_name: first, last_name: last || first || "Client",
        email: l.email || "", phone: l.phone || "", address: l.address || "",
        notes: l.description || "",
      });
      navigate(`/devis-editeur?client=${data.client_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Création impossible"); }
  };

  return (
    <div className="max-w-4xl mx-auto px-4 py-8" data-testid="my-leads-page">
      <SEO title="Mes demandes — ConstruPilot" description="Les demandes de travaux qui vous sont assignées." />
      <div className="flex items-center gap-3 mb-6">
        <span className="h-10 w-10 grid place-items-center rounded-xl bg-primary/10"><Inbox className="h-5 w-5 text-primary" /></span>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Mes demandes</h1>
          <p className="text-sm text-muted-foreground">Les demandes de travaux qui vous sont assignées — prenez-les en charge.</p>
        </div>
        {leads.length > 0 && <Badge variant="secondary" className="ml-auto" data-testid="my-leads-count">{leads.length}</Badge>}
      </div>

      {loading ? (
        <div className="py-20 text-center text-muted-foreground"><Loader2 className="h-6 w-6 mx-auto animate-spin" /></div>
      ) : leads.length === 0 ? (
        <div className="rounded-xl border border-border bg-card p-12 text-center" data-testid="my-leads-empty">
          <Inbox className="h-8 w-8 mx-auto mb-3 text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Aucune demande assignée pour le moment.</p>
        </div>
      ) : (
        <div className="grid gap-4" data-testid="my-leads-list">
          {leads.map((l) => {
            const h = HANDLING[l.handling_status];
            return (
              <div key={l.lead_id} className="rounded-xl border border-border bg-card p-5 space-y-3" data-testid={`my-lead-${l.lead_id}`}>
                <div className="flex flex-wrap items-center gap-3">
                  <p className="font-semibold">{l.name || l.email || "Client"}</p>
                  {l.budget ? <span className="num text-primary font-bold">{eur(l.budget)}</span> : null}
                  {h ? <span className={`px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase border ${h.cls}`}>{h.label}</span>
                     : <span className="px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase border bg-secondary text-muted-foreground border-border flex items-center gap-1"><Clock className="h-3 w-3" /> À traiter</span>}
                  {l.auto_assigned && <Badge variant="outline" className="text-[10px]">Auto</Badge>}
                </div>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                  {l.email && <span className="flex items-center gap-1"><Mail className="h-3.5 w-3.5" /> {l.email}</span>}
                  {l.phone && <span className="flex items-center gap-1"><Phone className="h-3.5 w-3.5" /> {l.phone}</span>}
                  {l.address && <span className="flex items-center gap-1"><MapPin className="h-3.5 w-3.5" /> {l.address}</span>}
                </div>
                {l.description && <p className="text-sm">{l.description}</p>}
                <div className="flex flex-wrap items-center gap-2 pt-2 border-t border-border">
                  {l.handling_status !== "acceptee" && (
                    <Button size="sm" className="rounded-sm gap-1.5 h-8" disabled={busy.startsWith(l.lead_id)} onClick={() => setHandling(l, "acceptee")} data-testid={`my-lead-accept-${l.lead_id}`}>
                      <Check className="h-3.5 w-3.5" /> Prendre en charge
                    </Button>
                  )}
                  {l.handling_status !== "refusee" && (
                    <Button size="sm" variant="outline" className="rounded-sm gap-1.5 h-8" disabled={busy.startsWith(l.lead_id)} onClick={() => setHandling(l, "refusee")} data-testid={`my-lead-refuse-${l.lead_id}`}>
                      <X className="h-3.5 w-3.5" /> Refuser
                    </Button>
                  )}
                  <Button size="sm" variant="secondary" className="rounded-sm gap-1.5 h-8" onClick={() => createQuote(l)} data-testid={`my-lead-quote-${l.lead_id}`}>
                    <FileText className="h-3.5 w-3.5" /> Créer un devis
                  </Button>
                  {l.email && <a href={`mailto:${l.email}`} className="inline-flex items-center gap-1.5 h-8 px-3 rounded-sm border border-border text-xs font-semibold hover:border-primary/40"><Mail className="h-3.5 w-3.5" /> Contacter</a>}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
