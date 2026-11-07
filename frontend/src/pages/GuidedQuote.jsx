import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, ArrowRight, CheckCircle2, CircleHelp, FileText, Loader2, Mic, Plus, Trash2, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api, eur2 } from "@/lib/api";
import { MODES, fmt, newRequestId, term, useWorkProfile } from "@/lib/workProfile";

const DRAFT_KEY = "cp_guided_quote_draft_v1";
const EMPTY_ROOM = () => ({ name: "", length_m: "", width_m: "", height_m: "", openings: [], paint_ceiling: false });
const EMPTY = () => ({
  description: "", client_id: "", client_name: "", address: "",
  works: { prep: true, walls: true, ceiling: false, cracks: false, supply_paint: true },
  rooms: [EMPTY_ROOM()], crack_repair_ml: "", coats: "", yield_m2_per_l: "", can_size_l: "",
  prices: { labor_per_m2: "", prep_per_m2: "", crack_per_ml: "", paint_per_can: "", paint_per_l: "" },
});
const NAO_SEI = "nao_sei";

function loadDraft() {
  try { const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null"); if (d?.job) return d; } catch { /* rascunho ilegível */ }
  return null;
}

// ---------------------------------------------------------------- campos
function Help({ help }) {
  if (!help) return null;
  return <dl className="mt-3 grid gap-1 rounded-xl bg-muted/60 p-3 text-sm" data-testid="field-help">
    {help.what && <div><dt className="inline font-semibold">O que introduzir: </dt><dd className="inline">{help.what}</dd></div>}
    {help.example && <div><dt className="inline font-semibold">Exemplo: </dt><dd className="inline">{help.example}</dd></div>}
    {help.unit && <div><dt className="inline font-semibold">Unidade: </dt><dd className="inline">{help.unit}</dd></div>}
    {help.where && <div><dt className="inline font-semibold">Onde encontrar: </dt><dd className="inline">{help.where}</dd></div>}
    {help.effect && <div><dt className="inline font-semibold">Efeito no resultado: </dt><dd className="inline">{help.effect}</dd></div>}
  </dl>;
}

function NumberField({ label, value, onChange, unit, testid, suggestion, guided }) {
  const unknown = value === NAO_SEI;
  return <div className="space-y-2">
    <label className="block text-sm font-medium">{label}
      <div className="mt-1 flex items-center gap-2">
        <input type="number" inputMode="decimal" min="0" step="any" className="h-12 w-full min-w-0 rounded-xl border bg-background px-3 text-lg"
          value={unknown ? "" : value} placeholder={unknown ? "Por confirmar" : ""} onChange={e => onChange(e.target.value)} data-testid={testid} />
        {unit && <span className="shrink-0 text-sm text-muted-foreground">{unit}</span>}
      </div>
    </label>
    <div className="flex flex-wrap gap-2">
      {guided && <button type="button" onClick={() => onChange(NAO_SEI)} data-testid={`${testid}-unknown`}
        className={`min-h-10 rounded-lg border px-3 text-sm ${unknown ? "border-amber-500 bg-amber-500/10" : ""}`}>Não sei</button>}
      {suggestion && <button type="button" onClick={() => onChange(String(suggestion.value))} className="min-h-10 rounded-lg border border-dashed px-3 text-sm" data-testid={`${testid}-suggestion`}>
        Usar {fmt(suggestion.value)} {unit} (sugestão a confirmar)</button>}
    </div>
    {unknown && <p className="text-xs text-amber-700 dark:text-amber-400">Fica pendente: o resultado que depende deste valor não será calculado.</p>}
  </div>;
}

// ---------------------------------------------------------------- perguntas
function buildQuestions(job, language) {
  const q = [];
  q.push({ id: "describe", section: "Pedido", title: "Descreva o trabalho", help: { what: "Por palavras suas: o que o cliente pediu.", example: "O senhor Manuel quer pintar uma sala e dois quartos. Tenho de comprar a tinta e reparar fissuras." } });
  q.push({ id: "client", section: "Cliente e local", title: "Para quem é o orçamento?" });
  q.push({ id: "address", section: "Cliente e local", title: "Onde é a obra?", help: { what: "Morada da obra (pode ser diferente da do cliente).", example: "Rua das Flores 12, 2.º Esq., Lisboa" } });
  q.push({ id: "works", section: "Trabalhos", title: "Que trabalhos vai fazer?" });
  job.rooms.forEach((r, i) => {
    const n = r.name || `Divisão ${i + 1}`;
    q.push({ id: `room-${i}-name`, section: "Divisões", title: `Nome da divisão ${i + 1}`, room: i, help: { example: "Sala, Quarto 1, Corredor" } });
    q.push({ id: `room-${i}-dims`, section: "Divisões", title: `${n}: medidas do chão`, room: i,
      help: { what: "Comprimento e largura do chão.", example: "5 m × 4 m", unit: "metros", where: "Fita métrica ou medidor laser, de parede a parede; ou numa planta cotada.", effect: "Determina o perímetro das paredes e a área do teto." } });
    q.push({ id: `room-${i}-height`, section: "Divisões", title: `${n}: ${term("ceiling_height", language).toLowerCase()}`, room: i,
      help: { what: "Altura do chão ao teto.", example: "2,60 m", unit: "metros", where: "Meça num canto da divisão.", effect: "Multiplicado pelo perímetro dá a área das paredes." } });
    q.push({ id: `room-${i}-openings`, section: "Divisões", title: `${n}: ${term("openings", language).toLowerCase()}`, room: i,
      help: { what: "Portas, janelas e outros vãos que não serão pintados.", example: "Porta 0,90 × 2,10 m; janela 1,50 × 1,20 m", unit: "metros", effect: "A área destas aberturas é retirada das paredes." } });
    if (i === job.rooms.length - 1) q.push({ id: "room-add", section: "Divisões", title: "Há mais divisões?" });
  });
  if (job.works.cracks) q.push({ id: "cracks", section: "Trabalhos", title: "Quantos metros de fissuras há a reparar?", help: { what: "Comprimento total aproximado das fissuras.", unit: "metros lineares (ml)", where: "Meça cada fissura e some.", effect: "Quantidade da linha de reparação de fissuras." } });
  if (job.works.walls || job.works.ceiling) {
    q.push({ id: "coats", section: "Tinta", title: term("coats", language), help: { what: "Número de camadas de tinta.", example: "2", where: "Depende do estado da parede e da cor; a ficha técnica do produto indica o recomendado.", effect: "A quantidade de tinta é proporcional ao número de demãos." } });
    q.push({ id: "yield", section: "Tinta", title: term("yield", language), help: { what: "Quantos metros quadrados cobre 1 litro numa demão.", example: "10 m²/L", unit: "m²/L", where: "Ficha técnica ou rótulo da lata.", effect: "Quanto maior o rendimento, menos litros são necessários." } });
    if (job.works.supply_paint) q.push({ id: "can", section: "Tinta", title: "Tamanho da lata que vai comprar", help: { example: "15 L", unit: "litros", effect: "Converte os litros em número de latas a orçamentar." } });
  }
  q.push({ id: "prices", section: "Preços", title: "Os seus preços", help: { what: "Os preços que pratica, sem IVA. Os valores ficam visíveis e editáveis no orçamento.", effect: "Preço × quantidade = total de cada linha. Um preço em branco fica marcado «por confirmar»." } });
  q.push({ id: "review", section: "Revisão", title: "Reveja o orçamento" });
  return q;
}

function toPayload(job, requestId) {
  const clean = v => (v === "" ? null : v);
  return {
    request_id: requestId, description: job.description, client_id: job.client_id || null, client_name: job.client_name, address: job.address,
    job: {
      rooms: job.rooms.map(r => ({ name: r.name || undefined, length_m: clean(r.length_m), width_m: clean(r.width_m), height_m: clean(r.height_m),
        openings: r.openings.map(o => ({ width_m: clean(o.width_m), height_m: clean(o.height_m), count: o.count || 1 })),
        paint_walls: job.works.walls, paint_ceiling: job.works.ceiling })),
      coats: clean(job.coats), yield_m2_per_l: clean(job.yield_m2_per_l), can_size_l: clean(job.can_size_l),
      crack_repair: job.works.cracks, crack_repair_ml: clean(job.crack_repair_ml), surface_prep: job.works.prep, supply_paint: job.works.supply_paint,
      prices: Object.fromEntries(Object.entries(job.prices).map(([k, v]) => [k, clean(v)])),
    },
  };
}

// ---------------------------------------------------------------- página
export default function GuidedQuote() {
  const nav = useNavigate();
  const { profile, save: saveProfile } = useWorkProfile();
  const restored = useRef(loadDraft());
  const [job, setJob] = useState(restored.current?.job || EMPTY());
  const [idx, setIdx] = useState(restored.current?.idx || 0);
  const [requestId, setRequestId] = useState(restored.current?.request_id || newRequestId());
  const [showHelp, setShowHelp] = useState(false);
  const [clients, setClients] = useState([]);
  const [preview, setPreview] = useState(null);
  const [previewError, setPreviewError] = useState("");
  const [saving, setSaving] = useState(false);
  const [listening, setListening] = useState(false);
  const mode = profile.mode || "guiado";
  const guided = mode === "guiado";
  const language = profile.language || "simples";

  const questions = useMemo(() => buildQuestions(job, language), [job, language]);
  const sections = useMemo(() => [...new Set(questions.map(q => q.section))], [questions]);
  // Guiado: uma pergunta por ecrã. Direto/avançado: uma secção por ecrã. Mesmo objeto `job` nos dois casos.
  const pages = useMemo(() => guided ? questions.map(q => [q]) : sections.map(s => questions.filter(q => q.section === s)), [guided, questions, sections]);
  const page = Math.min(idx, pages.length - 1);
  const current = pages[page];
  const isReview = current.some(q => q.id === "review");

  useEffect(() => { api.get("/clients").then(({ data }) => setClients(data.clients || data || [])).catch(() => {}); }, []);
  useEffect(() => { try { localStorage.setItem(DRAFT_KEY, JSON.stringify({ job, idx: page, request_id: requestId })); } catch { /* armazenamento indisponível */ } }, [job, page, requestId]);
  useEffect(() => { window.scrollTo?.({ top: 0, behavior: "smooth" }); setShowHelp(false); }, [page]);
  // Mudar de modo mantém a pergunta atual visível.
  const switchMode = async (m) => {
    const qid = current[0]?.id;
    await saveProfile({ mode: m }).catch(() => {});
    const nextPages = m === "guiado" ? questions.map(q => [q]) : sections.map(s => questions.filter(q => q.section === s));
    setIdx(Math.max(0, nextPages.findIndex(p => p.some(q => q.id === qid))));
  };

  useEffect(() => {
    if (!isReview) return;
    setPreview(null); setPreviewError("");
    api.post("/guided-quote/preview", toPayload(job, requestId)).then(({ data }) => setPreview(data))
      .catch(e => setPreviewError(e?.response?.data?.detail || "Não foi possível calcular. Verifique as medidas."));
  }, [isReview, job, requestId]);

  const set = patch => setJob(j => ({ ...j, ...patch }));
  const setRoom = (i, patch) => setJob(j => ({ ...j, rooms: j.rooms.map((r, k) => (k === i ? { ...r, ...patch } : r)) }));
  const setPrice = (k, v) => setJob(j => ({ ...j, prices: { ...j.prices, [k]: v } }));

  const dictate = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast.info("O ditado por voz não está disponível neste navegador. Escreva o pedido."); return; }
    const rec = new SR(); rec.lang = "pt-PT"; rec.interimResults = false;
    rec.onresult = e => set({ description: `${job.description} ${e.results[0][0].transcript}`.trim() });
    rec.onend = () => setListening(false); setListening(true); rec.start();
  };

  const saveQuote = async () => {
    setSaving(true);
    try {
      const { data } = await api.post("/guided-quote", toPayload(job, requestId));
      localStorage.removeItem(DRAFT_KEY);
      toast.success("Orçamento guardado como rascunho. Nada foi enviado ao cliente.");
      nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar. O seu trabalho continua aqui.");
    } finally { setSaving(false); }
  };

  const restart = () => { setJob(EMPTY()); setIdx(0); setRequestId(newRequestId()); localStorage.removeItem(DRAFT_KEY); };

  const render = (q) => {
    const r = q.room != null ? job.rooms[q.room] : null;
    switch (q.id) {
      case "describe": return <div className="space-y-2">
        <textarea rows={4} className="w-full rounded-xl border bg-background p-3 text-base" value={job.description} maxLength={2000}
          placeholder="Ex.: O senhor Manuel quer pintar uma sala e dois quartos…" onChange={e => set({ description: e.target.value })} data-testid="gq-description" />
        <Button type="button" variant="outline" onClick={dictate} disabled={listening}><Mic className="mr-1 h-4 w-4" />{listening ? "A ouvir…" : "Ditar por voz"}</Button>
      </div>;
      case "client": return <div className="space-y-3">
        {clients.length > 0 && <label className="block text-sm font-medium">Cliente existente
          <select className="mt-1 h-12 w-full rounded-xl border bg-background px-3" value={job.client_id} data-testid="gq-client"
            onChange={e => { const c = clients.find(x => x.client_id === e.target.value); set({ client_id: e.target.value, client_name: c ? (c.company || `${c.first_name || ""} ${c.last_name || ""}`.trim()) : job.client_name }); }}>
            <option value="">— Escolher —</option>{clients.map(c => <option key={c.client_id} value={c.client_id}>{c.company || `${c.first_name || ""} ${c.last_name || ""}`.trim()}</option>)}
          </select></label>}
        <label className="block text-sm font-medium">{clients.length ? "Ou nome do cliente" : "Nome do cliente"}
          <input className="mt-1 h-12 w-full rounded-xl border bg-background px-3" value={job.client_name} maxLength={160} data-testid="gq-client-name"
            onChange={e => set({ client_name: e.target.value, client_id: "" })} placeholder="Manuel Silva" /></label>
        <p className="text-xs text-muted-foreground">Pode completar os dados do cliente (contactos, NIF) no orçamento antes de o enviar.</p>
      </div>;
      case "address": return <input className="h-12 w-full rounded-xl border bg-background px-3" value={job.address} maxLength={300} onChange={e => set({ address: e.target.value })} data-testid="gq-address" />;
      case "works": return <div className="grid gap-2 sm:grid-cols-2">
        {[["walls", "Pintar paredes"], ["ceiling", "Pintar tetos"], ["prep", "Preparar superfícies (limpar, lixar, betumar)"], ["cracks", "Reparar fissuras"], ["supply_paint", "Fornecer a tinta"]].map(([k, l]) =>
          <label key={k} className={`flex min-h-12 cursor-pointer items-center gap-3 rounded-xl border px-3 ${job.works[k] ? "border-primary bg-primary/10" : ""}`}>
            <input type="checkbox" className="h-5 w-5 accent-[hsl(var(--primary))]" checked={job.works[k]} onChange={e => set({ works: { ...job.works, [k]: e.target.checked } })} data-testid={`gq-work-${k}`} />{l}</label>)}
      </div>;
      case "room-add": return <div className="flex flex-wrap gap-2">
        <Button type="button" variant="outline" onClick={() => { set({ rooms: [...job.rooms, EMPTY_ROOM()] }); setIdx(i => i + 1); }} data-testid="gq-add-room"><Plus className="mr-1 h-4 w-4" />Adicionar outra divisão</Button>
        {job.rooms.length > 1 && <Button type="button" variant="ghost" onClick={() => set({ rooms: job.rooms.slice(0, -1) })}><Trash2 className="mr-1 h-4 w-4" />Remover a última</Button>}
        <p className="w-full text-sm text-muted-foreground">{job.rooms.length} divisão(ões): {job.rooms.map((x, i) => x.name || `Divisão ${i + 1}`).join(", ")}</p>
      </div>;
      case "cracks": return <NumberField guided={guided} label="Fissuras" unit="ml" value={job.crack_repair_ml} onChange={v => set({ crack_repair_ml: v })} testid="gq-cracks" />;
      case "coats": return <NumberField guided={guided} label={term("coats", language)} value={job.coats} onChange={v => set({ coats: v })} testid="gq-coats" suggestion={job.coats === "" || job.coats === NAO_SEI ? { value: 2 } : null} />;
      case "yield": return <NumberField guided={guided} label={term("yield", language)} unit="m²/L" value={job.yield_m2_per_l} onChange={v => set({ yield_m2_per_l: v })} testid="gq-yield" suggestion={job.yield_m2_per_l === "" || job.yield_m2_per_l === NAO_SEI ? { value: 10 } : null} />;
      case "can": return <NumberField guided={guided} label="Lata" unit="L" value={job.can_size_l} onChange={v => set({ can_size_l: v })} testid="gq-can" />;
      case "prices": return <div className="grid gap-4 sm:grid-cols-2">
        {job.works.walls || job.works.ceiling ? <NumberField guided={guided} label={`Pintura — ${term("unit_price", language)}`} unit="€/m²" value={job.prices.labor_per_m2} onChange={v => setPrice("labor_per_m2", v)} testid="gq-price-labor" /> : null}
        {job.works.prep && <NumberField guided={guided} label={`Preparação — ${term("unit_price", language)}`} unit="€/m²" value={job.prices.prep_per_m2} onChange={v => setPrice("prep_per_m2", v)} testid="gq-price-prep" />}
        {job.works.cracks && <NumberField guided={guided} label={`Fissuras — ${term("unit_price", language)}`} unit="€/ml" value={job.prices.crack_per_ml} onChange={v => setPrice("crack_per_ml", v)} testid="gq-price-cracks" />}
        {job.works.supply_paint && <NumberField guided={guided} label="Preço de uma lata, sem IVA" unit="€/lata" value={job.prices.paint_per_can} onChange={v => setPrice("paint_per_can", v)} testid="gq-price-can" />}
        <p className="text-xs text-muted-foreground sm:col-span-2">Para consultar preços de referência, abra o <Link to="/precos" className="underline" target="_blank">comparador de preços</Link>. A taxa de IVA é escolhida no orçamento, segundo as regras em vigor.</p>
      </div>;
      case "review": return <Review preview={preview} error={previewError} language={language} />;
      default:
        if (q.id.endsWith("-name")) return <input className="h-12 w-full rounded-xl border bg-background px-3" value={r.name} maxLength={60} placeholder={`Divisão ${q.room + 1}`} onChange={e => setRoom(q.room, { name: e.target.value })} data-testid={`gq-room-${q.room}-name`} />;
        if (q.id.endsWith("-dims")) return <div className="grid gap-4 sm:grid-cols-2">
          <NumberField guided={guided} label="Comprimento" unit="m" value={r.length_m} onChange={v => setRoom(q.room, { length_m: v })} testid={`gq-room-${q.room}-length`} />
          <NumberField guided={guided} label="Largura" unit="m" value={r.width_m} onChange={v => setRoom(q.room, { width_m: v })} testid={`gq-room-${q.room}-width`} /></div>;
        if (q.id.endsWith("-height")) return <NumberField guided={guided} label={term("ceiling_height", language)} unit="m" value={r.height_m} onChange={v => setRoom(q.room, { height_m: v })} testid={`gq-room-${q.room}-height`} />;
        if (q.id.endsWith("-openings")) return <div className="space-y-3">
          {r.openings.map((o, k) => <div key={k} className="grid grid-cols-[1fr_1fr_auto] items-end gap-2 rounded-xl border p-2">
            <NumberField label={`${o.kind || "Abertura"} — largura`} unit="m" value={o.width_m} onChange={v => setRoom(q.room, { openings: r.openings.map((x, j) => j === k ? { ...x, width_m: v } : x) })} testid={`gq-room-${q.room}-op-${k}-w`} />
            <NumberField label="altura" unit="m" value={o.height_m} onChange={v => setRoom(q.room, { openings: r.openings.map((x, j) => j === k ? { ...x, height_m: v } : x) })} testid={`gq-room-${q.room}-op-${k}-h`} />
            <Button type="button" variant="ghost" size="icon" aria-label="Remover abertura" onClick={() => setRoom(q.room, { openings: r.openings.filter((_, j) => j !== k) })}><Trash2 className="h-4 w-4" /></Button>
          </div>)}
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" onClick={() => setRoom(q.room, { openings: [...r.openings, { kind: "Porta", width_m: "", height_m: "" }] })} data-testid={`gq-room-${q.room}-add-door`}><Plus className="mr-1 h-4 w-4" />Porta</Button>
            <Button type="button" variant="outline" onClick={() => setRoom(q.room, { openings: [...r.openings, { kind: "Janela", width_m: "", height_m: "" }] })}><Plus className="mr-1 h-4 w-4" />Janela</Button>
          </div>
          {r.openings.length === 0 && <p className="text-sm text-muted-foreground">Sem aberturas: nada será deduzido às paredes.</p>}
        </div>;
        return null;
    }
  };

  const sectionIndex = sections.indexOf(current[0].section);
  return (
    <div className="mx-auto max-w-2xl space-y-4 px-1 pb-24" data-testid="guided-quote">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div><p className="text-xs font-semibold uppercase tracking-wide text-primary">Orçamento de pintura</p>
          <h1 className="text-2xl font-bold">{sections[sectionIndex]}</h1></div>
        <div className="flex items-center gap-1 rounded-xl bg-muted p-1" role="radiogroup" aria-label="Modo">
          {MODES.map(m => <button key={m.key} type="button" role="radio" aria-checked={mode === m.key} onClick={() => switchMode(m.key)} data-testid={`gq-mode-${m.key}`}
            className={`min-h-9 rounded-lg px-3 text-sm ${mode === m.key ? "bg-background font-semibold text-primary shadow-sm" : "text-muted-foreground"}`}>{m.label}</button>)}
        </div>
      </div>
      {/* Passo atual e próximo */}
      <ol className="flex flex-wrap gap-1 text-xs" aria-label="Etapas">
        {sections.map((s, i) => <li key={s} className={`rounded-full px-2 py-1 ${i === sectionIndex ? "bg-primary text-primary-foreground" : i < sectionIndex ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground"}`}>{s}</li>)}
      </ol>
      {sections[sectionIndex + 1] && <p className="text-xs text-muted-foreground">A seguir: {sections[sectionIndex + 1]}</p>}

      <div className="space-y-6 rounded-2xl border bg-card p-4 sm:p-6">
        {current.map(q => <div key={q.id} data-testid={`gq-q-${q.id}`}>
          <div className="flex items-start justify-between gap-2">
            <h2 className="text-lg font-semibold">{q.title}</h2>
            {q.help && <button type="button" onClick={() => setShowHelp(h => !h)} className="inline-flex min-h-10 items-center gap-1 rounded-lg px-2 text-sm text-primary" data-testid="gq-help-toggle">
              <CircleHelp className="h-4 w-4" />Ajuda-me</button>}
          </div>
          {(showHelp || (mode === "avancado" && q.help)) && <Help help={q.help} />}
          {guided && q.help?.example && !showHelp && <p className="mb-2 text-sm text-muted-foreground">Ex.: {q.help.example}</p>}
          <div className="mt-3">{render(q)}</div>
        </div>)}
      </div>

      <div className="sticky bottom-2 z-10 flex items-center justify-between gap-2 rounded-2xl border bg-background/95 p-2 shadow-lg backdrop-blur">
        <Button type="button" variant="outline" className="min-h-12" disabled={page === 0} onClick={() => setIdx(page - 1)} data-testid="gq-back"><ArrowLeft className="mr-1 h-4 w-4" />Voltar</Button>
        <button type="button" className="text-xs text-muted-foreground underline" onClick={restart}>Recomeçar</button>
        {isReview
          ? <Button type="button" className="min-h-12" onClick={saveQuote} disabled={saving || !preview} data-testid="gq-save">{saving ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <FileText className="mr-1 h-4 w-4" />}Guardar orçamento</Button>
          : <Button type="button" className="min-h-12" onClick={() => setIdx(page + 1)} data-testid="gq-next">Seguinte<ArrowRight className="ml-1 h-4 w-4" /></Button>}
      </div>
      <p className="text-center text-xs text-muted-foreground">O rascunho é guardado automaticamente neste dispositivo. Nada é enviado sem a sua confirmação.</p>
    </div>
  );
}

