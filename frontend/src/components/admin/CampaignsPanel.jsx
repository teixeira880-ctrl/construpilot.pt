import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Mail, Users, CheckCircle2, XCircle, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export default function CampaignsPanel() {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.get("/admin/campaigns")
      .then(({ data }) => setRows(data.campaigns || []))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  return (
    <div className="space-y-4" data-testid="admin-campaigns-panel">
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
