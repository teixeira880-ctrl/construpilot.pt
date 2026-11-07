import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, History, Settings2 } from "lucide-react";
import { api } from "@/lib/api";
import { MODES } from "@/lib/workProfile";
import { WorkProfileOnboarding } from "@/components/workprofile/WorkProfileOnboarding";

/** Elemento principal do painel: « O que precisas de fazer hoje? ».
 *  Só mostra tarefas que o utilizador já pode abrir (permissões + plano, calculados no servidor). */
export function TaskHome({ onProfile }) {
  const [data, setData] = useState(null);
  const [open, setOpen] = useState(false);
  const [failed, setFailed] = useState(false);

  const load = () => api.get("/me/work-profile/home").then(({ data }) => { setData(data); onProfile?.(data.profile); }).catch(() => setFailed(true));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { load(); }, []);

  const save = async (patch) => { const { data: p } = await api.put("/me/work-profile", patch); await load(); window.dispatchEvent(new CustomEvent("cp:work-profile", { detail: p })); return p; };
  const setMode = async (mode) => { try { await save({ mode }); } catch { /* o modo atual mantém-se */ } };

  if (failed) return null;
  if (!data) return <div className="surface h-40 animate-pulse p-5" aria-busy="true" data-testid="task-home-loading" />;
  const { profile, tasks, continue: cont, show_onboarding } = data;

  return (
    <section className="rounded-2xl border border-primary/25 bg-card p-4 shadow-sm sm:p-6" data-testid="task-home">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h2 className="text-xl font-bold sm:text-2xl">O que precisas de fazer hoje?</h2>
        <div className="flex items-center gap-1 rounded-xl bg-muted p-1" role="radiogroup" aria-label="Modo de utilização" data-testid="mode-switch">
          {MODES.map(m => <button key={m.key} type="button" role="radio" aria-checked={profile.mode === m.key} title={m.hint}
            onClick={() => setMode(m.key)} data-testid={`mode-switch-${m.key}`}
            className={`min-h-9 rounded-lg px-3 text-sm ${profile.mode === m.key ? "bg-background font-semibold text-primary shadow-sm" : "text-muted-foreground"}`}>{m.label}</button>)}
        </div>
      </div>

      {show_onboarding && <div className="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-primary/10 p-3 text-sm" data-testid="onboarding-invite">
        <span>Diga-nos em que trabalha e mostramos primeiro as ferramentas certas (3 perguntas, opcional).</span>
        <span className="flex gap-2">
          <button type="button" className="rounded-lg bg-primary px-3 py-2 font-semibold text-primary-foreground" onClick={() => setOpen(true)} data-testid="onboarding-open">Personalizar</button>
          <button type="button" className="rounded-lg px-3 py-2" onClick={() => save({ onboarding: "skipped" })} data-testid="onboarding-dismiss">Agora não</button>
        </span>
      </div>}

      {cont?.length > 0 && <div className="mt-4 space-y-2" data-testid="continue-list">
        {cont.map(c => <Link key={c.url} to={c.url} className="flex min-h-12 items-center gap-3 rounded-xl border bg-background px-3 py-2 hover:border-primary">
          <History className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" /><span className="flex-1"><small className="block text-xs text-muted-foreground">Continuar onde fiquei</small>{c.label}</span><ArrowRight className="h-4 w-4" />
        </Link>)}
      </div>}

      <div className="mt-4 grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3" data-testid="task-list">
        {tasks.map(t => <Link key={t.key} to={t.url} data-testid={`home-task-${t.key}`}
          className="flex min-h-14 items-center justify-between gap-2 rounded-xl border bg-background px-4 py-3 font-medium hover:border-primary hover:bg-primary/5">
          <span>{t.label}</span><ArrowRight className="h-4 w-4 shrink-0 text-primary" /></Link>)}
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm text-muted-foreground">
        <span>Todas as outras ferramentas estão no menu e na pesquisa.</span>
        <button type="button" onClick={() => setOpen(true)} className="inline-flex items-center gap-1 underline-offset-2 hover:underline" data-testid="work-profile-edit">
          <Settings2 className="h-4 w-4" />Alterar o meu perfil</button>
      </div>
      <WorkProfileOnboarding open={open} onOpenChange={setOpen} profile={profile} onSave={save} />
    </section>
  );
}
