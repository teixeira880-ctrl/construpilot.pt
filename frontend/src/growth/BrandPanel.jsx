import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Pencil, Check } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useApi, err } from "./lib";
import { Empty, ErrorBox } from "./Bits";

const FACT_STATUS = { confirmed: ["confirmado", "bg-emerald-500/15 text-emerald-700"], to_verify: ["a verificar", "bg-amber-500/15 text-amber-700"], planned: ["previsto", "bg-muted text-muted-foreground"] };
const EMPTY = { category: "produit", statement: "", source: "", date: new Date().toISOString().slice(0, 10), status: "to_verify" };

export function BrandPanel({ projectId, canEdit }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/facts`, [projectId]);
  const [form, setForm] = useState(null);
  const save = async () => {
    try {
      if (form.fact_id) await api.put(`/growth/facts/${form.fact_id}`, form); else await api.post(`/growth/projects/${projectId}/facts`, form);
      toast.success("Ficha de marca atualizada"); setForm(null); reload();
    } catch (e) { toast.error(err(e)); }
  };
  const remove = async (f) => { try { await api.delete(`/growth/facts/${f.fact_id}`); reload(); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const cats = [...new Set(data.facts.map((f) => f.category))];
  return <div className="space-y-4" data-testid="growth-brand">
    <div className="flex flex-wrap items-center gap-2">
      <p className="text-sm text-muted-foreground flex-1">Cada informação tem uma fonte, uma data e um estado. <strong>Só os factos «confirmado» alimentam as afirmações publicadas.</strong></p>
      {canEdit && <Button size="sm" onClick={() => setForm(EMPTY)} data-testid="growth-fact-add"><Plus className="h-4 w-4" /> Adicionar um facto</Button>}
    </div>
    {form && <div className="surface p-3 grid sm:grid-cols-2 gap-2" data-testid="growth-fact-form">
      <Input placeholder="Categoria (produto, preços, provas…)" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} data-testid="growth-fact-category" />
      <select className="h-9 rounded-md border bg-background px-2 text-sm" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} data-testid="growth-fact-status">
        {Object.entries(FACT_STATUS).map(([k, [l]]) => <option key={k} value={k}>{l}</option>)}
      </select>
      <Input className="sm:col-span-2" placeholder="Afirmação" value={form.statement} onChange={(e) => setForm({ ...form, statement: e.target.value })} data-testid="growth-fact-statement" />
      <Input placeholder="Fonte (URL, documento, pessoa)" value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} data-testid="growth-fact-source" />
      <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })} data-testid="growth-fact-date" />
      <div className="flex gap-2 sm:col-span-2"><Button size="sm" onClick={save} disabled={!form.statement.trim()} data-testid="growth-fact-save"><Check className="h-4 w-4" /> Guardar</Button><Button size="sm" variant="ghost" onClick={() => setForm(null)}>Cancelar</Button></div>
    </div>}
    {cats.length === 0 && <Empty>Nenhum facto indicado.</Empty>}
    {cats.map((c) => <section key={c}>
      <h3 className="overline mb-1">{c}</h3>
      <ul className="divide-y border rounded-md">
        {data.facts.filter((f) => f.category === c).map((f) => <li key={f.fact_id} className="px-3 py-2 text-sm flex flex-wrap items-start gap-2" data-testid={`growth-fact-${f.fact_id}`}>
          <div className="flex-1 min-w-[220px]"><p>{f.statement}</p><p className="text-[11px] text-muted-foreground">Fonte: {f.source || "—"} · {f.date || "—"}</p></div>
          <Badge className={`rounded-sm border-0 ${FACT_STATUS[f.status]?.[1]}`}>{FACT_STATUS[f.status]?.[0] || f.status}</Badge>
          {canEdit && <><Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => setForm(f)} data-testid={`growth-fact-edit-${f.fact_id}`}><Pencil className="h-3.5 w-3.5" /></Button>
            <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => remove(f)} data-testid={`growth-fact-delete-${f.fact_id}`}><Trash2 className="h-3.5 w-3.5" /></Button></>}
        </li>)}
      </ul>
    </section>)}
  </div>;
}
