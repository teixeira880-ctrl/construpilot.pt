import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Plus, Trash2, Save } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

// Recursos e custos da empresa: mão de obra por função (custo/hora carregado), veículos (custo/dia + consumo),
// máquinas, gasóleo, custos de estrutura e parâmetros de obra — usados no dossier económico (custo, venda, margem).
const KIND = { mao_de_obra: "Mão de obra", veiculo: "Veículo", maquina: "Máquina" };
const UNIT = { h: "€/h", dia: "€/dia", km: "€/km", mes: "€/mês" };
const PARAMS = [
  ["fuel_price_l", "Gasóleo (€/L)", 0.01], ["km_per_day", "Km por dia de obra", 1], ["hours_per_day", "Horas de trabalho por dia", 0.5],
  ["overhead_pct", "Custos de estrutura (% do custo)", 0.5], ["target_margin_pct", "Margem-alvo (%)", 0.5],
  ["labour_share_pct", "Parte de mão de obra nos custos diretos (%)", 1], ["supervision_h_week", "Enquadramento (h/semana)", 0.5],
  ["truck_days_pct", "Camião (% dos dias de obra)", 1], ["digger_days_pct", "Giratória (% dos dias de obra)", 1],
];

export default function CostResourcesPanel() {
  const [data, setData] = useState(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { api.get("/company/cost-resources").then(({ data: d }) => setData(d)).catch(() => toast.error("Impossível carregar os recursos")); }, []);
  if (!data) return <div className="surface p-10 text-center animate-pulse">A carregar…</div>;
  const res = data.resources || [];
  const P = data.params || {};
  const setRes = (i, k, v) => setData((d) => ({ ...d, resources: d.resources.map((r, j) => (j === i ? { ...r, [k]: v } : r)) }));
  const setP = (k, v) => setData((d) => ({ ...d, params: { ...d.params, [k]: v } }));
  const setTeam = (grp, id, v) => setData((d) => ({ ...d, params: { ...d.params, [grp]: { ...(d.params[grp] || {}), [id]: v } } }));
  const add = (kind) => setData((d) => ({ ...d, resources: [...d.resources, { id: `${kind}_${Date.now().toString(36)}`, kind, name: "", unit: kind === "mao_de_obra" ? "h" : "dia", cost: 0, origin: "empresa" }] }));
  const save = async () => {
    setSaving(true);
    try {
      const num = (v) => (v === "" || v == null ? null : Number(v));
      const body = {
        resources: res.filter((r) => r.name).map((r) => ({ id: r.id, kind: r.kind, name: r.name, unit: r.unit, cost: Number(r.cost) || 0,
          consumption_l_100km: r.kind === "veiculo" ? num(r.consumption_l_100km) : null })),
        params: Object.fromEntries([...PARAMS.map(([k]) => [k, num(P[k])]),
          ["team", P.team || {}], ["vehicles", P.vehicles || {}], ["machines", P.machines || {}]]),
      };
      const { data: d } = await api.put("/company/cost-resources", body);
      setData(d);
      toast.success("Recursos guardados — usados nos dossiers económicos");
    } catch (e) { toast.error(e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || "Não foi possível guardar"); }
    finally { setSaving(false); }
  };
  const group = (kind) => res.map((r, i) => [r, i]).filter(([r]) => r.kind === kind);
  return (
    <div className="grid gap-5" data-testid="cost-resources">
      <p className="text-sm text-muted-foreground">
        Os custos reais da sua empresa: cada colaborador por função (custo/hora com encargos), veículos (custo/dia e consumo),
        máquinas, gasóleo e custos de estrutura. Entram no <b>dossier económico</b> de cada orçamento (custo, venda e margem).
        Os valores marcados <b>hipótese</b> são valores por defeito — substitua-os pelos seus.
      </p>
      {Object.keys(KIND).map((kind) => (
        <div key={kind} className="surface p-4 grid gap-2">
          <div className="flex items-center justify-between">
            <p className="font-display font-bold text-sm">{KIND[kind]}</p>
            <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={() => add(kind)} data-testid={`cost-add-${kind}`}><Plus className="h-3.5 w-3.5" /> Adicionar</Button>
          </div>
          {group(kind).map(([r, i]) => {
            const grp = kind === "mao_de_obra" ? "team" : kind === "veiculo" ? "vehicles" : "machines";
            return (
              <div key={r.id} className="grid grid-cols-12 gap-2 items-center" data-testid={`cost-row-${r.id}`}>
                <Input className="col-span-12 md:col-span-4 rounded-sm" value={r.name} placeholder="Função / veículo / máquina" onChange={(e) => setRes(i, "name", e.target.value)} />
                <div className="col-span-4 md:col-span-2 flex items-center gap-1">
                  <Input type="number" step="0.01" min="0" className="rounded-sm num" value={r.cost} onChange={(e) => setRes(i, "cost", e.target.value)} />
                  <select className="rounded-sm border border-border bg-background px-1 py-2 text-xs" value={r.unit} onChange={(e) => setRes(i, "unit", e.target.value)}>
                    {Object.entries(UNIT).map(([u, l]) => <option key={u} value={u}>{l}</option>)}
                  </select>
                </div>
                {kind === "veiculo" ? (
                  <div className="col-span-4 md:col-span-2 flex items-center gap-1 text-xs"><Input type="number" step="0.1" min="0" className="rounded-sm num" value={r.consumption_l_100km ?? ""} onChange={(e) => setRes(i, "consumption_l_100km", e.target.value)} /> L/100km</div>
                ) : <span className="hidden md:block md:col-span-2" />}
                <div className="col-span-3 md:col-span-2 flex items-center gap-1 text-xs">
                  <Input type="number" step="0.5" min="0" className="rounded-sm num" value={(P[grp] || {})[r.id] ?? ""} placeholder="0" onChange={(e) => setTeam(grp, r.id, e.target.value === "" ? 0 : Number(e.target.value))} />
                  <span className="text-muted-foreground">{kind === "mao_de_obra" ? "na equipa" : "por obra"}</span>
                </div>
                <span className={`col-span-1 text-[10px] uppercase font-bold ${r.origin === "empresa" ? "text-primary" : "text-amber-600"}`}>{r.origin === "empresa" ? "empresa" : "hipótese"}</span>
                <Button size="icon" variant="ghost" className="col-span-1 h-7 w-7 text-destructive" onClick={() => setData((d) => ({ ...d, resources: d.resources.filter((_, j) => j !== i) }))}><Trash2 className="h-3.5 w-3.5" /></Button>
              </div>
            );
          })}
        </div>
      ))}
      <div className="surface p-4 grid sm:grid-cols-3 gap-3">
        <p className="sm:col-span-3 font-display font-bold text-sm">Parâmetros de obra</p>
        {PARAMS.map(([k, label, step]) => (
          <label key={k} className="text-xs grid gap-1">{label}
            <Input type="number" step={step} min="0" className="rounded-sm num" value={P[k] ?? ""} onChange={(e) => setP(k, e.target.value)} data-testid={`cost-param-${k}`} />
          </label>
        ))}
      </div>
      <div><Button onClick={save} disabled={saving} className="rounded-sm gap-2" data-testid="cost-save">{saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Guardar os recursos da empresa</Button></div>
    </div>
  );
}
