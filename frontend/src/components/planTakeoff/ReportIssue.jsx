import { useEffect, useState } from "react";
import { Flag, History } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { pollCotesJob } from "@/lib/cotesJobs";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";

const fmt = (d) => new Date(d).toLocaleString("pt-PT", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });

export function ReportIssueButton({ plan, pageIndex, target, onReported }) {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ element: "", description: "", expected_value: "" });
  useEffect(() => { if (target) setForm((f) => ({ ...f, element: f.element || target })); }, [target]);
  const submit = async () => {
    try {
      await api.post(`/takeoffs/${plan.plan_id}/cotes/issues`, { page_index: pageIndex, target: target || "", ...form });
      toast.success("Erro assinalado — a análise está marcada «a rever», foi arquivada uma versão");
      setOpen(false); setForm({ element: "", description: "", expected_value: "" }); onReported?.();
    } catch (e) { toast.error(e?.response?.data?.detail?.[0]?.msg || e?.response?.data?.detail || "Assinalar impossível"); }
  };
  return (
    <>
      <Button size="sm" variant="outline" className="rounded-sm gap-1 border-orange-400 text-orange-700" onClick={() => setOpen(true)} data-testid="report-issue-btn"><Flag className="h-3.5 w-3.5" /> Comunicar um erro de análise</Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent data-testid="report-issue-dialog">
          <DialogHeader><DialogTitle>Comunicar um erro de análise</DialogTitle></DialogHeader>
          <div className="grid gap-3 text-sm">
            {target && <p className="text-xs text-muted-foreground">Elemento selecionado: <b>{target}</b></p>}
            <label className="grid gap-1">Cota / medida / elemento em causa<input className="border rounded-sm px-2 py-1.5 bg-background" value={form.element} onChange={(e) => setForm({ ...form, element: e.target.value })} placeholder="ex.: Cota n.º 16 (5,33 m), INT-H-006, parede M13…" data-testid="issue-element" /></label>
            <label className="grid gap-1">Descrição do erro<textarea className="border rounded-sm px-2 py-1.5 bg-background" rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="O que está errado, o que a planta mostra realmente…" data-testid="issue-description" /></label>
            <label className="grid gap-1">Valor esperado (opcional)<input className="border rounded-sm px-2 py-1.5 bg-background" value={form.expected_value} onChange={(e) => setForm({ ...form, expected_value: e.target.value })} placeholder="ex. 4.57" data-testid="issue-expected" /></label>
            <div className="flex justify-end gap-2"><Button variant="ghost" onClick={() => setOpen(false)}>Cancelar</Button><Button onClick={submit} disabled={form.element.length < 2 || form.description.length < 5} data-testid="issue-submit">Enviar a comunicação</Button></div>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

export function VersionHistory({ plan, pageIndex, refreshKey, onChanged }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(null);
  const reanalyze = async (id) => {
    setBusy(id);
    try {
      const r = await api.post(`/takeoffs/${plan.plan_id}/cotes/issues/${id}/reanalyze`);
      const res = await pollCotesJob(r.data.job_id, { timeoutMs: 600000 });
      toast[res.changed ? "success" : "info"](res.changed ? `Alvo recalculado: valor alterado — versão v${res.version}, ocorrência encerrada` : `Alvo recalculado: valor inalterado (versão v${res.version} arquivada)`);
      const d = await api.get(`/takeoffs/${plan.plan_id}/cotes/versions?page_index=${pageIndex}`); setData(d.data); onChanged?.();
    } catch (e) { toast.error(e?.response?.data?.detail || e.message || "Nova análise impossível"); }
    finally { setBusy(null); }
  };
  useEffect(() => { if (open) api.get(`/takeoffs/${plan.plan_id}/cotes/versions?page_index=${pageIndex}`).then((r) => setData(r.data)).catch(() => setData({ versions: [], issues: [] })); }, [open, plan?.plan_id, pageIndex, refreshKey]);
  const resolve = async (id) => { await api.patch(`/takeoffs/${plan.plan_id}/cotes/issues/${id}`, { resolution: "Corrigido após recálculo" }); toast.success("Ocorrência encerrada"); setData(null); setOpen(false); setTimeout(() => setOpen(true), 50); };
  return (
    <details className="text-xs border rounded-sm p-3 bg-card" open={open} onToggle={(e) => setOpen(e.target.open)} data-testid="version-history">
      <summary className="cursor-pointer font-medium flex items-center gap-1"><History className="h-3.5 w-3.5" /> Histórico de versões e comunicações</summary>
      {data && (
        <div className="grid gap-2 mt-2">
          <div className="grid gap-1">
            {data.versions.length === 0 && <p className="text-muted-foreground">Nenhuma versão arquivada.</p>}
            {data.versions.map((v) => (
              <div key={v.version_id} className="flex flex-wrap gap-x-2 border-l-2 pl-2" data-testid={`version-${v.version}`}>
                <b>v{v.version}</b><span>{fmt(v.created_at)}</span>
                <span className="text-muted-foreground">{{ check: "recálculo das cotas", issue_reported: "comunicação do utilizador", reanalysis: "nova análise IA", guided_correction: "correção guiada" }[v.trigger] || v.trigger}</span>
                {v.trigger === "guided_correction" && <span className={v.changed ? "text-emerald-700" : "text-muted-foreground"}>· alvo {v.changed ? "alterada" : "inalterada"}</span>}
                {v.summary && <span>· {v.summary.ok} ok / {v.summary.warn} diferenças / {v.summary.ko} incoerências</span>}
                {v.interior_validation && <span>· interior: {v.interior_validation.complete ? "complet" : "incomplet"}</span>}
                {v.open_issues > 0 && <span className="text-orange-600">· {v.open_issues} ocorrência(s) em aberto</span>}
              </div>
            ))}
          </div>
          {data.issues.length > 0 && (
            <div className="grid gap-1" data-testid="issue-list">
              <b>Ocorrências</b>
              {data.issues.map((i) => (
                <div key={i.issue_id} className={`flex flex-wrap items-center gap-x-2 border-l-2 pl-2 ${i.status === "open" ? "border-orange-500" : "border-emerald-500"}`} data-testid={`issue-${i.issue_id}`}>
                  <span className="font-medium">{i.element}</span>{i.target && <span className="font-mono text-muted-foreground">{i.target}</span>}
                  <span>— {i.description}</span>{i.expected_value && <span>· esperado {i.expected_value}</span>}
                  <span className="text-muted-foreground">{fmt(i.created_at)}</span>
                  {i.status === "open" ? (<>
                    <button className="underline text-primary" disabled={busy === i.issue_id} onClick={() => reanalyze(i.issue_id)} data-testid={`issue-reanalyze-${i.issue_id}`}>{busy === i.issue_id ? "reanálise em curso…" : "correção guiada (reanalisar o alvo)"}</button>
                    <button className="underline" onClick={() => resolve(i.issue_id)} data-testid={`issue-resolve-${i.issue_id}`}>marcar corrigido</button>
                  </>) : <span className="text-emerald-700">corrigido</span>}
                  {i.resolution && <span className="block w-full text-muted-foreground">{i.resolution}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </details>
  );
}
