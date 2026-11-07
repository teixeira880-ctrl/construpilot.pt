import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Check, ChevronLeft, Loader2, Sparkles } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { MODES } from "@/lib/workProfile";

const Chip = ({ active, onClick, children, testid }) => (
  <button type="button" onClick={onClick} data-testid={testid} aria-pressed={active}
    className={`min-h-11 rounded-xl border px-3 py-2 text-left text-sm transition ${active ? "border-primary bg-primary/10 font-semibold text-foreground" : "border-border bg-card hover:border-primary/60"}`}>
    {active && <Check className="mr-1 inline h-4 w-4 text-primary" aria-hidden="true" />}{children}
  </button>
);

const toggle = (list, key) => (list.includes(key) ? list.filter(k => k !== key) : [...list, key]);

/** Onboarding curto (3 perguntas), sempre editável e sempre possível de saltar. */
export function WorkProfileOnboarding({ open, onOpenChange, profile, onSave }) {
  const [catalog, setCatalog] = useState(null);
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState(profile);
  const [describe, setDescribe] = useState("");
  const [suggested, setSuggested] = useState([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => { if (open) { setDraft(profile); setStep(0); setSuggested([]); } }, [open, profile]);
  useEffect(() => { if (open && !catalog) api.get("/me/work-profile/catalog").then(({ data }) => setCatalog(data)).catch(() => {}); }, [open, catalog]);

  const finish = async (onboarding) => {
    setBusy(true);
    try {
      await onSave(onboarding === "skipped" ? { onboarding } : {
        professions: draft.professions, other_profession: draft.other_profession, responsibilities: draft.responsibilities,
        frequent_tasks: draft.frequent_tasks, mode: draft.mode, language: draft.language, onboarding,
      });
      onOpenChange(false);
      if (onboarding === "done") toast.success("Preferências guardadas. Pode alterá-las a qualquer momento em Preferências.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar. Tente novamente.");
    } finally { setBusy(false); }
  };

  const askSuggestion = async () => {
    if (describe.trim().length < 2) return;
    try { const { data } = await api.post("/me/work-profile/suggest", { text: describe }); setSuggested(data.suggestions || []); } catch { setSuggested([]); }
  };

  const professionTasks = (catalog?.profession_tasks || {});
  const relevantTasks = (() => {
    const keys = new Set((draft?.professions || []).flatMap(p => professionTasks[p] || []));
    const all = catalog?.tasks || [];
    const first = all.filter(t => keys.has(t.key));
    return [...first, ...all.filter(t => !keys.has(t.key))];
  })();

  const steps = ["Em que trabalhas?", "O que precisas de fazer com mais frequência?", "Preferes ajuda passo a passo ou acesso direto?"];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-xl" data-testid="work-profile-onboarding">
        <DialogHeader>
          <p className="text-xs font-semibold uppercase tracking-wide text-primary">Passo {step + 1} de 3</p>
          <DialogTitle className="text-xl">{steps[step]}</DialogTitle>
          <DialogDescription>
            {step === 0 && "Escolha uma ou mais opções. Serve só para sugerir ferramentas — não altera as suas permissões nem o seu plano."}
            {step === 1 && "As tarefas escolhidas aparecem primeiro no seu painel. Todas as outras continuam acessíveis."}
            {step === 2 && "Pode mudar a qualquer momento, sem perder o trabalho feito."}
          </DialogDescription>
        </DialogHeader>

        {!catalog ? <div className="grid place-items-center py-10"><Loader2 className="h-6 w-6 animate-spin" /></div> : <>
          {step === 0 && <div className="space-y-4">
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {catalog.professions.map(p => <Chip key={p.key} testid={`profession-${p.key}`} active={draft.professions.includes(p.key)}
                onClick={() => setDraft(d => ({ ...d, professions: toggle(d.professions, p.key) }))}>{p.label}</Chip>)}
            </div>
            {draft.professions.includes("outra") && <label className="block text-sm">Qual?
              <input className="mt-1 w-full rounded-lg border bg-background px-3 py-2" maxLength={120} value={draft.other_profession || ""}
                onChange={e => setDraft(d => ({ ...d, other_profession: e.target.value }))} data-testid="other-profession" /></label>}
            <div className="rounded-xl border border-dashed p-3">
              <label className="block text-sm font-medium" htmlFor="wp-describe">Ou descreva a sua atividade e sugerimos</label>
              <div className="mt-2 flex gap-2">
                <input id="wp-describe" className="min-w-0 flex-1 rounded-lg border bg-background px-3 py-2 text-sm" placeholder="Ex.: faço pinturas e pequenas reparações em casas"
                  value={describe} onChange={e => setDescribe(e.target.value)} />
                <Button type="button" variant="outline" onClick={askSuggestion} data-testid="profession-suggest"><Sparkles className="mr-1 h-4 w-4" />Sugerir</Button>
              </div>
              {suggested.length > 0 && <div className="mt-2 flex flex-wrap items-center gap-2 text-sm">
                <span>Sugestão:</span>{suggested.map(s => <span key={s.key} className="rounded-full bg-muted px-2 py-1">{s.label}</span>)}
                <Button size="sm" type="button" onClick={() => { setDraft(d => ({ ...d, professions: [...new Set([...d.professions, ...suggested.map(s => s.key)])] })); setSuggested([]); }}
                  data-testid="profession-suggest-confirm">Confirmar</Button>
              </div>}
            </div>
            <details className="text-sm"><summary className="cursor-pointer font-medium">A sua função na empresa (opcional)</summary>
              <div className="mt-2 flex flex-wrap gap-2">{catalog.responsibilities.map(r => <Chip key={r.key} active={draft.responsibilities.includes(r.key)}
                onClick={() => setDraft(d => ({ ...d, responsibilities: toggle(d.responsibilities, r.key) }))}>{r.label}</Chip>)}</div>
            </details>
          </div>}

          {step === 1 && <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            {relevantTasks.map(t => <Chip key={t.key} testid={`task-${t.key}`} active={draft.frequent_tasks.includes(t.key)}
              onClick={() => setDraft(d => ({ ...d, frequent_tasks: toggle(d.frequent_tasks, t.key).slice(0, 8) }))}>{t.label}</Chip>)}
          </div>}

          {step === 2 && <div className="space-y-4">
            <div className="grid gap-2">{MODES.map(m => <Chip key={m.key} testid={`mode-${m.key}`} active={draft.mode === m.key} onClick={() => setDraft(d => ({ ...d, mode: m.key }))}>
              <strong>{m.label}</strong><span className="block text-xs text-muted-foreground">{m.hint}</span></Chip>)}</div>
            <div><p className="mb-2 text-sm font-medium">Linguagem</p><div className="grid grid-cols-2 gap-2">
              <Chip testid="language-simples" active={draft.language === "simples"} onClick={() => setDraft(d => ({ ...d, language: "simples" }))}>Corrente<span className="block text-xs text-muted-foreground">«Preço por unidade, sem IVA»</span></Chip>
              <Chip testid="language-tecnica" active={draft.language === "tecnica"} onClick={() => setDraft(d => ({ ...d, language: "tecnica" }))}>Técnica<span className="block text-xs text-muted-foreground">«P.U. s/ IVA»</span></Chip>
            </div></div>
          </div>}
        </>}

        <div className="mt-2 flex flex-wrap items-center justify-between gap-2 border-t pt-4">
          <Button type="button" variant="ghost" onClick={() => finish("skipped")} disabled={busy} data-testid="onboarding-skip">Saltar e começar</Button>
          <div className="flex gap-2">
            {step > 0 && <Button type="button" variant="outline" onClick={() => setStep(s => s - 1)}><ChevronLeft className="mr-1 h-4 w-4" />Voltar</Button>}
            {step < 2 ? <Button type="button" onClick={() => setStep(s => s + 1)} data-testid="onboarding-next">Seguinte</Button>
              : <Button type="button" onClick={() => finish("done")} disabled={busy} data-testid="onboarding-finish">{busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}Concluir</Button>}
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
