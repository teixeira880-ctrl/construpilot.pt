import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Play, RefreshCw, Users, Mail, Building2, Power } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

function Stat({ icon: Icon, label, value, testid }) {
  return (
    <div className="surface rounded-md p-4" data-testid={testid}>
      <div className="flex items-center gap-2 text-muted-foreground text-xs"><Icon className="h-4 w-4" />{label}</div>
      <div className="text-2xl font-bold mt-1">{value}</div>
    </div>
  );
}

export default function BridgePanel() {
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [form, setForm] = useState({ enabled: true, min_budget: 3000, max_per_lead: 5, cooldown_days: 30, founder_name: "", founder_phone: "", site_url: "" });

  const load = () => api.get("/admin/bridge/stats").then(({ data }) => {
    setData(data);
    setForm({ ...data.settings });
  }).catch(() => {});

  useEffect(() => { load(); }, []);

  const save = async (patch) => {
    setSaving(true);
    try {
      const { data } = await api.post("/admin/bridge/settings", patch);
      setForm({ ...data });
      toast.success("Definições guardadas");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Falha");
    } finally { setSaving(false); }
  };

  const runBatch = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/admin/bridge/run-batch");
      toast.success(`${data.emails_sent ?? 0} e-mail(s) enviado(s) · ${data.leads ?? 0} lead(s)`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Falha do lote");
    } finally { setRunning(false); }
  };

  if (!data) return <div className="flex items-center gap-2 text-muted-foreground"><Loader2 className="h-4 w-4 animate-spin" /> A carregar…</div>;

  return (
    <div className="space-y-5" data-testid="admin-bridge-panel">
      <div>
        <h3 className="font-display font-bold text-lg">Agent Ponte B2B ↔ B2C</h3>
        <p className="text-sm text-muted-foreground">
          Cruza cada pedido de particular com a base de profissionais (Apify) do mesmo distrito e envia automaticamente um convite direcionado. Tempo real + lote diário.
        </p>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Stat icon={Building2} label="Profissionais (base)" value={data.artisans_active} testid="bridge-stat-artisans" />
        <Stat icon={Mail} label="Convites (7 d)" value={data.outreach_last_7d} testid="bridge-stat-7d" />
        <Stat icon={Mail} label="Convites (total)" value={data.outreach_total} testid="bridge-stat-total" />
        <Stat icon={Users} label="Leads tratados" value={data.leads_processed} testid="bridge-stat-leads" />
      </div>

      <div className="surface rounded-md p-5 space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Switch checked={form.enabled} onCheckedChange={(v) => save({ enabled: v })}
                    data-testid="bridge-enabled-switch" />
            <Label className="text-sm flex items-center gap-1"><Power className="h-4 w-4" /> Agente ativo</Label>
          </div>
          <Button variant="default" size="sm" className="rounded-sm gap-2" onClick={runBatch}
                  disabled={running} data-testid="bridge-run-batch">
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} Lançar o lote agora
          </Button>
        </div>

        <div className="grid sm:grid-cols-3 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Budget minimum (€)</Label>
            <Input type="number" min={0} value={form.min_budget}
                   onChange={(e) => setForm({ ...form, min_budget: Number(e.target.value) })}
                   onBlur={() => save({ min_budget: form.min_budget })} className="rounded-sm h-9 text-sm"
                   data-testid="bridge-min-budget" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Máx. profissionais / lead</Label>
            <Input type="number" min={1} max={20} value={form.max_per_lead}
                   onChange={(e) => setForm({ ...form, max_per_lead: Number(e.target.value) })}
                   onBlur={() => save({ max_per_lead: form.max_per_lead })} className="rounded-sm h-9 text-sm"
                   data-testid="bridge-max-per-lead" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Intervalo mínimo (dias)</Label>
            <Input type="number" min={1} value={form.cooldown_days}
                   onChange={(e) => setForm({ ...form, cooldown_days: Number(e.target.value) })}
                   onBlur={() => save({ cooldown_days: form.cooldown_days })} className="rounded-sm h-9 text-sm"
                   data-testid="bridge-cooldown" />
          </div>
        </div>
        {saving && <p className="text-xs text-muted-foreground">A guardar…</p>}

        <div className="grid sm:grid-cols-3 gap-4 pt-2 border-t border-border">
          <div className="space-y-1.5">
            <Label className="text-xs">Nome do fundador (assinatura)</Label>
            <Input value={form.founder_name}
                   onChange={(e) => setForm({ ...form, founder_name: e.target.value })}
                   onBlur={() => save({ founder_name: form.founder_name })}
                   placeholder="ex : Carlos" className="rounded-sm h-9 text-sm"
                   data-testid="bridge-founder-name" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Telefone (no e-mail)</Label>
            <Input value={form.founder_phone}
                   onChange={(e) => setForm({ ...form, founder_phone: e.target.value })}
                   onBlur={() => save({ founder_phone: form.founder_phone })}
                   placeholder="ex : 06 12 34 56 78" className="rounded-sm h-9 text-sm"
                   data-testid="bridge-founder-phone" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Site (signature)</Label>
            <Input value={form.site_url}
                   onChange={(e) => setForm({ ...form, site_url: e.target.value })}
                   onBlur={() => save({ site_url: form.site_url })}
                   placeholder="https://construpilot.pt" className="rounded-sm h-9 text-sm"
                   data-testid="bridge-site-url" />
          </div>
        </div>
      </div>

      <div className="flex items-center justify-between">
        <h4 className="font-semibold">Profissionais por distrito</h4>
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={load}
                data-testid="bridge-refresh"><RefreshCw className="h-4 w-4" /> Atualizar</Button>
      </div>
      {data.artisans_by_department?.length ? (
        <div className="flex flex-wrap gap-2" data-testid="bridge-by-dept">
          {data.artisans_by_department.map((d) => (
            <span key={d.department} className="text-sm px-3 py-1 rounded-full bg-muted" data-testid={`bridge-dept-${d.department}`}>
              Dist. {d.department} · <b>{d.count}</b>
            </span>
          ))}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Base vazia. Lance a predefinição «Leads» no separador Apify (com contactos) para a alimentar.
        </p>
      )}
    </div>
  );
}
