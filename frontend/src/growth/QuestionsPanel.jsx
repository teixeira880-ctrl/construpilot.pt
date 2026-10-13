import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Check } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useApi, err } from "./lib";
import { Empty, ErrorBox } from "./Bits";

const INTENTS = ["descoberta", "comparaison", "achat", "necessidade profissional", "marque"];

export function QuestionsPanel({ projectId, canEdit }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/questions`, [projectId]);
  const [draft, setDraft] = useState({ text: "", intent: "descoberta", branded: false });
  const [editing, setEditing] = useState(null);
  const save = async (q) => { try { await api.put(`/growth/questions/${q.question_id}`, { text: q.text, intent: q.intent, branded: q.branded, active: q.active }); setEditing(null); reload(); } catch (e) { toast.error(err(e)); } };
  const add = async () => { try { await api.post(`/growth/projects/${projectId}/questions`, { ...draft, branded: draft.branded || draft.intent === "marque" }); setDraft({ ...draft, text: "" }); reload(); } catch (e) { toast.error(err(e)); } };
  const remove = async (q) => { try { await api.delete(`/growth/questions/${q.question_id}`); reload(); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  return <div className="space-y-4" data-testid="growth-questions">
    <p className="text-sm text-muted-foreground">{data.questions.length} questions · {data.questions.filter((q) => q.branded).length} com marca · editáveis antes da ativação; qualquer alteração do texto cria uma nova versão.</p>
    {canEdit && <div className="surface p-3 flex flex-wrap gap-2 items-center" data-testid="growth-question-form">
      <Input className="flex-1 min-w-[260px]" placeholder="Nova pergunta…" value={draft.text} onChange={(e) => setDraft({ ...draft, text: e.target.value })} data-testid="growth-question-text" />
      <select className="h-9 rounded-md border bg-background px-2 text-sm" value={draft.intent} onChange={(e) => setDraft({ ...draft, intent: e.target.value })} data-testid="growth-question-intent">{INTENTS.map((i) => <option key={i}>{i}</option>)}</select>
      <label className="text-xs flex items-center gap-1"><input type="checkbox" checked={draft.branded} onChange={(e) => setDraft({ ...draft, branded: e.target.checked })} /> mentionne ConstruPilot</label>
      <Button size="sm" onClick={add} disabled={draft.text.trim().length < 8} data-testid="growth-question-add"><Plus className="h-4 w-4" /> Adicionar</Button>
    </div>}
    {INTENTS.map((it) => { const qs = data.questions.filter((q) => q.intent === it); return qs.length ? <section key={it}>
      <h3 className="overline mb-1">{it} <span className="num">({qs.length})</span></h3>
      <ul className="divide-y border rounded-md">{qs.map((q) => <li key={q.question_id} className={`px-3 py-2 text-sm flex flex-wrap items-center gap-2 ${!q.active ? "opacity-50" : ""}`} data-testid={`growth-question-${q.question_id}`}>
        {editing?.question_id === q.question_id ? <><Input className="flex-1 min-w-[240px]" value={editing.text} onChange={(e) => setEditing({ ...editing, text: e.target.value })} /><Button size="sm" onClick={() => save(editing)} data-testid={`growth-question-save-${q.question_id}`}><Check className="h-4 w-4" /></Button></>
          : <span className="flex-1 min-w-[240px] cursor-text" onDoubleClick={() => canEdit && setEditing(q)}>{q.text}</span>}
        {q.branded && <Badge variant="outline" className="rounded-sm text-[10px]">marque</Badge>}<span className="num text-[10px] text-muted-foreground">v{q.version}</span>
        {canEdit && <><label className="text-xs flex items-center gap-1"><input type="checkbox" checked={q.active} onChange={() => save({ ...q, active: !q.active })} data-testid={`growth-question-active-${q.question_id}`} /> active</label>
          <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => remove(q)} data-testid={`growth-question-delete-${q.question_id}`}><Trash2 className="h-3.5 w-3.5" /></Button></>}
      </li>)}</ul></section> : null; })}
    {data.questions.length === 0 && <Empty>Nenhuma pergunta.</Empty>}
  </div>;
}

export function CompetitorsPanel({ projectId, canEdit }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/brands`, [projectId]);
  const [draft, setDraft] = useState({ name: "", variants: "", domains: "" });
  const add = async () => { try { await api.post(`/growth/projects/${projectId}/brands`, { name: draft.name, variants: draft.variants.split(",").map((s) => s.trim()).filter(Boolean), domains: draft.domains.split(",").map((s) => s.trim()).filter(Boolean), confirmed: true }); setDraft({ name: "", variants: "", domains: "" }); reload(); } catch (e) { toast.error(err(e)); } };
  const confirm = async (b) => { try { await api.put(`/growth/brands/${b.brand_id}`, { name: b.name, variants: b.variants, domains: b.domains, confirmed: true }); reload(); } catch (e) { toast.error(err(e)); } };
  const remove = async (b) => { try { await api.delete(`/growth/brands/${b.brand_id}`); reload(); } catch (e) { toast.error(err(e)); } };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  return <div className="space-y-4" data-testid="growth-competitors">
    <p className="text-sm text-muted-foreground">Marcas acompanhadas nas respostas IA (nomes, variantes, domínios). As sugestões devem ser confirmadas; nenhum concorrente é inventado: adicione os realmente observados nas respostas.</p>
    {canEdit && <div className="surface p-3 grid sm:grid-cols-4 gap-2" data-testid="growth-brand-form">
      <Input placeholder="Nome" value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })} data-testid="growth-brand-name" /><Input placeholder="Variantes (virgule)" value={draft.variants} onChange={(e) => setDraft({ ...draft, variants: e.target.value })} /><Input placeholder="Domínios (vírgula)" value={draft.domains} onChange={(e) => setDraft({ ...draft, domains: e.target.value })} data-testid="growth-brand-domains" />
      <Button size="sm" onClick={add} disabled={!draft.name.trim()} data-testid="growth-brand-add"><Plus className="h-4 w-4" /> Adicionar</Button></div>}
    <ul className="divide-y border rounded-md">{data.brands.map((b) => <li key={b.brand_id} className="px-3 py-2 text-sm flex flex-wrap items-center gap-2" data-testid={`growth-brand-${b.brand_id}`}>
      <strong className="min-w-[120px]">{b.name}</strong><span className="text-xs text-muted-foreground flex-1">{b.variants?.join(", ")} · {b.domains?.join(", ") || "—"}</span>
      {b.is_self && <Badge className="rounded-sm">ConstruPilot</Badge>}{b.suggested && !b.confirmed && <Badge variant="outline" className="rounded-sm text-amber-700">sugestão a confirmar</Badge>}
      {canEdit && !b.confirmed && <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => confirm(b)} data-testid={`growth-brand-confirm-${b.brand_id}`}><Check className="h-3.5 w-3.5" /> Confirmar</Button>}
      {canEdit && !b.is_self && <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive" onClick={() => remove(b)} data-testid={`growth-brand-delete-${b.brand_id}`}><Trash2 className="h-3.5 w-3.5" /></Button>}
    </li>)}</ul>
  </div>;
}
