import { useEffect, useState } from "react";
import { api, eur } from "@/lib/api";
import { toast } from "sonner";

export function CostForecast({ chantierId, data, onSaved, onReload }) {
  const [rate, setRate] = useState(""), [remaining, setRemaining] = useState("");
  const [selected, setSelected] = useState([]), [busy, setBusy] = useState(false), [error, setError] = useState("");
  useEffect(() => { setRate(data.cost_settings?.labor_rate ?? ""); setRemaining(data.cost_settings?.remaining_cost_ht ?? ""); setSelected(data.scope.selected_ids || []); setError(""); }, [data]);
  const save = async e => {
    e.preventDefault(); setBusy(true); setError("");
    try { const { data: updated } = await api.put(`/chantiers/${chantierId}/cost-settings`, { expected_version: data.cost_version, labor_rate: rate === "" ? null : Number(rate), remaining_cost_ht: remaining === "" ? null : Number(remaining), quote_ids: selected }); onSaved(updated); toast.success("Hipóteses do orçamento guardadas"); }
    catch (e) { setError(e?.response?.data?.detail || "Não foi possível guardar"); }
    finally { setBusy(false); }
  };
  return <section className="rounded-xl border border-border bg-secondary/20 p-4 grid gap-4" data-testid="chantier-forecast">
    <div><h3 className="font-semibold">Previsão no final</h3><p className="text-xs text-muted-foreground mt-1">Compromissos registados + por comprometer. Uma estimativa baseada nas suas hipóteses, a atualizar com o avanço.</p></div>
    <div className="grid sm:grid-cols-3 gap-3">{[["Custo final estimado", data.forecast?.final_cost_ht], ["Margem final estimada", data.forecast?.margin_ht], ["Diferença face ao custo previsto", data.forecast?.over_budget_ht]].map(([label, value]) => <div key={label}><p className="text-xs text-muted-foreground">{label}</p><p className="text-xl font-semibold tabular-nums">{value == null ? "A completar" : eur(value)}</p></div>)}</div>
    <form onSubmit={save} className="grid gap-4">
      <fieldset><legend className="text-sm font-medium mb-2">Orçamentos que constituem o orçamento da obra</legend><p className="text-xs text-muted-foreground mb-2">Selecione os contratos e aditamentos a acumular, sem contar duas vezes uma versão substituída.</p>
        <div className="grid gap-2 max-h-40 overflow-auto">{(data.scope.available_quotes || []).map(q => <label key={q.doc_id} className="flex gap-2 items-center text-sm min-h-9"><input type="checkbox" checked={selected.includes(q.doc_id)} onChange={e => setSelected(s => e.target.checked ? [...s, q.doc_id] : s.filter(id => id !== q.doc_id))} />{q.label}</label>)}</div>
        {data.scope.selection_required && <p className="text-xs text-amber-700" role="status">Várias versões: escolha a sua referência para apresentar o orçamento.</p>}
      </fieldset>
      <div className="grid sm:grid-cols-2 gap-3"><label className="text-xs grid gap-1">Custo horário com encargos estimado (€/h)<input type="number" min="0" max="10000" step="0.01" value={rate} onChange={e => setRate(e.target.value)} className="rounded-lg border bg-background px-3 min-h-11 w-full" data-testid="chantier-costs-rate" placeholder="A preencher" /></label>
        <label className="text-xs grid gap-1">Por comprometer estimado (€ s/ IVA)<input type="number" min="0" max="10000000000" step="0.01" value={remaining} onChange={e => setRemaining(e.target.value)} className="rounded-lg border bg-background px-3 min-h-11 w-full" data-testid="chantier-remaining" placeholder="A preencher" /></label></div>
      <p className="text-xs text-muted-foreground">O valor por comprometer inclui as despesas futuras ainda não registadas. Exclua as encomendas já comprometidas, mesmo não entregues. Introduza 0 apenas se não for esperado nenhum custo adicional.</p>
      {error && <p role="alert" className="text-sm text-destructive">{error} <button type="button" className="underline min-h-10" onClick={onReload}>Recarregar o orçamento</button></p>}
      <button disabled={busy} className="rounded-lg border border-primary/30 text-primary bg-background min-h-11 px-4 py-2 text-sm font-medium justify-self-start disabled:opacity-50" data-testid="forecast-save">{busy ? "A guardar…" : "Guardar e recalcular"}</button>
    </form>
  </section>;
}

function Delivery({ chantierId, order, onSaved }) {
  const [form, setForm] = useState({ status: order.delivery.status || "awaiting", expected_date: order.delivery.expected_date || "", notes: order.delivery.notes || "" });
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const save = async e => {
    e.preventDefault(); setBusy(true); setError("");
    try { await api.put(`/chantiers/${chantierId}/purchases/${order.order_id}/delivery`, { ...form, expected_date: form.expected_date || null, expected_version: order.delivery_version }); onSaved(); }
    catch (e) { setError(e?.response?.data?.detail || "Acompanhamento não guardado"); }
    finally { setBusy(false); }
  };
  return <details className="rounded-xl border p-3"><summary className="cursor-pointer text-sm min-h-9"><span className="font-medium">{order.supplier}</span><span className="text-muted-foreground"> · {order.amount == null ? "Preço por preencher" : eur(order.amount)} · {({ awaiting: "Em espera", partial: "Entrega parcial", received: "Recebido", issue: "Incident" })[order.delivery.status || "awaiting"]}</span></summary>
    <form onSubmit={save} className="grid gap-3 pt-3"><div className="grid sm:grid-cols-2 gap-3"><label className="text-xs grid gap-1">Receção<select className="rounded-lg border bg-background min-h-11 px-2" value={form.status} onChange={e => setForm({ ...form, status: e.target.value })}><option value="awaiting">Em espera</option><option value="partial">Entrega parcial</option><option value="received">Recebido</option><option value="issue">Incidente a resolver</option></select></label><label className="text-xs grid gap-1">Entrega prevista<input type="date" className="rounded-lg border bg-background min-h-11 px-2 min-w-0" value={form.expected_date} onChange={e => setForm({ ...form, expected_date: e.target.value })} /></label></div>
      <label className="text-xs grid gap-1">Quantidades recebidas, em falta ou incidente<textarea className="rounded-lg border bg-background p-3" maxLength={2000} value={form.notes} onChange={e => setForm({ ...form, notes: e.target.value })} /></label>{error && <p className="text-sm text-destructive" role="alert">{error}</p>}<button disabled={busy} className="rounded-lg border min-h-11 px-3 text-sm justify-self-start">Guardar o acompanhamento</button></form>
  </details>;
}
export function PurchaseDeliveries({ chantierId, orders, onSaved }) {
  return <section className="grid gap-3" data-testid="purchase-deliveries"><h3 className="font-semibold">Compras e entregas</h3><p className="text-xs text-muted-foreground">Acompanhamento declarado das encomendas comprometidas. As encomendas em rascunho ficam excluídas dos custos comprometidos.</p>{orders.filter(o => o.engaged).map(o => <Delivery key={o.order_id + ':' + o.delivery_version} chantierId={chantierId} order={o} onSaved={onSaved} />)}{!orders.some(o => o.engaged) && <p className="text-sm text-muted-foreground">Nenhuma encomenda comprometida neste processo.</p>}</section>;
}
