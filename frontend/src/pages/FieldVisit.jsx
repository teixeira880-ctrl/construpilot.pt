import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Camera, CheckCircle2, Loader2, Plus, Save, Trash2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { compressImage } from "@/lib/imageCompress";

const SOURCES = [["medido", "Medido"], ["planta", "Da planta"], ["estimado", "Estimado"]];
const SECTIONS = [
  ["access", "Acessos", "Estacionamento, elevador, chaves, horários permitidos"],
  ["demolitions", "Demolições e remoções", "O que é preciso retirar ou demolir"],
  ["protections", "Proteção de espaços", "Móveis, pavimentos, zonas onde a família continua a viver"],
  ["notes", "Notas", "Tudo o resto"],
];
const EMPTY = { title: "", address: "", client_name: "", visit_date: new Date().toISOString().slice(0, 10), access: "", demolitions: "", protections: "", notes: "", measures: [], questions: [], photos: [], summary: "" };
const DRAFT = "cp_field_visit_draft_v1";

const toDataUrl = file => new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(file); });
const toForm = v => ({ ...EMPTY, ...v, measures: (v.measures || []).map(m => ({ ...m, value: m.value ?? "" })), summary: v.summary || "" });

export default function FieldVisit() {
  const [params, setParams] = useSearchParams();
  const visitId = params.get("id");
  const [list, setList] = useState([]);
  const [form, setForm] = useState(() => { try { return JSON.parse(localStorage.getItem(DRAFT)) || EMPTY; } catch { return EMPTY; } });
  const [saved, setSaved] = useState(null);
  const [saving, setSaving] = useState(false);
  const [question, setQuestion] = useState("");

  const loadList = () => api.get("/field/visits").then(({ data }) => setList(Array.isArray(data) ? data : [])).catch(() => {});
  useEffect(() => { loadList(); }, []);
  useEffect(() => {
    if (!visitId) return;
    api.get(`/field/visits/${visitId}`).then(({ data }) => { setForm(toForm(data)); setSaved(data); }).catch(() => toast.error("Visita não encontrada"));
  }, [visitId]);
  useEffect(() => { if (!visitId) try { localStorage.setItem(DRAFT, JSON.stringify(form)); } catch { /* sem armazenamento */ } }, [form, visitId]);

  const set = patch => setForm(f => ({ ...f, ...patch }));
  const setMeasure = (i, patch) => set({ measures: form.measures.map((m, k) => (k === i ? { ...m, ...patch } : m)) });

  const addPhotos = async (files) => {
    const urls = [];
    for (const f of Array.from(files || []).slice(0, 12)) {
      try { urls.push(await toDataUrl(await compressImage(f))); } catch { toast.error(`Fotografia ${f.name} inválida`); }
    }
    set({ photos: [...form.photos, ...urls].slice(0, 24) });
  };

  const save = async () => {
    setSaving(true);
    try {
      const body = { ...form, summary: saved && form.summary !== saved.summary ? form.summary : (saved?.summary_edited ? form.summary : null) };
      const { data } = visitId ? await api.put(`/field/visits/${visitId}`, body) : await api.post("/field/visits", body);
      setSaved(data); setForm(toForm(data));
      if (!visitId) { localStorage.removeItem(DRAFT); setParams({ id: data.visit_id }); }
      loadList();
      toast.success("Visita guardada");
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar. Os dados continuam aqui."); }
    finally { setSaving(false); }
  };

  const photoSrc = p => (p.startsWith("data:") ? p : `${process.env.REACT_APP_BACKEND_URL}/api/field/file?path=${encodeURIComponent(p)}`);

  return (
    <div className="mx-auto max-w-3xl space-y-4 pb-24" data-testid="field-visit">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <div><p className="text-xs font-semibold uppercase tracking-wide text-primary">Visita à obra</p>
          <h1 className="text-2xl font-bold">{form.title || "Nova visita"}</h1></div>
        {visitId && <Button variant="outline" onClick={() => { setParams({}); setForm(EMPTY); setSaved(null); }}><Plus className="mr-1 h-4 w-4" />Nova visita</Button>}
      </div>

      <section className="grid gap-3 rounded-2xl border bg-card p-4 sm:grid-cols-2">
        {[["title", "Título", "Moradia do Sr. Manuel"], ["client_name", "Cliente", "Manuel Silva"], ["address", "Morada da obra", "Rua das Flores 12, Lisboa"]].map(([k, l, ph]) =>
          <label key={k} className="block text-sm font-medium">{l}<input className="mt-1 h-11 w-full rounded-xl border bg-background px-3" placeholder={ph} value={form[k]} onChange={e => set({ [k]: e.target.value })} data-testid={`visit-${k}`} /></label>)}
        <label className="block text-sm font-medium">Data<input type="date" className="mt-1 h-11 w-full rounded-xl border bg-background px-3" value={form.visit_date} onChange={e => set({ visit_date: e.target.value })} /></label>
      </section>

      <section className="space-y-3 rounded-2xl border bg-card p-4">
        <h2 className="font-semibold">Fotografias</h2>
        <div className="flex flex-wrap gap-2">
          {form.photos.map((p, i) => <div key={i} className="relative"><img src={photoSrc(p)} alt="" className="h-20 w-20 rounded-lg object-cover" />
            <button type="button" aria-label="Remover fotografia" className="absolute -right-1 -top-1 rounded-full bg-background p-1 shadow" onClick={() => set({ photos: form.photos.filter((_, k) => k !== i) })}><Trash2 className="h-3 w-3" /></button></div>)}
          <label className="grid h-20 w-20 cursor-pointer place-items-center rounded-lg border border-dashed text-xs text-muted-foreground"><Camera className="h-5 w-5" />Adicionar
            <input type="file" accept="image/*" capture="environment" multiple className="hidden" onChange={e => addPhotos(e.target.files)} data-testid="visit-photos" /></label>
        </div>
        <p className="text-xs text-muted-foreground">Uma fotografia sem medida de referência não dá medidas exatas: registe as medidas abaixo.</p>
      </section>

      <section className="space-y-3 rounded-2xl border bg-card p-4">
        <h2 className="font-semibold">Medidas</h2>
        {form.measures.map((m, i) => <div key={i} className="grid grid-cols-2 gap-2 rounded-xl border p-2 sm:grid-cols-[2fr_1fr_70px_1fr_auto]">
          <input aria-label="O quê" className="col-span-2 h-11 rounded-lg border bg-background px-2 sm:col-span-1" placeholder="Ex.: Sala — comprimento" value={m.label} onChange={e => setMeasure(i, { label: e.target.value })} data-testid={`visit-measure-${i}-label`} />
          <input aria-label="Valor" type="number" inputMode="decimal" min="0" step="any" className="h-11 rounded-lg border bg-background px-2" placeholder="por medir" value={m.value} onChange={e => setMeasure(i, { value: e.target.value })} data-testid={`visit-measure-${i}-value`} />
          <input aria-label="Unidade" className="h-11 rounded-lg border bg-background px-2" value={m.unit || "m"} onChange={e => setMeasure(i, { unit: e.target.value })} />
          <select aria-label="Origem" className="h-11 rounded-lg border bg-background px-2" value={m.source || "medido"} onChange={e => setMeasure(i, { source: e.target.value })}>{SOURCES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
          <Button variant="ghost" size="icon" aria-label="Remover medida" onClick={() => set({ measures: form.measures.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></Button>
        </div>)}
        <Button variant="outline" onClick={() => set({ measures: [...form.measures, { label: "", value: "", unit: "m", source: "medido" }] })} data-testid="visit-add-measure"><Plus className="mr-1 h-4 w-4" />Medida</Button>
      </section>

      <section className="grid gap-3 rounded-2xl border bg-card p-4">
        {SECTIONS.map(([k, l, ph]) => <label key={k} className="block text-sm font-medium">{l}<textarea rows={2} className="mt-1 w-full rounded-xl border bg-background p-2" placeholder={ph} value={form[k]} onChange={e => set({ [k]: e.target.value })} data-testid={`visit-${k}`} /></label>)}
      </section>

      <section className="space-y-2 rounded-2xl border bg-card p-4">
        <h2 className="font-semibold">Perguntas pendentes</h2>
        {form.questions.map((q, i) => <label key={i} className="flex min-h-11 items-center gap-2 text-sm">
          <input type="checkbox" className="h-5 w-5" checked={!!q.answered} onChange={e => set({ questions: form.questions.map((x, k) => k === i ? { ...x, answered: e.target.checked } : x) })} />
          <span className={q.answered ? "line-through text-muted-foreground" : ""}>{q.text}</span>
          <button type="button" aria-label="Remover pergunta" className="ml-auto" onClick={() => set({ questions: form.questions.filter((_, k) => k !== i) })}><Trash2 className="h-4 w-4" /></button></label>)}
        <div className="flex gap-2"><input className="h-11 min-w-0 flex-1 rounded-xl border bg-background px-3" placeholder="Ex.: Que cor quer o cliente na sala?" value={question} onChange={e => setQuestion(e.target.value)} data-testid="visit-question" />
          <Button variant="outline" onClick={() => { if (question.trim()) { set({ questions: [...form.questions, { text: question.trim(), answered: false }] }); setQuestion(""); } }} data-testid="visit-add-question">Adicionar</Button></div>
      </section>

      {saved && <section className="space-y-3 rounded-2xl border border-primary/30 bg-card p-4" data-testid="visit-summary">
        <h2 className="font-semibold">Resumo (editável)</h2>
        <textarea rows={8} className="w-full rounded-xl border bg-background p-2 font-mono text-sm" value={form.summary} onChange={e => set({ summary: e.target.value })} data-testid="visit-summary-text" />
        {saved.to_confirm?.length ? <div className="rounded-xl bg-amber-500/10 p-3 text-sm" data-testid="visit-to-confirm"><p className="flex items-center gap-1 font-semibold"><TriangleAlert className="h-4 w-4" />Falta confirmar</p>
          <ul className="list-disc pl-5">{saved.to_confirm.map(x => <li key={x}>{x}</li>)}</ul></div>
          : <p className="flex items-center gap-1 text-sm text-primary"><CheckCircle2 className="h-4 w-4" />Nada pendente.</p>}
      </section>}

      <div className="sticky bottom-2 z-10 flex justify-end rounded-2xl border bg-background/95 p-2 shadow-lg backdrop-blur">
        <Button className="min-h-12" onClick={save} disabled={saving} data-testid="visit-save">{saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Save className="mr-1 h-4 w-4" />}Guardar e gerar resumo</Button>
      </div>

      {list.length > 0 && <section className="space-y-2" data-testid="visit-list"><h2 className="font-semibold">Visitas anteriores</h2>
        {list.map(v => <button key={v.visit_id} type="button" onClick={() => setParams({ id: v.visit_id })}
          className={`flex min-h-12 w-full items-center justify-between rounded-xl border px-3 text-left text-sm ${v.visit_id === visitId ? "border-primary" : ""}`}>
          <span>{v.title}{v.address ? ` — ${v.address}` : ""}</span><span className="text-xs text-muted-foreground">{v.to_confirm?.length ? `${v.to_confirm.length} por confirmar` : "completa"}</span></button>)}
      </section>}
    </div>
  );
}
