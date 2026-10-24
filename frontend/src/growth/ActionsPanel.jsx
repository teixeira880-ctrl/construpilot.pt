import { useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Wand2, FileText } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { useApi, err, STATUS_FR } from "./lib";
import { Empty, ErrorBox } from "./Bits";

const IMPACT = { fort: "bg-red-500/15 text-red-700", moyen: "bg-amber-500/15 text-amber-700", faible: "bg-muted text-muted-foreground" };
const EMPTY = { title: "", problem: "", evidence: "", url: "", impact: "moyen", effort: "moyen", owner: "", due_date: "", kpi: "" };

export function ActionsPanel({ projectId, canEdit, onContent }) {
  const { data, error, reload } = useApi(`/growth/projects/${projectId}/actions`, [projectId]);
  const [form, setForm] = useState(null);
  const [busy, setBusy] = useState(false);
  const gen = async () => { setBusy(true); try { const r = await api.post(`/growth/projects/${projectId}/actions/generate`); toast.success(r.data.created ? `${r.data.created} ação(ões) criada(s) a partir da auditoria e da última campanha` : "Nada de novo: lance uma auditoria ou uma campanha"); reload(); } catch (e) { toast.error(err(e)); } finally { setBusy(false); } };
  const save = async () => { try { await api.post(`/growth/projects/${projectId}/actions`, form); setForm(null); reload(); } catch (e) { toast.error(err(e)); } };
  const patch = async (a, changes) => { try { await api.put(`/growth/actions/${a.action_id}`, { ...a, ...changes }); reload(); } catch (e) { toast.error(err(e)); } };
  const remove = async (a) => { try { await api.delete(`/growth/actions/${a.action_id}`); reload(); } catch (e) { toast.error(err(e)); } };
  const toContent = async (a) => {
    try { const r = await api.post(`/growth/projects/${projectId}/contents`, { topic: a.title.replace(/^Publier une réponse utile à : /, "").replace(/[«»]/g, "").trim(), intent: a.source === "campaign" ? "découverte" : "besoin métier", action_id: a.action_id, question_id: a.question_id || "" }); toast.success("Ideia de conteúdo criada"); onContent?.(r.data.content_id); }
    catch (e) { toast.error(err(e)); }
  };
  if (error) return <ErrorBox error={error} onRetry={reload} />;
  if (!data) return null;
  const order = { fort: 0, moyen: 1, faible: 2 };
  const list = [...data.actions].sort((a, b) => (a.status === "done") - (b.status === "done") || order[a.impact] - order[b.impact]);
  return <div className="space-y-4" data-testid="growth-actions">
    <div className="flex flex-wrap gap-2 items-center">
      <p className="text-sm text-muted-foreground flex-1">Plano priorizado: tarefa, problema, prova, URL, impacto, esforço, responsável, prazo, indicador. As ações provenientes de uma campanha são hipóteses a verificar.</p>
      {canEdit && <Button size="sm" variant="outline" onClick={gen} disabled={busy} data-testid="growth-actions-generate"><Wand2 className="h-4 w-4" /> Gerar a partir de auditoria + campanha</Button>}
      {canEdit && <Button size="sm" onClick={() => setForm(EMPTY)} data-testid="growth-action-add"><Plus className="h-4 w-4" /> Ação manual</Button>}
    </div>
    {form && <div className="surface p-3 grid sm:grid-cols-2 gap-2 text-sm" data-testid="growth-action-form">
      <Input className="sm:col-span-2" placeholder="Tarefa precisa" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} data-testid="growth-action-title" />
      <Input placeholder="Problema / oportunidade" value={form.problem} onChange={(e) => setForm({ ...form, problem: e.target.value })} /><Input placeholder="Prova" value={form.evidence} onChange={(e) => setForm({ ...form, evidence: e.target.value })} />
      <Input placeholder="URL em causa" value={form.url} onChange={(e) => setForm({ ...form, url: e.target.value })} /><Input placeholder="Indicador a acompanhar" value={form.kpi} onChange={(e) => setForm({ ...form, kpi: e.target.value })} />
      <select className="h-9 rounded-md border bg-background px-2" value={form.impact} onChange={(e) => setForm({ ...form, impact: e.target.value })}><option value="fort">impacto forte</option><option value="moyen">impacto médio</option><option value="faible">impacto fraco</option></select>
      <select className="h-9 rounded-md border bg-background px-2" value={form.effort} onChange={(e) => setForm({ ...form, effort: e.target.value })}><option value="faible">esforço reduzido</option><option value="moyen">esforço médio</option><option value="élevé">esforço elevado</option></select>
      <Input placeholder="Responsável" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /><Input type="date" value={form.due_date} onChange={(e) => setForm({ ...form, due_date: e.target.value })} />
      <div className="flex gap-2 sm:col-span-2"><Button size="sm" onClick={save} disabled={!form.title.trim()} data-testid="growth-action-save">Guardar</Button><Button size="sm" variant="ghost" onClick={() => setForm(null)}>Cancelar</Button></div>
    </div>}
    {list.length === 0 && <Empty testid="growth-actions-empty">Nenhuma ação. Gere o plano a partir da última auditoria e da última campanha.</Empty>}
    <ul className="divide-y border rounded-md">{list.map((a) => <li key={a.action_id} className={`px-3 py-2 text-sm space-y-1 ${a.status === "done" ? "opacity-50" : ""}`} data-testid={`growth-action-${a.action_id}`}>
      <div className="flex flex-wrap items-center gap-2"><Badge className={`rounded-sm border-0 ${IMPACT[a.impact]}`}>impact {a.impact}</Badge><Badge variant="outline" className="rounded-sm">effort {a.effort}</Badge><strong className="flex-1 min-w-[200px]">{a.title}</strong>
        <Badge variant="outline" className="rounded-sm text-[10px]">{a.source}</Badge>
        {canEdit && <select className="h-7 rounded-md border bg-background px-1 text-xs" value={a.status} onChange={(e) => patch(a, { status: e.target.value })} data-testid={`growth-action-status-${a.action_id}`}><option value="todo">a fazer</option><option value="doing">em curso</option><option value="done">feito</option></select>}
        {!canEdit && <span className="text-xs">{STATUS_FR[a.status]}</span>}</div>
      <p className="text-xs"><strong>Problema:</strong> {a.problem || "—"} · <strong>Prova:</strong> {a.evidence || "—"}</p>
      <p className="text-xs text-muted-foreground">{a.url && <a className="underline mr-2" href={a.url} target="_blank" rel="noreferrer">{a.url}</a>}Responsável: {a.owner || "—"} · Prazo: {a.due_date || "—"} · Indicador: {a.kpi || "—"}</p>
      {canEdit && a.status !== "done" && <div className="flex gap-2"><Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => toContent(a)} data-testid={`growth-action-content-${a.action_id}`}><FileText className="h-3.5 w-3.5" /> Preparar um conteúdo</Button>
        <Button size="sm" variant="ghost" className="h-7 text-xs text-destructive" onClick={() => remove(a)}><Trash2 className="h-3.5 w-3.5" /></Button></div>}
    </li>)}</ul>
  </div>;
}