function Review({ preview, error, language }) {
  if (error) return <p className="rounded-xl bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-400" role="alert" data-testid="gq-review-error">{error}</p>;
  if (!preview) return <div className="grid place-items-center py-8"><Loader2 className="h-6 w-6 animate-spin" /></div>;
  const lines = preview.lines.filter(l => l.kind === "line");
  const c = preview.calc;
  return <div className="space-y-4" data-testid="gq-review">
    <div className="rounded-xl bg-muted/50 p-3 text-sm">
      <p><strong>Superfície a pintar:</strong> {fmt(c.surface_m2)} m² <span className="ml-1 rounded bg-background px-1.5 py-0.5 text-xs">cálculo</span></p>
      {c.liters != null && <p><strong>Tinta:</strong> {fmt(c.liters, 1)} L{c.cans != null && ` → ${c.cans} lata(s) de ${fmt(c.can_size_l)} L`} <span className="ml-1 rounded bg-background px-1.5 py-0.5 text-xs">cálculo</span></p>}
      <p className="mt-1 text-xs text-muted-foreground">Fórmula: {c.formula}</p>
      <details className="mt-2"><summary className="cursor-pointer text-xs font-medium">Detalhe por divisão</summary>
        <ul className="mt-1 space-y-1 text-xs">{c.rooms.map((r, i) => <li key={i}>{r.name}: paredes {fmt(r.walls_gross_m2)} m² − aberturas {fmt(r.openings_m2)} m² = {fmt(r.walls_net_m2)} m²{r.ceiling_m2 ? ` + teto ${fmt(r.ceiling_m2)} m²` : ""}</li>)}</ul></details>
    </div>
    <div className="overflow-x-auto"><table className="w-full text-sm">
      <thead><tr className="border-b text-left text-xs text-muted-foreground"><th className="py-2">Trabalho</th><th className="text-right">{term("qty", language)}</th><th className="text-right">{term("unit_price", language)}</th><th className="text-right">Total</th></tr></thead>
      <tbody>{lines.map((l, i) => <tr key={i} className="border-b align-top">
        <td className="py-2 pr-2">{l.designation}{(l.price_missing || l.quantity_missing) && <span className="ml-1 rounded bg-amber-500/15 px-1.5 text-xs text-amber-700 dark:text-amber-400">por confirmar</span>}</td>
        <td className="whitespace-nowrap text-right">{l.quantity_missing ? "—" : `${fmt(l.qty)} ${l.unit}`}</td>
        <td className="whitespace-nowrap text-right">{l.price_missing ? "—" : eur2(l.unit_price_ht)}</td>
        <td className="whitespace-nowrap text-right">{l.price_missing || l.quantity_missing ? "—" : eur2(l.qty * l.unit_price_ht)}</td></tr>)}</tbody>
    </table></div>
    <p className="text-right text-lg font-bold" data-testid="gq-total-ht">Total sem IVA: {eur2(preview.totals?.ht)}</p>
    <p className="text-xs text-muted-foreground text-right">O IVA é definido no orçamento, linha a linha.</p>
    {preview.to_confirm.length > 0 ? <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-3 text-sm" data-testid="gq-to-confirm">
      <p className="flex items-center gap-1 font-semibold"><TriangleAlert className="h-4 w-4" />Por confirmar antes de enviar</p>
      <ul className="mt-1 list-disc pl-5">{preview.to_confirm.map(x => <li key={x}>{x}</li>)}</ul>
      <p className="mt-1 text-xs">Pode guardar já: estes pontos ficam anotados no orçamento.</p>
    </div> : <p className="flex items-center gap-1 text-sm text-primary"><CheckCircle2 className="h-4 w-4" />Todos os dados essenciais estão preenchidos.</p>}
    <p className="text-xs text-muted-foreground">Depois de guardar, abre-se o orçamento: aí pode gerar o PDF e preparar o envio (com confirmação do destinatário e do conteúdo).</p>
  </div>;
}
