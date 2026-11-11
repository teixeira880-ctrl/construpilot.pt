import { useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Loader2, Mic, Plus, Trash2, TriangleAlert, Wand2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { newRequestId } from "@/lib/workProfile";
import { currentUiLocale } from "@/lib/uiLang";

const today = () => new Date().toISOString().slice(0, 10);

/** Registo diário: o texto livre é transformado numa PROPOSTA; só é guardado após confirmação. */
export default function DailyLog() {
  const [text, setText] = useState("");
  const [proposal, setProposal] = useState(null);
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [logs, setLogs] = useState([]);
  const [requestId, setRequestId] = useState(newRequestId());

  const load = () => api.get("/field/daily").then(({ data }) => setLogs(Array.isArray(data) ? data : [])).catch(() => {});
  useEffect(() => { load(); }, []);

  const dictate = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast.info("O ditado por voz não está disponível neste navegador."); return; }
    const rec = new SR(); rec.lang = currentUiLocale();
    rec.onresult = e => setText(t => `${t} ${e.results[0][0].transcript}`.trim());
    rec.onend = () => setListening(false); setListening(true); rec.start();
  };

  const interpret = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/field/daily/parse", { text });
      setProposal({ ...data, date: today(), workers: data.workers ?? "", hours: data.hours ?? "", notes: "",
        missing_materials: data.missing_materials.map(m => ({ item: m.item, quantity: "" })) });
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível interpretar. Preencha à mão."); setProposal(manual()); }
    finally { setBusy(false); }
  };
  const manual = () => ({ date: today(), workers: "", hours: "", work_done: [""], missing_materials: [], blockers: [], ambiguous: [], notes: "", source_text: text });

  const confirm = async () => {
    setBusy(true);
    try {
      const body = { ...proposal, request_id: requestId, confirmed: true, workers: proposal.workers === "" ? null : Number(proposal.workers),
        hours: proposal.hours === "" ? null : Number(proposal.hours), work_done: proposal.work_done.filter(Boolean),
        missing_materials: proposal.missing_materials.filter(m => m.item), source_text: text };
      await api.post("/field/daily", body);
      toast.success("Registo guardado");
      setProposal(null); setText(""); setRequestId(newRequestId()); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar. Os dados continuam aqui."); }
    finally { setBusy(false); }
  };

  const P = proposal;
  const setP = patch => setProposal(p => ({ ...p, ...patch }));
  const listEditor = (key, placeholder) => <div className="space-y-2">
    {P[key].map((v, i) => <div key={i} className="flex gap-2"><input className="h-11 min-w-0 flex-1 rounded-xl border bg-background px-3" value={v} placeholder={placeholder}
      onChange={e => setP({ [key]: P[key].map((x, k) => k === i ? e.target.value : x) })} data-testid={`daily-${key}-${i}`} />
      <Button variant="ghost" size="icon" aria-label="Remover" onClick={() => setP({ [key]: P[key].filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></Button></div>)}
    <Button variant="outline" size="sm" onClick={() => setP({ [key]: [...P[key], ""] })}><Plus className="mr-1 h-4 w-4" />Adicionar</Button>
  </div>;

  return (
    <div className="mx-auto max-w-2xl space-y-4 pb-16" data-testid="daily-log">
      <div><p className="text-xs font-semibold uppercase tracking-wide text-primary">Registo diário</p><h1 className="text-2xl font-bold">Como correu o dia?</h1>
        <p className="text-sm text-muted-foreground">Escreva ou dite como falaria a um colega. Preparamos o registo e confirma antes de guardar.</p></div>

      {!P && <section className="space-y-3 rounded-2xl border bg-card p-4">
        <textarea rows={4} className="w-full rounded-xl border bg-background p-3 text-base" maxLength={3000} placeholder="Ex.: Hoje fomos dois, colocámos o chão da cozinha e faltou cola."
          value={text} onChange={e => setText(e.target.value)} data-testid="daily-text" />
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={dictate} disabled={listening}><Mic className="mr-1 h-4 w-4" />{listening ? "A ouvir…" : "Ditar"}</Button>
          <Button onClick={interpret} disabled={busy || !text.trim()} data-testid="daily-interpret">{busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Wand2 className="mr-1 h-4 w-4" />}Preparar registo</Button>
          <Button variant="ghost" onClick={() => setProposal(manual())}>Preencher à mão</Button>
        </div>
      </section>}

      {P && <section className="space-y-4 rounded-2xl border border-primary/30 bg-card p-4" data-testid="daily-proposal">
        <h2 className="font-semibold">Confirme o registo</h2>
        {P.ambiguous?.length > 0 && <div className="rounded-xl bg-amber-500/10 p-3 text-sm" data-testid="daily-ambiguous"><p className="flex items-center gap-1 font-semibold"><TriangleAlert className="h-4 w-4" />A verificar</p>
          <ul className="list-disc pl-5">{P.ambiguous.map(a => <li key={a}>{a}</li>)}</ul></div>}
        <div className="grid grid-cols-3 gap-2">
          <label className="text-sm font-medium">Data<input type="date" className="mt-1 h-11 w-full rounded-xl border bg-background px-2" value={P.date} onChange={e => setP({ date: e.target.value })} /></label>
          <label className="text-sm font-medium">Pessoas<input type="number" min="0" inputMode="numeric" className="mt-1 h-11 w-full rounded-xl border bg-background px-2" placeholder="?" value={P.workers} onChange={e => setP({ workers: e.target.value })} data-testid="daily-workers" /></label>
          <label className="text-sm font-medium">Horas<input type="number" min="0" max="24" step="0.5" inputMode="decimal" className="mt-1 h-11 w-full rounded-xl border bg-background px-2" placeholder="não indicado" value={P.hours} onChange={e => setP({ hours: e.target.value })} data-testid="daily-hours" /></label>
        </div>
        <div><p className="mb-1 text-sm font-medium">Trabalhos feitos</p>{listEditor("work_done", "Ex.: chão da cozinha")}</div>
        <div><p className="mb-1 text-sm font-medium">Materiais em falta</p>
          {P.missing_materials.map((m, i) => <div key={i} className="mb-2 grid grid-cols-[2fr_1fr_auto] gap-2">
            <input className="h-11 rounded-xl border bg-background px-3" value={m.item} onChange={e => setP({ missing_materials: P.missing_materials.map((x, k) => k === i ? { ...x, item: e.target.value } : x) })} data-testid={`daily-material-${i}`} />
            <input className="h-11 rounded-xl border bg-background px-3" placeholder="quantidade?" value={m.quantity} onChange={e => setP({ missing_materials: P.missing_materials.map((x, k) => k === i ? { ...x, quantity: e.target.value } : x) })} />
            <Button variant="ghost" size="icon" aria-label="Remover" onClick={() => setP({ missing_materials: P.missing_materials.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></Button></div>)}
          <Button variant="outline" size="sm" onClick={() => setP({ missing_materials: [...P.missing_materials, { item: "", quantity: "" }] })}><Plus className="mr-1 h-4 w-4" />Material</Button></div>
        <div><p className="mb-1 text-sm font-medium">Bloqueios</p>{listEditor("blockers", "Ex.: à espera do canalizador")}</div>
        <label className="block text-sm font-medium">Notas<textarea rows={2} className="mt-1 w-full rounded-xl border bg-background p-2" value={P.notes} onChange={e => setP({ notes: e.target.value })} /></label>
        <div className="flex flex-wrap justify-between gap-2">
          <Button variant="ghost" onClick={() => setProposal(null)}>Voltar ao texto</Button>
          <Button className="min-h-12" onClick={confirm} disabled={busy} data-testid="daily-confirm">{busy ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1 h-4 w-4" />}Confirmar e guardar</Button>
        </div>
      </section>}

      {logs.length > 0 && <section className="space-y-2" data-testid="daily-history"><h2 className="font-semibold">Registos anteriores</h2>
        {logs.slice(0, 30).map(l => <article key={l.log_id} className="rounded-xl border bg-card p-3 text-sm">
          <p className="font-medium">{l.date || l.created_at?.slice(0, 10)} · {l.workers != null ? `${l.workers} pessoa(s)` : "equipa não indicada"}{l.hours != null ? ` · ${l.hours} h` : ""}</p>
          {l.work_done?.length > 0 && <p>Feito: {l.work_done.join("; ")}</p>}
          {l.missing_materials?.length > 0 && <p className="text-amber-700 dark:text-amber-400">Em falta: {l.missing_materials.map(m => m.item + (m.quantity ? ` (${m.quantity})` : "")).join(", ")}</p>}
          {l.blockers?.length > 0 && <p>Bloqueios: {l.blockers.join("; ")}</p>}
        </article>)}
      </section>}
    </div>
  );
}
