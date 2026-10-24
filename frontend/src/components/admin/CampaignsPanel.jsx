import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Mail, Users, CheckCircle2, XCircle, RefreshCw, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";
import MarketingEmailsPanel from "@/components/admin/MarketingEmailsPanel";

function UpsellStats() {
  const [st, setSt] = useState(null);
  useEffect(() => { api.get("/admin/campaigns/upsell/stats").then(({ data }) => setSt(data)).catch(() => setSt({ weeks: [], total: null })); }, []);
  if (!st) return null;
  const pct = (v) => (v == null ? "—" : `${v} %`);
  return (
    <div className="border-t border-border/50 pt-3" data-testid="admin-upsell-stats">
      <p className="overline text-[10px] mb-2">Conversão em assinaturas pagas — por semana de envio</p>
      {st.total && (
        <p className="text-xs mb-2" data-testid="admin-upsell-stats-total">
          Total: D+3 <b className="num">{st.total.j3_sent}</b> enviados → <b className="num text-emerald-600">{st.total.conv_j3}</b> assinaturas ({pct(st.total.rate_j3)}) ·
          J+10 <b className="num">{st.total.j10_sent}</b> enviados → <b className="num text-emerald-600">{st.total.conv_j10}</b> assinaturas ({pct(st.total.rate_j10)})
        </p>
      )}
      {st.weeks.length === 0 ? <p className="text-xs text-muted-foreground">Nenhum envio automático por enquanto.</p> : (
        <table className="w-full text-xs">
          <thead><tr className="text-left text-muted-foreground border-b border-border">
            <th className="py-1 pr-3 font-medium">Semana</th><th className="py-1 pr-3 font-medium text-right">D+3 enviados</th><th className="py-1 pr-3 font-medium text-right">→ pagos</th>
            <th className="py-1 pr-3 font-medium text-right">D+10 enviados</th><th className="py-1 pr-3 font-medium text-right">→ pagos</th></tr></thead>
          <tbody>
            {st.weeks.map((w) => (
              <tr key={w.week} className="border-b border-border/40" data-testid={`admin-upsell-week-${w.week}`}>
                <td className="py-1 pr-3 num">{w.week}</td>
                <td className="py-1 pr-3 text-right num">{w.j3_sent}</td>
                <td className="py-1 pr-3 text-right num text-emerald-600">{w.conv_j3} <span className="text-muted-foreground">({pct(w.rate_j3)})</span></td>
                <td className="py-1 pr-3 text-right num">{w.j10_sent}</td>
                <td className="py-1 pr-3 text-right num text-emerald-600">{w.conv_j10} <span className="text-muted-foreground">({pct(w.rate_j10)})</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

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
      toast.success(`Pré-visualização enviada para ${data.to}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio da pré-visualização impossível"); }
    finally { setBusy(""); }
  };
  const runNow = async (step) => {
    if (!window.confirm(step === "j10" ? "Enviar o relançamento D+10 (código promocional) a todas as contas gratuitas elegíveis agora?" : "Enviar o email de incentivo D+3 a todas as contas gratuitas elegíveis agora?")) return;
    setBusy(`r-${step}`);
    try {
      const { data } = await api.post(`/admin/campaigns/upsell/run?step=${step}`);
      toast.success(`${data.sent} enviado(s) · ${data.failed} falha(s) · ${data.candidates} elegível(is)${data.code ? ` · code ${data.code}` : ""}`);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(""); }
  };

  const Btn = ({ id, onClick, children, variant = "outline" }) => (
    <Button variant={variant} size="sm" className="rounded-sm gap-2" onClick={onClick} disabled={!!busy} data-testid={`admin-upsell-${id}`}>
      {busy === id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} {children}
    </Button>
  );

  return (
    <div className="space-y-4" data-testid="admin-campaigns-panel">
      <MarketingEmailsPanel />
      <div className="surface rounded-md p-5 space-y-3" data-testid="admin-upsell-panel">
        <div>
          <h3 className="font-display font-bold text-lg">Emails de incentivo automáticos</h3>
          <p className="text-sm text-muted-foreground">D+3 após a inscrição: Premium (19 €) para particulares, Pro (149 €) para profissionais — 10:00 UTC. D+10: lembrete com código promocional -20 % durante 3 meses, válido 7 dias — 10:20 UTC. Um único envio por conta, opt-out respeitado.</p>
        </div>
        <div className="grid sm:grid-cols-2 gap-4 text-xs">
          <div className="space-y-2">
            <p className="overline text-[10px]">D+3 — Incentivo</p>
            <div className="flex flex-wrap gap-2">
              <Btn id="p-pro-j3" onClick={() => preview("pro", "j3")}>Pré-visualização email Pro</Btn>
              <Btn id="p-particulier-j3" onClick={() => preview("particulier", "j3")}>Pré-visualização email Particular</Btn>
              <Btn id="r-j3" variant="default" onClick={() => runNow("j3")}>Enviar agora</Btn>
            </div>
          </div>
          <div className="space-y-2">
            <p className="overline text-[10px]">D+10 — Relançamento código promocional</p>
            <div className="flex flex-wrap gap-2">
              <Btn id="p-pro-j10" onClick={() => preview("pro", "j10")}>Pré-visualização Pro (promo)</Btn>
              <Btn id="p-particulier-j10" onClick={() => preview("particulier", "j10")}>Pré-visualização Particular (promo)</Btn>
              <Btn id="r-j10" variant="default" onClick={() => runNow("j10")}>Enviar agora</Btn>
            </div>
          </div>
        </div>
        <p className="text-[11px] text-muted-foreground">As pré-visualizações são enviadas para o seu endereço admin. Os envios reais são registados abaixo (tipos auto_upsell_j3 / auto_upsell_j10).</p>
        <UpsellStats />
      </div>

      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-display font-bold text-lg">Histórico das campanhas e-mail</h3>
          <p className="text-sm text-muted-foreground">Envios em grupo efetuados a partir do detalhe dos indicadores.</p>
        </div>
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={load} data-testid="admin-campaigns-refresh">
          <RefreshCw className="h-4 w-4" /> Atualizar
        </Button>
      </div>

      {loading ? (
        <div className="h-40 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
      ) : rows.length === 0 ? (
        <div className="surface rounded-sm p-10 text-center text-muted-foreground">
          <Mail className="h-10 w-10 mx-auto opacity-40 mb-3" />
          <p className="text-sm">Nenhuma campanha enviada por enquanto.</p>
          <p className="text-xs mt-1">Selecione contactos no detalhe de um indicador, depois « E-mail ».</p>
        </div>
      ) : (
        <div className="grid gap-2" data-testid="admin-campaigns-list">
          {rows.map((c, i) => (
            <div key={c.campaign_id || i} className="surface rounded-sm p-4 flex flex-wrap items-center gap-4"
                 data-testid={`admin-campaign-${i}`}>
              <div className="min-w-0 flex-1">
                <p className="font-semibold truncate">{c.subject}</p>
                <p className="text-xs text-muted-foreground">
                  {c.created_at ? new Date(c.created_at).toLocaleString("pt-PT") : ""}
                  {c.sent_by ? ` · por ${c.sent_by}` : ""}
                </p>
              </div>
              <span className="text-sm flex items-center gap-1 text-muted-foreground">
                <Users className="h-4 w-4" /> {c.recipients_count} dest.
              </span>
              <span className="text-sm flex items-center gap-1 text-primary font-semibold">
                <CheckCircle2 className="h-4 w-4" /> {c.sent} enviado(s)
              </span>
              {c.failed > 0 && (
                <span className="text-sm flex items-center gap-1 text-red-600">
                  <XCircle className="h-4 w-4" /> {c.failed} falha(s)
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
