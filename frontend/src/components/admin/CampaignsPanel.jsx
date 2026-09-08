import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Mail, Users, CheckCircle2, XCircle, RefreshCw, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function CampaignsPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  const load = () => {
    setLoading(true);
    api.get("/admin/campaigns")
      .then(({ data }) => setRows(data.campaigns || []))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const preview = async (audience, step) => {
    setBusy(`p-${audience}-${step}`);
    try {
      const { data } = await api.post(`/admin/campaigns/upsell/preview?audience=${audience}&step=${step}`);
      toast.success(`Aperçu envoyé à ${data.to}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Envoi de l'aperçu impossible"); }
    finally { setBusy(""); }
  };
  const runNow = async (step) => {
    if (!window.confirm(step === "j10" ? "Envoyer la relance J+10 (code promo) à tous les comptes gratuits éligibles maintenant ?" : "Envoyer l'email d'incitation J+3 à tous les comptes gratuits éligibles maintenant ?")) return;
    setBusy(`r-${step}`);
    try {
      const { data } = await api.post(`/admin/campaigns/upsell/run?step=${step}`);
      toast.success(`${data.sent} envoyé(s) · ${data.failed} échec(s) · ${data.candidates} éligible(s)${data.code ? ` · code ${data.code}` : ""}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Envoi impossible"); }
    finally { setBusy(""); }
  };

  const Btn = ({ id, onClick, children, variant = "outline" }) => (
    <Button variant={variant} size="sm" className="rounded-sm gap-2" onClick={onClick} disabled={!!busy} data-testid={`admin-upsell-${id}`}>
      {busy === id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} {children}
    </Button>
  );

  return (
    <div className="space-y-4" data-testid="admin-campaigns-panel">
      <div className="surface rounded-md p-5 space-y-3" data-testid="admin-upsell-panel">
        <div>
          <h3 className="font-display font-bold text-lg">Emails d'incitation automatiques</h3>
          <p className="text-sm text-muted-foreground">J+3 après inscription : Premium (19 €) pour les particuliers, Pro (149 €) pour les artisans — 10:00 UTC. J+10 : relance avec code promo -20 % pendant 3 mois, valable 7 jours — 10:20 UTC. Un seul envoi par compte, opt-out respecté.</p>
        </div>
        <div className="grid sm:grid-cols-2 gap-4 text-xs">
          <div className="space-y-2">
            <p className="overline text-[10px]">J+3 — Incitation</p>
            <div className="flex flex-wrap gap-2">
              <Btn id="p-pro-j3" onClick={() => preview("pro", "j3")}>Aperçu email Pro</Btn>
              <Btn id="p-particulier-j3" onClick={() => preview("particulier", "j3")}>Aperçu email Particulier</Btn>
              <Btn id="r-j3" variant="default" onClick={() => runNow("j3")}>Envoyer maintenant</Btn>
            </div>
          </div>
          <div className="space-y-2">
            <p className="overline text-[10px]">J+10 — Relance code promo</p>
            <div className="flex flex-wrap gap-2">
              <Btn id="p-pro-j10" onClick={() => preview("pro", "j10")}>Aperçu Pro (promo)</Btn>
              <Btn id="p-particulier-j10" onClick={() => preview("particulier", "j10")}>Aperçu Particulier (promo)</Btn>
              <Btn id="r-j10" variant="default" onClick={() => runNow("j10")}>Envoyer maintenant</Btn>
            </div>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">Les aperçus sont envoyés à votre adresse admin. Les envois réels sont journalisés ci-dessous (types auto_upsell_j3 / auto_upsell_j10).</p>
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-display font-bold text-lg">Historique des campagnes e-mail</h3>
          <p className="text-sm text-muted-foreground">Envois groupés effectués depuis le détail des indicateurs.</p>
        </div>
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={load} data-testid="admin-campaigns-refresh">
          <RefreshCw className="h-4 w-4" /> Actualiser
        </Button>
      </div>

      {loading ? (
        <div className="h-40 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : rows.length === 0 ? (
        <div className="surface rounded-sm p-10 text-center text-muted-foreground">
          <Mail className="h-10 w-10 mx-auto opacity-40 mb-3" />
          <p className="text-sm">Aucune campagne envoyée pour le moment.</p>
          <p className="text-xs mt-1">Sélectionnez des contacts dans le détail d'un indicateur, puis « E-mail ».</p>
        </div>
      ) : (
        <div className="grid gap-2" data-testid="admin-campaigns-list">
          {rows.map((c, i) => (
            <div key={c.campaign_id || i} className="surface rounded-sm p-4 flex flex-wrap items-center gap-4"
                 data-testid={`admin-campaign-${i}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold truncate">{c.subject}</p>
                <p className="text-xs text-muted-foreground">
                  {c.created_at ? new Date(c.created_at).toLocaleString("fr-FR") : ""}
                  {c.sent_by ? ` · par ${c.sent_by}` : ""}
                </p>
              </div>
              <span className="text-sm flex items-center gap-1 text-muted-foreground">
                <Users className="h-4 w-4" /> {c.recipients_count} dest.
              </span>
              <span className="text-sm flex items-center gap-1 text-primary font-semibold">
                <CheckCircle2 className="h-4 w-4" /> {c.sent} envoyé(s)
              </span>
              {c.failed > 0 && (
                <span className="text-sm flex items-center gap-1 text-red-600">
                  <XCircle className="h-4 w-4" /> {c.failed} échec(s)
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
