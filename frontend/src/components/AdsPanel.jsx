import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Megaphone, Trash2, Loader2, Pencil, BarChart3, Copy } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { api, eur, num } from "@/lib/api";
import { SectionTitle, Stat } from "@/components/Bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

const PLATFORMS = ["google", "meta", "instagram", "linkedin", "tiktok", "other"];
const EMPTY = { name: "", platform: "google", budget: "", spend: "", leads: "", revenue: "", status: "active", lead_source: "" };

export default function AdsPanel() {
  const [rows, setRows] = useState([]);
  const [sum, setSum] = useState(null);
  const [sources, setSources] = useState([]);
  const [channels, setChannels] = useState([]);
  const [utm, setUtm] = useState({ source: "instagram", campaign: "lancement" });
  const utmLink = `https://construpilot.fr/?utm_source=${utm.source}&utm_medium=social&utm_campaign=${encodeURIComponent(utm.campaign || "lancement")}`;
  const copyUtm = () => { navigator.clipboard.writeText(utmLink); toast.success("Link copiado — cole-o no seu anúncio"); };
  const [filters, setFilters] = useState({ platforms: [], months: [] });
  const [fPlatform, setFPlatform] = useState("");
  const [fMonth, setFMonth] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [editingId, setEditingId] = useState(null);
  const [saving, setSaving] = useState(false);
  const [toDelete, setToDelete] = useState(null);

  const load = () => {
    const params = {};
    if (fPlatform) params.platform = fPlatform;
    if (fMonth) params.month = fMonth;
    api.get("/ads/campaigns", { params }).then(({ data }) => setRows(data));
    api.get("/ads/summary", { params }).then(({ data }) => setSum(data));
    api.get("/ads/lead-sources").then(({ data }) => setSources(data)).catch(() => {});
    api.get("/ads/filters").then(({ data }) => setFilters(data)).catch(() => {});
    api.get("/ads/channels").then(({ data }) => setChannels(data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [fPlatform, fMonth]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const openNew = () => { setEditingId(null); setForm(EMPTY); setOpen(true); };
  const openEdit = (c) => {
    setEditingId(c.campaign_id);
    setForm({
      name: c.name, platform: c.platform || "google", status: c.status || "active",
      budget: String(c.budget ?? ""), spend: String(c.spend ?? ""),
      leads: String(c.leads ?? ""), revenue: String(c.revenue ?? ""),
      lead_source: c.lead_source || "",
    });
    setOpen(true);
  };

  const save = async () => {
    if (!form.name.trim()) return toast.error("Nom requis");
    setSaving(true);
    const payload = {
      name: form.name, platform: form.platform, status: form.status,
      budget: Number(form.budget) || 0, spend: Number(form.spend) || 0,
      leads: Number(form.leads) || 0, revenue: Number(form.revenue) || 0,
      lead_source: form.lead_source || "",
    };
    try {
      if (editingId) {
        await api.put(`/ads/campaigns/${editingId}`, payload);
        toast.success("Campanha modificada");
      } else {
        await api.post("/ads/campaigns", payload);
        toast.success("Campanha adicionada");
      }
      setOpen(false); setForm(EMPTY); setEditingId(null); load();
    } catch { toast.error("Erro"); } finally { setSaving(false); }
  };
  const del = async () => {
    if (!toDelete) return;
    await api.delete(`/ads/campaigns/${toDelete.campaign_id}`); toast.success("Eliminada"); setToDelete(null); load();
  };

  return (
    <div className="grid gap-6" data-testid="ads-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionTitle over="Marketing" title="Publicidade & aquisição">
          Acompanhe as suas campanhas publicitárias: despesas, leads gerados, custo por lead e ROI.
        </SectionTitle>
        <Button onClick={openNew} className="rounded-sm gap-2" data-testid="ads-new-btn">
          <Plus className="h-4 w-4" /> Nova campanha
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-2" data-testid="ads-filters">
        <span className="text-xs text-muted-foreground">Filtrer :</span>
        <select value={fPlatform} onChange={(e) => setFPlatform(e.target.value)} data-testid="ads-filter-platform"
          className="rounded-sm border border-border bg-background px-2 py-1.5 text-sm">
          <option value="">Todas as plataformas</option>
          {filters.platforms.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select value={fMonth} onChange={(e) => setFMonth(e.target.value)} data-testid="ads-filter-month"
          className="rounded-sm border border-border bg-background px-2 py-1.5 text-sm">
          <option value="">Todo o período</option>
          {filters.months.map((m) => <option key={m} value={m}>{m}</option>)}
        </select>
        {(fPlatform || fMonth) && (
          <button onClick={() => { setFPlatform(""); setFMonth(""); }} data-testid="ads-filter-reset"
            className="text-xs text-primary hover:underline">Reiniciar</button>
        )}
      </div>

      {sum && (
        <div className="grid grid-cols-2 lg:grid-cols-6 gap-3" data-testid="ads-kpis">
          <Stat label="Despesa total" value={eur(sum.total_spend)} />
          <Stat label="Budget" value={eur(sum.total_budget)} />
          <Stat label="Leads (saisis)" value={num(sum.total_leads)} />
          <Stat label="Leads reais (CRM)" value={num(sum.total_real_leads || 0)} accent />
          <Stat label="CPL real" value={sum.real_cpl != null ? eur(sum.real_cpl) : (sum.cpl != null ? eur(sum.cpl) : "—")} />
          <Stat label="ROAS" value={sum.roas != null ? `${sum.roas}×` : "—"} accent />
        </div>
      )}

      <div className="surface p-5 rounded-sm" data-testid="ads-utm-generator">
        <p className="text-sm font-display font-semibold mb-3">Gerador de link publicitário (UTM)</p>
        <div className="flex flex-wrap items-end gap-3">
          <div className="grid gap-1">
            <label className="text-xs text-muted-foreground">Rede</label>
            <select value={utm.source} onChange={(e) => setUtm({ ...utm, source: e.target.value })}
              className="rounded-sm h-9 border border-input bg-background px-2 text-sm" data-testid="utm-source">
              <option value="instagram">Instagram</option>
              <option value="linkedin">LinkedIn</option>
              <option value="facebook">Facebook</option>
              <option value="tiktok">TikTok</option>
            </select>
          </div>
          <div className="grid gap-1 flex-1 min-w-[160px]">
            <label className="text-xs text-muted-foreground">Nome de campanha</label>
            <input value={utm.campaign} onChange={(e) => setUtm({ ...utm, campaign: e.target.value })}
              className="rounded-sm h-9 border border-input bg-background px-2 text-sm w-full" data-testid="utm-campaign" placeholder="lancement" />
          </div>
          <Button size="sm" className="rounded-sm gap-2" onClick={copyUtm} data-testid="utm-copy"><Copy className="h-4 w-4" /> Copiar o link</Button>
        </div>
        <p className="mt-2 text-xs text-muted-foreground break-all num" data-testid="utm-preview">{utmLink}</p>
      </div>

      {channels && channels.length > 0 && (
        <div className="surface p-5 rounded-sm" data-testid="ads-channels">
          <p className="text-sm font-display font-semibold mb-3">Leads par canal d'acquisition</p>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
            {channels.map((c) => (
              <div key={c.channel} className="rounded-sm border border-border p-3 flex items-center justify-between" data-testid={`channel-${c.channel}`}>
                <span className="text-sm capitalize flex items-center gap-1.5">
                  <span className={`h-2 w-2 rounded-full ${c.channel === "linkedin" ? "bg-[#0a66c2]" : c.channel === "instagram" ? "bg-pink-500" : c.channel === "facebook" ? "bg-blue-600" : "bg-muted-foreground"}`} />
                  {c.channel}
                </span>
                <b className="num text-primary">{num(c.leads)}</b>
              </div>
            ))}
          </div>
        </div>
      )}

      {sum && sum.by_platform && sum.by_platform.length > 0 && (
        <div className="surface p-5 rounded-sm" data-testid="ads-chart">
          <div className="flex items-center gap-2 mb-4">
            <BarChart3 className="h-4 w-4 text-primary" />
            <p className="text-sm font-display font-semibold">Despesas vs leads por plataforma</p>
          </div>
          <div style={{ width: "100%", height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sum.by_platform} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="platform" tick={{ fontSize: 11 }} />
                <YAxis yAxisId="left" tick={{ fontSize: 10 }} width={48}
                  tickFormatter={(v) => `${v}€`} />
                <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} allowDecimals={false} width={32} />
                <Tooltip
                  contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 4, fontSize: 12 }}
                  formatter={(value, name) => name === "Despesa (€)" ? [eur(value), name] : [num(value), name]} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Bar yAxisId="left" dataKey="spend" name="Dépense (€)" fill="var(--primary)" radius={[3, 3, 0, 0]} maxBarSize={40} />
                <Bar yAxisId="right" dataKey="leads" name="Leads" fill="#f59e0b" radius={[3, 3, 0, 0]} maxBarSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {rows.length === 0 ? (
        <div className="surface p-10 text-center space-y-2" data-testid="ads-empty">
          <Megaphone className="h-8 w-8 mx-auto text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Nenhuma campanha. Adicione a sua primeira campanha publicitária.</p>
        </div>
      ) : (
        <div className="grid gap-2" data-testid="ads-list">
          {rows.map((c) => {
            const cpl = c.leads ? c.spend / c.leads : null;
            return (
              <div key={c.campaign_id} className="surface p-4 rounded-sm flex flex-wrap items-center gap-3" data-testid={`ads-row-${c.campaign_id}`}>
                <div className="min-w-0 flex-1">
                  <p className="font-display font-semibold">{c.name}</p>
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">
                    {c.platform} · {c.status}
                    {c.lead_source ? <span className="ml-1 text-primary normal-case">· CRM: {c.lead_source}</span> : null}
                  </p>
                </div>
                <div className="text-right text-sm"><span className="text-muted-foreground text-xs">Despesa</span><br /><span className="num font-bold">{eur(c.spend)}</span></div>
                <div className="text-right text-sm"><span className="text-muted-foreground text-xs">Leads</span><br /><span className="num font-bold">{num(c.leads)}</span></div>
                {c.lead_source ? (
                  <div className="text-right text-sm"><span className="text-muted-foreground text-xs">Leads reais</span><br /><span className="num font-bold text-emerald-500">{num(c.real_leads || 0)}</span></div>
                ) : null}
                <div className="text-right text-sm"><span className="text-muted-foreground text-xs">CPL {c.lead_source ? "real" : ""}</span><br /><span className="num font-bold text-primary">{(c.lead_source && c.real_cpl != null) ? eur(c.real_cpl) : (cpl != null ? eur(cpl) : "—")}</span></div>
                <Button size="icon" variant="ghost" className="h-8 w-8" onClick={() => openEdit(c)} data-testid={`ads-edit-${c.campaign_id}`}><Pencil className="h-4 w-4" /></Button>
                <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => setToDelete(c)} data-testid={`ads-del-${c.campaign_id}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editingId ? "Modificar a campanha" : "Nova campanha"}</DialogTitle>
            <DialogDescription>Indique a despesa e os leads para calcular o custo por lead.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div><Label>Nom</Label><Input value={form.name} onChange={set("name")} className="rounded-sm mt-1" data-testid="ads-name" /></div>
            <div><Label>Plateforme</Label>
              <select value={form.platform} onChange={set("platform")} data-testid="ads-platform"
                className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm">
                {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Budget (€)</Label><Input type="number" value={form.budget} onChange={set("budget")} className="rounded-sm mt-1 num" data-testid="ads-budget" /></div>
              <div><Label>Despesa (€)</Label><Input type="number" value={form.spend} onChange={set("spend")} className="rounded-sm mt-1 num" data-testid="ads-spend" /></div>
              <div><Label>Leads</Label><Input type="number" value={form.leads} onChange={set("leads")} className="rounded-sm mt-1 num" data-testid="ads-leads" /></div>
              <div><Label>Volume de negócios atribuído (€)</Label><Input type="number" value={form.revenue} onChange={set("revenue")} className="rounded-sm mt-1 num" data-testid="ads-revenue" /></div>
            </div>
            <div>
              <Label>Source CRM (attribution auto)</Label>
              <Input value={form.lead_source} onChange={set("lead_source")} list="ads-lead-sources"
                placeholder="ex. landing-google, meta-printemps…"
                className="rounded-sm mt-1" data-testid="ads-lead-source" />
              <datalist id="ads-lead-sources">
                {sources.map((s) => <option key={s} value={s} />)}
              </datalist>
              <p className="text-[11px] text-muted-foreground mt-1">
                Ligue esta campanha ao campo «origem» dos seus leads CRM para calcular automaticamente o custo real por lead.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} className="rounded-sm">Cancelar</Button>
            <Button onClick={save} disabled={saving} className="rounded-sm gap-2" data-testid="ads-save">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Guardar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent data-testid="ads-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Eliminar a campanha&nbsp;?</AlertDialogTitle>
            <AlertDialogDescription>
              « {toDelete?.name} » será definitivamente eliminada. Esta ação é irreversível.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-sm" data-testid="ads-delete-cancel">Cancelar</AlertDialogCancel>
            <AlertDialogAction onClick={del} className="rounded-sm bg-red-600 hover:bg-red-700" data-testid="ads-delete-confirm">Eliminar</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
