import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import { Layers, Ruler, Package, ListChecks, Camera, History, FileText, Target, Link2, Check, Plus, Info, ClipboardList,
  Sparkles, AlertTriangle, ArrowRight, Users, RefreshCw, Maximize2, ShoppingCart, ImagePlus, Lock, X } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { Breadcrumbs, ModeToggle, PhaseLocalSelectors, Pill, Loading, ErrorBox, errMsg, useDossierContext, STATUS_TEXT } from "./common";
import { AssistantPanel } from "./AssistantPanel";

const STAGE_ICONS = { preparar: ClipboardList, medir: Ruler, orcamentar: Package, executar: Users, validar: Check };
const fmt = (v) => (v === null || v === undefined ? "—" : new Intl.NumberFormat("pt-PT", { maximumFractionDigits: 2 }).format(v));

function ImpactDialog({ impact, onCancel, onConfirm }) {
  if (!impact) return null;
  return (
    <Dialog open onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="max-w-lg" data-testid="dob-impact-dialog">
        <DialogHeader><DialogTitle>Rever o impacto antes de confirmar</DialogTitle>
          <DialogDescription>{impact.message}</DialogDescription></DialogHeader>
        <div className="grid gap-3 text-sm">
          {impact.impact?.locked && <p className="dob-notice"><Lock size={16} /> {impact.impact.locked_reason}. O compromisso original (orçamento, encomenda ou auto) não é alterado por esta ação.</p>}
          {(impact.impact?.related || []).map((r) => (
            <div key={r.specialty}>
              <p className="font-semibold">{r.label} <span className="text-muted-foreground font-normal">· {r.relation_label}{r.confirmed ? "" : " (por confirmar)"}</span></p>
              {r.items_to_review.length ? <ul className="list-disc ms-5">{r.items_to_review.map((i) => <li key={i.item_id}>{i.title}</li>)}</ul> : <p className="text-muted-foreground">Sem registos a rever.</p>}
            </div>
          ))}
          <p className="text-muted-foreground">Ao confirmar, a alteração fica no histórico e os registos acima são assinalados para revisão.</p>
          <div className="flex justify-end gap-2">
            <button type="button" className="dob-ghost" onClick={onCancel}>Cancelar</button>
            <button type="button" className="dob-primary" onClick={onConfirm} data-testid="dob-impact-confirm">Confirmar alteração</button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/** Registo novo: no modo Guiado, uma pergunta de cada vez (com «Não sei»); no Técnico, formulário compacto. */
function AddRecord({ mode, data, cat, fase, local, onSave, initialKind, onClose }) {
  const [step, setStep] = useState(initialKind ? 1 : 0);
  const [f, setF] = useState({ kind: initialKind || "tarefa", title: "", element: "", detail: "", status: "por_fazer", phase: fase || "", location_id: local || "",
    quantity: "", unit: "m²", document: "", revision: "", page: "", scale: "", method: "", source: "manual" });
  const KINDS = [["tarefa", "Uma tarefa a fazer"], ["pendencia", "Uma pendência ou dúvida"], ["verificacao", "Uma verificação"], ["medicao", "Uma medição"],
    ["material", "Um material"], ["registo", "Um registo ou fotografia"], ["alteracao", "Uma alteração"], ["nota", "Uma nota"]];
  const submit = async (unknown = false) => {
    const body = { specialty: data.specialty.key, kind: f.kind, title: f.title.trim() || (unknown ? "Informação por definir" : ""), element: f.element, detail: f.detail,
      status: unknown ? "pendente" : f.status, phase: f.phase || null, location_id: f.location_id || null, source: f.source, revision: f.revision };
    if (!body.title) { toast.error("Indique um título."); return; }
    if (f.kind === "medicao") {
      const q = f.quantity === "" ? null : Number(String(f.quantity).replace(",", "."));
      if (q !== null && (Number.isNaN(q) || q < 0)) { toast.error("Quantidade inválida."); return; }
      body.measurement = { document: f.document, revision: f.revision, page: f.page, element: f.element, scale: f.scale, method: f.method, quantity: q, unit: f.unit };
      if (q !== null) body.quantities = { medida: q };
      if (q === null) body.status = "pendente";
    }
    if (f.kind === "material") body.validation = "por_confirmar";
    await onSave(body);
  };
  if (mode === "guiado") {
    return (
      <div className="dob-card dob-card-pad grid gap-3" data-testid="dob-add-guided">
        <div className="flex items-center justify-between"><p className="font-bold">Registar nesta especialidade</p><button type="button" aria-label="Fechar" onClick={onClose}><X size={18} /></button></div>
        {step === 0 && <><p>O que quer registar?</p><div className="dob-area-grid">{KINDS.map(([k, l]) => <button key={k} type="button" className="dob-area-card" onClick={() => { setF({ ...f, kind: k }); setStep(1); }}>{l}</button>)}</div></>}
        {step === 1 && <>
          <label className="dob-field"><span>{f.kind === "medicao" ? "O que mediu? (ex.: área de cerâmica da fachada norte)" : f.kind === "material" ? "Que material? (ex.: cerâmica 30×60)" : "Descreva em poucas palavras"}</span>
            <input autoFocus value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="dob-add-title" /></label>
          <div className="flex flex-wrap gap-2">
            <button type="button" className="dob-primary" onClick={() => (f.kind === "medicao" ? setStep(2) : submit())} disabled={!f.title.trim()} data-testid="dob-add-next">{f.kind === "medicao" ? "Seguinte" : "Guardar"}</button>
            <button type="button" className="dob-ghost" onClick={() => submit(true)} data-testid="dob-add-unknown">Não sei — fica pendente</button>
          </div>
        </>}
        {step === 2 && <>
          <p>Qual é a quantidade? <span className="text-sm text-muted-foreground">(a área de uma parede é comprimento × altura, sem as janelas)</span></p>
          <div className="flex flex-wrap gap-2 items-end">
            <label className="dob-field"><span>Quantidade</span><input inputMode="decimal" value={f.quantity} onChange={(e) => setF({ ...f, quantity: e.target.value })} data-testid="dob-add-qty" /></label>
            <label className="dob-field"><span>Unidade</span><select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}>{["m²", "m", "m³", "un", "kg"].map((u) => <option key={u}>{u}</option>)}</select></label>
            <label className="dob-field"><span>De onde vem? (planta, página)</span><input value={f.document} onChange={(e) => setF({ ...f, document: e.target.value })} placeholder="Ex.: Fachadas.pdf, página 2" /></label>
          </div>
          <div className="flex flex-wrap gap-2"><button type="button" className="dob-primary" onClick={() => submit()}>Guardar</button><button type="button" className="dob-ghost" onClick={() => { setF({ ...f, quantity: "" }); submit(true); }}>Não sei — fica pendente</button></div>
        </>}
      </div>
    );
  }
  return (
    <form className="dob-card dob-card-pad grid gap-2" onSubmit={(e) => { e.preventDefault(); submit(); }} data-testid="dob-add-technical">
      <div className="flex items-center justify-between"><p className="font-bold">Novo registo</p><button type="button" aria-label="Fechar" onClick={onClose}><X size={18} /></button></div>
      <div className="grid sm:grid-cols-4 gap-2">
        <label className="dob-field"><span>Tipo</span><select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}>{Object.entries(cat.item_kinds).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="dob-field sm:col-span-2"><span>Título</span><input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} data-testid="dob-add-title" /></label>
        <label className="dob-field"><span>Elemento</span><input value={f.element} onChange={(e) => setF({ ...f, element: e.target.value })} /></label>
        <label className="dob-field"><span>Estado</span><select value={f.status} onChange={(e) => setF({ ...f, status: e.target.value })}>{Object.entries(cat.task_status).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
        <label className="dob-field"><span>Fase</span><select value={f.phase} onChange={(e) => setF({ ...f, phase: e.target.value })}><option value="">Transversal</option>{cat.phases.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}</select></label>
        <label className="dob-field"><span>Local</span><select value={f.location_id} onChange={(e) => setF({ ...f, location_id: e.target.value })}><option value="">Toda a obra</option>{data.locations.map((l) => <option key={l.location_id} value={l.location_id}>{l.path}</option>)}</select></label>
        <label className="dob-field"><span>Origem</span><select value={f.source} onChange={(e) => setF({ ...f, source: e.target.value })}>{Object.entries(cat.sources).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select></label>
      </div>
      {f.kind === "medicao" && <div className="grid sm:grid-cols-4 gap-2">
        {[["document", "Documento"], ["revision", "Revisão"], ["page", "Página/elemento"], ["scale", "Escala"], ["method", "Método"], ["quantity", "Quantidade"]].map(([k, l]) =>
          <label key={k} className="dob-field"><span>{l}</span><input value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} inputMode={k === "quantity" ? "decimal" : undefined} /></label>)}
        <label className="dob-field"><span>Unidade</span><select value={f.unit} onChange={(e) => setF({ ...f, unit: e.target.value })}>{["m²", "m", "m³", "un", "kg"].map((u) => <option key={u}>{u}</option>)}</select></label>
      </div>}
      <label className="dob-field"><span>Detalhe / especificação / referência</span><textarea rows={2} value={f.detail} onChange={(e) => setF({ ...f, detail: e.target.value })} /></label>
      <div><button type="submit" className="dob-primary" data-testid="dob-add-save">Guardar registo</button></div>
    </form>
  );
}

function LayersBlock({ item, mode, onValidate }) {
  const [fix, setFix] = useState(null);
  return (
    <div className="grid gap-2" data-testid={`dob-layers-${item.item_id}`}>
      <ol className="dob-rows">
        {(item.layers || []).map((l) => (
          <li key={l.order} className="dob-row flex-wrap">
            <span className="h-7 w-7 rounded-full bg-muted grid place-items-center text-sm font-bold" aria-hidden="true">{l.order}</span>
            <div className="dob-row-main"><p>{l.name}{l.material ? ` — ${l.material}` : ""}</p>
              <p>{{ extraido: "Extraído", manual: "Manual", inferido: "Inferido" }[l.source]}{l.reference ? ` · ${l.reference}` : ""}{l.note && mode === "tecnico" ? ` · ${l.note}` : ""}</p></div>
            <Pill s={l.validation}>{l.validation === "por_confirmar" ? "A confirmar" : undefined}</Pill>
            {l.validation === "por_confirmar" && <span className="flex gap-1">
              <button type="button" className="dob-ghost" style={{ minHeight: 32 }} onClick={() => onValidate(item, { action: "confirmar", layer_order: l.order })} data-testid={`dob-layer-confirm-${l.order}`}>Confirmar</button>
              <button type="button" className="dob-ghost" style={{ minHeight: 32 }} onClick={() => setFix({ order: l.order, material: l.material || "" })} data-testid={`dob-layer-fix-${l.order}`}>Corrigir</button>
              <button type="button" className="dob-ghost" style={{ minHeight: 32 }} onClick={() => onValidate(item, { action: "rejeitar", layer_order: l.order })}>Rejeitar</button>
            </span>}
          </li>
        ))}
      </ol>
      {fix && <form className="flex flex-wrap gap-2 items-end" onSubmit={(e) => { e.preventDefault(); onValidate(item, { action: "corrigir", layer_order: fix.order, material: fix.material }).then(() => setFix(null)); }}>
        <label className="dob-field flex-1"><span>Material correto da camada {fix.order}</span><input autoFocus value={fix.material} onChange={(e) => setFix({ ...fix, material: e.target.value })} data-testid="dob-layer-fix-input" /></label>
        <button type="submit" className="dob-primary" disabled={!fix.material.trim()}>Guardar correção</button><button type="button" className="dob-ghost" onClick={() => setFix(null)}>Cancelar</button>
      </form>}
    </div>
  );
}

function Origin({ m }) {
  if (!m) return null;
  const rows = [["Documento", m.document], ["Revisão", m.revision], ["Página", m.page], ["Elemento", m.element], ["Escala", m.scale], ["Método", m.method],
    ["Quantidade", m.quantity !== null && m.quantity !== undefined ? `${fmt(m.quantity)} ${m.unit || ""}` : "Por medir"]];
  return <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm" data-testid="dob-origin">{rows.map(([k, v]) => <Fragment key={k}><dt className="text-muted-foreground">{k}</dt><dd>{v || "—"}</dd></Fragment>)}</dl>;
}

function QuantitiesTable({ item, cat, onSave }) {
  const [q, setQ] = useState(item.quantities || {});
  const unit = item.measurement?.unit || "";
  return (
    <div className="overflow-x-auto">
      <table className="dob-table" data-testid={`dob-quantities-${item.item_id}`}>
        <thead><tr>{cat.quantity_kinds.map((k) => <th key={k.key} scope="col">{k.label}</th>)}<th /></tr></thead>
        <tbody><tr>
          {cat.quantity_kinds.map((k) => <td key={k.key}><label className="sr-only" htmlFor={`q-${item.item_id}-${k.key}`}>{k.label}</label>
            <input id={`q-${item.item_id}-${k.key}`} inputMode="decimal" value={q[k.key] ?? ""} placeholder="—" onChange={(e) => setQ({ ...q, [k.key]: e.target.value })} /> <span className="text-xs">{unit}</span></td>)}
          <td><button type="button" className="dob-ghost" style={{ minHeight: 32 }} onClick={() => {
            const out = {};
            for (const [k, v] of Object.entries(q)) { if (v === "" || v === null || v === undefined) continue; const n = Number(String(v).replace(",", ".")); if (Number.isNaN(n) || n < 0) { toast.error(`Valor inválido: ${k}`); return; } out[k] = n; }
            onSave(item, { quantities: out });
          }}>Guardar</button></td>
        </tr></tbody>
      </table>
      <p className="dob-hint mt-1"><Info size={13} /> Cada quantidade é guardada à parte: medir não é o mesmo que orçamentar, encomendar, executar ou faturar.</p>
    </div>
  );
}

export function Specialty({ cat, mode, setMode, reloadTree, setHasAssistant }) {
  const { key } = useParams();
  const { chantierId, fase, local, setCtx, base, qs, tool } = useDossierContext();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState("plantas");
  const [adding, setAdding] = useState(null);
  const [impact, setImpact] = useState(null);
  // No telemóvel o assistente abre só a pedido, para não tapar as ações.
  const [assistant, setAssistant] = useState(() => typeof window === "undefined" || !window.matchMedia || window.matchMedia("(min-width: 901px)").matches);

  const load = useCallback(() => api.get(`/dossier-obra/${chantierId}/especialidades/${key}`, { params: { fase: fase || undefined, local: local || undefined } })
    .then(({ data }) => { setData(data); setError(null); }).catch((e) => setError(errMsg(e))), [chantierId, key, fase, local]);
  useEffect(() => { setData(null); load(); }, [load]);
  useEffect(() => { setHasAssistant?.(assistant); return () => setHasAssistant?.(false); }, [assistant, setHasAssistant]);

  const refresh = () => { load(); reloadTree(); };
  const patchItem = async (item, patch, confirm = false) => {
    try {
      const { data: out } = await api.patch(`/dossier-obra/${chantierId}/itens/${item.item_id}`, { ...patch, confirm });
      if (out.flagged_for_review?.length) toast.info(`${out.flagged_for_review.length} registo(s) relacionado(s) assinalado(s) para revisão.`);
      setImpact(null); refresh(); return true;
    } catch (e) {
      if (e?.response?.status === 409 && e.response.data?.detail?.impact) { setImpact({ ...e.response.data.detail, item, patch }); return false; }
      toast.error(errMsg(e)); return false;
    }
  };
  const validate = async (item, body) => {
    try { await api.post(`/dossier-obra/${chantierId}/itens/${item.item_id}/validacao`, body); toast.success("Registado no histórico"); refresh(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const create = async (body) => {
    try { await api.post(`/dossier-obra/${chantierId}/itens`, body); toast.success("Registo guardado"); setAdding(null); refresh(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  const setState = async (patch) => { try { await api.patch(`/dossier-obra/${chantierId}/especialidades/${key}`, patch); refresh(); } catch (e) { toast.error(errMsg(e)); } };

  const items = useMemo(() => data?.items || [], [data]);
  const byKind = (k) => items.filter((i) => i.kind === k);
  if (error) return <ErrorBox onRetry={load}>{error}</ErrorBox>;
  if (!data) return <Loading>A carregar a especialidade…</Loading>;

  const s = data.specialty;
  const state = data.state;
  const checklist = items.filter((i) => ["tarefa", "pendencia", "verificacao"].includes(i.kind));
  const firstMed = byKind("medicao")[0];
  const firstMat = byKind("material")[0];
  const revision = items.map((i) => i.revision).filter(Boolean).sort().slice(-1)[0];
  const element = items.find((i) => i.element)?.element;
  const reportLink = `${base}/compilar${qs({ esp: key, scope: "especialidade" })}`;
  const TABS = [["plantas", "Plantas e camadas", Layers], ["medicoes", "Medições", Ruler], ["materiais", "Materiais", Package], ["tarefas", "Tarefas", ListChecks],
    ["registos", "Registos", Camera], ["historico", "Histórico", History], ["relatorio", "Relatório", FileText]];
  const history = items.flatMap((i) => (i.history || []).map((h) => ({ ...h, title: i.title }))).sort((a, b) => (b.at || "").localeCompare(a.at || ""));

  return (
    <>
      <div className="grid gap-4 min-w-0" data-testid="dob-specialty">
        <Breadcrumbs items={[{ label: "Dossier de obra", to: `${base}${qs()}` }, { label: data.area?.label.split(" e ")[0], to: `${base}${qs({ vista: "especialidades" })}` }, { label: s.label }]} />
        <header className="dob-head">
          <div className="dob-title">
            <span className="dob-title-icon"><Layers size={28} aria-hidden="true" /></span>
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2"><h1 data-testid="dob-specialty-name">{s.label}</h1>{data.chantier.demo && <span className="dob-demo">Exemplo demonstrativo</span>}</div>
              <p className="dob-sub">Projeto: {data.chantier.name}{mode === "guiado" ? ` — ${s.description}` : ""}</p>
            </div>
          </div>
          <Link to={`${base}/compilar${qs()}`} className="dob-primary"><FileText size={20} /> Compilar dossier</Link>
        </header>
        <div className="dob-context">
          <ModeToggle mode={mode} onChange={setMode} />
          <PhaseLocalSelectors phases={cat.phases} locations={data.locations} fase={fase} local={local} onChange={setCtx} />
          {!assistant && <button type="button" className="dob-ghost" onClick={() => setAssistant(true)} data-testid="dob-open-assistant"><Sparkles size={16} /> Assistente BTP</button>}
        </div>
        <div className="dob-card dob-card-pad"><div className="dob-stages" role="group" aria-label="Etapa do trabalho">
          {cat.stages.map((st, i) => { const Icon = STAGE_ICONS[st.key]; return (
            <span key={st.key} className="inline-flex items-center gap-1.5">
              {i > 0 && <ArrowRight size={16} className="dob-stage-arrow" aria-hidden="true" />}
              <button type="button" className="dob-stage" aria-pressed={state.stage === st.key} onClick={() => setState({ stage: st.key })} data-testid={`dob-stage-${st.key}`}><Icon size={17} aria-hidden="true" /> {st.label}</button>
            </span>); })}
        </div></div>

        <section className="dob-card dob-card-pad grid gap-4">
          <div className="flex flex-wrap items-center gap-3">
            <span className="dob-title-icon" style={{ width: 44, height: 44 }}><Layers size={22} /></span>
            <h2 className="text-xl font-bold">{element || s.label}</h2>
            {mode === "tecnico" ? <select className="dob-select" aria-label="Estado da especialidade" value={state.status || "por_iniciar"} onChange={(e) => setState({ status: e.target.value })} data-testid="dob-spec-status">
              {Object.entries(cat.specialty_status).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select> : <Pill s={state.status || "por_iniciar"} />}
            {data.counts.hidden_by_filter > 0 && <span className="dob-hint">{data.counts.hidden_by_filter} registo(s) de outras fases/locais ocultos pelo filtro</span>}
          </div>
          <div className="dob-kpis">
            <div className="dob-kpi"><Maximize2 size={22} aria-hidden="true" /><div><p>{firstMed?.validation === "confirmado" || firstMed?.validation === "validado" ? "Área validada" : "Área medida"}</p><p>{firstMed?.measurement?.quantity != null ? `${fmt(firstMed.measurement.quantity)} ${firstMed.measurement.unit}` : "Por medir"}</p></div></div>
            <div className="dob-kpi"><Layers size={22} aria-hidden="true" /><div><p>Material</p><p>{!firstMat ? "Por definir" : firstMat.validation === "por_confirmar" ? "Por confirmar" : STATUS_TEXT[firstMat.validation]}</p></div></div>
            {mode === "tecnico" || revision ? <div className="dob-kpi"><RefreshCw size={22} aria-hidden="true" /><div><p>Revisão</p><p>{revision || "—"}</p></div></div>
              : <div className="dob-kpi"><Users size={22} aria-hidden="true" /><div><p>Equipa</p><p>{state.responsible || "Por atribuir"}</p></div></div>}
          </div>
          {mode === "tecnico" && <label className="dob-field max-w-sm"><span>Responsável</span><input defaultValue={state.responsible || ""} onBlur={(e) => e.target.value !== (state.responsible || "") && setState({ responsible: e.target.value })} placeholder="Por atribuir" data-testid="dob-responsible" /></label>}
          <div className="dob-next"><Target size={30} aria-hidden="true" className="shrink-0" /><div><p className="font-bold text-lg">O próximo passo</p><p data-testid="dob-next-step">{data.next_step || "Sem passos em aberto. Registe a próxima tarefa ou verificação."}</p></div></div>
          <div className="dob-rows" id="dob-pendencias" data-testid="dob-checklist">
            {checklist.length === 0 && <p className="text-sm text-muted-foreground py-2">Sem tarefas nem pendências.</p>}
            {checklist.map((i) => {
              const done = i.status === "concluido";
              const locked = i.status === "bloqueado";
              return (
                <div key={i.item_id} className="dob-row">
                  {locked ? <Lock size={18} aria-label="Bloqueado" className="text-muted-foreground" /> :
                    <button type="button" role="checkbox" aria-checked={done} className="dob-check" aria-label={`Concluir: ${i.title}`} onClick={() => patchItem(i, { status: done ? "por_fazer" : "concluido" })} data-testid={`dob-check-${i.item_id}`}>{done && <Check size={14} />}</button>}
                  <div className="dob-row-main"><p>{i.title}</p>{(mode === "tecnico" || i.needs_review) && <p>{[cat.item_kinds[i.kind], i.location_path, i.needs_review && "A rever: alteração noutra especialidade"].filter(Boolean).join(" · ")}</p>}</div>
                  {i.related_specialty ? <Link to={`${base}/especialidade/${i.related_specialty}${qs()}`} className="dob-pill dob-pill-link" data-testid={`dob-related-${i.related_specialty}`}>{data.dependencies.find((d) => d.other === i.related_specialty)?.other_label || "Outra especialidade"}</Link>
                    : <Pill s={locked ? "bloqueado" : i.status}>{locked ? "Aguarda verificação" : undefined}</Pill>}
                </div>
              );
            })}
          </div>
          {data.dependencies.length > 0 && (
            <div className="flex flex-wrap items-center gap-2" data-testid="dob-links">
              <span className="dob-hint"><Link2 size={15} /> Ligações a outras especialidades</span>
              {data.dependencies.map((d) => (
                <Link key={d.dep_id} to={`${base}/especialidade/${d.other}${qs()}`} className="dob-link-chip" title={`${d.relation_label}${d.status !== "confirmada" ? " (por confirmar)" : ""}`} data-testid={`dob-link-${d.other}`}>
                  {d.other_label}{d.other_open > 0 && <span className="text-xs font-normal">· {d.other_open} em aberto</span>}{d.status !== "confirmada" && <span className="text-xs font-normal">· proposta</span>}
                </Link>))}
            </div>
          )}
        </section>

        <section className="dob-card dob-card-pad grid gap-2" aria-label="Ações">
          <div className="flex flex-wrap gap-2">
            <Link to={tool("/plan", key)} className="dob-ghost"><Plus size={16} /> Adicionar planta</Link>
            <button type="button" className="dob-ghost" onClick={() => setAdding("medicao")} data-testid="dob-action-medir"><Ruler size={16} /> Medir área</button>
            <button type="button" className="dob-ghost" onClick={() => setTab("materiais")}><Check size={16} /> Confirmar material</button>
            <Link to={tool("/appro", key)} className="dob-ghost"><ShoppingCart size={16} /> Pedir preço</Link>
            <button type="button" className="dob-ghost" onClick={() => setAdding("registo")}><ArrowRight size={16} /> Registar avanço</button>
            <Link to={tool("/suivi-chantier", key)} className="dob-ghost"><ImagePlus size={16} /> Adicionar fotografia</Link>
            <button type="button" className="dob-ghost" onClick={() => document.getElementById("dob-pendencias")?.scrollIntoView({ behavior: "smooth" })}><AlertTriangle size={16} /> Rever pendências</button>
            <Link to={reportLink} className="dob-ghost" data-testid="dob-action-report"><FileText size={16} /> Preparar relatório</Link>
            <button type="button" className="dob-primary" onClick={() => setAdding("_")} data-testid="dob-add"><Plus size={16} /> Novo registo</button>
          </div>
          <p className="dob-hint"><Info size={13} /> As ferramentas abrem com esta obra{fase || local ? ", fase e local" : ""} já selecionados.</p>
        </section>
        {adding && <AddRecord mode={mode} data={data} cat={cat} fase={fase} local={local} initialKind={adding === "_" ? null : adding} onSave={create} onClose={() => setAdding(null)} />}

        <section className="dob-card dob-card-pad grid gap-3">
          <h2 className="text-lg font-bold">Informação desta especialidade</h2>
          <div className="dob-tabs" role="tablist" aria-label="Secções da especialidade">
            {TABS.map(([k, l, Icon]) => <button key={k} type="button" role="tab" aria-selected={tab === k} onClick={() => setTab(k)} data-testid={`dob-tab-${k}`}><Icon size={16} aria-hidden="true" /> {l}</button>)}
          </div>
          <div role="tabpanel" className="grid gap-3">
            {tab === "plantas" && <>
              {byKind("medicao").length === 0 && byKind("documento").length === 0 && <p className="text-sm text-muted-foreground">Ainda sem plantas nem medições. <Link className="underline" to={tool("/plan", key)}>Adicionar uma planta</Link>.</p>}
              {byKind("medicao").map((m) => (
                <div key={m.item_id} className="grid sm:grid-cols-2 gap-4 border rounded-xl p-3">
                  <div><p className="font-semibold mb-1">{m.title}</p><p className="text-xs text-muted-foreground mb-2">Origem da medição · {{ extraido: "extraída de documento", manual: "introduzida manualmente", inferido: "inferida (a confirmar)" }[m.source]}</p><Origin m={m.measurement} /></div>
                  <div className="grid gap-2 content-start">{byKind("material").filter((x) => x.layers?.length && (!x.element || x.element === m.element)).map((x) => <LayersBlock key={x.item_id} item={x} mode={mode} onValidate={validate} />)}</div>
                </div>))}
              {byKind("material").some((x) => x.layers?.some((l) => l.source === "inferido" && l.validation === "por_confirmar")) &&
                <p className="dob-notice"><Info size={16} /> Trama detetada: confirmar material e composição. Uma trama não prova, por si só, o material nem todas as camadas.</p>}
              {byKind("documento").map((d) => <div key={d.item_id} className="dob-row"><FileText size={18} /><div className="dob-row-main"><p>{d.title}</p><p>{[d.revision && `Revisão ${d.revision}`, d.ref && "ligado por referência"].filter(Boolean).join(" · ")}</p></div><Pill s={d.display_status} /></div>)}
            </>}
            {tab === "medicoes" && (byKind("medicao").length === 0 ? <p className="text-sm text-muted-foreground">Sem medições. <button type="button" className="underline" onClick={() => setAdding("medicao")}>Medir área</button>.</p> :
              byKind("medicao").map((m) => <div key={m.item_id} className="grid gap-2 border rounded-xl p-3"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold flex-1">{m.title}</p><Pill s={m.display_status} /></div>
                {mode === "tecnico" ? <QuantitiesTable item={m} cat={cat} onSave={patchItem} /> : <p className="text-sm">Medida: <b>{m.measurement?.quantity != null ? `${fmt(m.measurement.quantity)} ${m.measurement.unit}` : "por medir"}</b>{m.measurement?.document ? ` — ${m.measurement.document}${m.measurement.page ? `, página ${m.measurement.page}` : ""}` : ""}</p>}
              </div>))}
            {tab === "materiais" && (byKind("material").length === 0 ? <p className="text-sm text-muted-foreground">Sem materiais registados.</p> :
              byKind("material").map((m) => <div key={m.item_id} className="grid gap-2 border rounded-xl p-3" data-testid="dob-material">
                <div className="flex flex-wrap items-center gap-2"><p className="font-semibold flex-1">{m.title}</p><Pill s={m.validation} /><span className="text-xs text-muted-foreground">{cat.sources[m.source]}</span></div>
                {m.detail && <p className="text-sm">{m.detail}</p>}
                {m.layers?.length ? <LayersBlock item={m} mode={mode} onValidate={validate} /> : m.validation === "por_confirmar" && <div className="flex gap-2"><button type="button" className="dob-ghost" onClick={() => validate(m, { action: "confirmar" })}>Confirmar</button><button type="button" className="dob-ghost" onClick={() => validate(m, { action: "rejeitar" })}>Rejeitar</button></div>}
                <Link to={tool("/appro", key)} className="dob-hint underline w-fit"><ShoppingCart size={13} /> Pedir preço deste material</Link>
              </div>))}
            {tab === "tarefas" && <><div className="dob-rows">{checklist.map((i) => <div key={i.item_id} className="dob-row"><div className="dob-row-main"><p>{i.title}</p><p>{[cat.item_kinds[i.kind], i.location_path, i.phase && cat.phases.find((p) => p.key === i.phase)?.label].filter(Boolean).join(" · ")}</p></div>
              {mode === "tecnico" ? <select className="dob-select" aria-label={`Estado de ${i.title}`} value={i.status} onChange={(e) => patchItem(i, { status: e.target.value })}>{Object.entries(cat.task_status).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select> : <Pill s={i.status} />}</div>)}</div>
              <Link to={tool("/planning", key)} className="dob-hint underline w-fit"><ArrowRight size={13} /> Abrir no planeamento</Link></>}
            {tab === "registos" && <>{[...byKind("registo"), ...byKind("verificacao"), ...byKind("alteracao"), ...byKind("nota")].map((r) => <div key={r.item_id} className="dob-row"><div className="dob-row-main"><p>{r.title}</p><p>{[cat.item_kinds[r.kind], (r.created_at || "").slice(0, 10)].join(" · ")}</p></div><Pill s={r.display_status} /></div>)}
              <Link to={tool("/suivi-chantier", key)} className="dob-ghost w-fit"><Camera size={16} /> Fotografias e relatórios de obra</Link></>}
            {tab === "historico" && <ol className="dob-rows" data-testid="dob-history">{history.slice(0, 80).map((h, i) => <li key={i} className="dob-row"><div className="dob-row-main"><p>{h.title} — {h.action.replace(/_/g, " ")}</p><p>{(h.at || "").slice(0, 16).replace("T", " ")} · {h.by}{h.note ? ` · ${h.note}` : ""}</p></div></li>)}</ol>}
            {tab === "relatorio" && <div className="grid gap-2"><p className="text-sm">O relatório reúne os registos desta especialidade (com origem, revisões e pendências) num documento PDF, Word, Excel ou ZIP.</p>
              <button type="button" className="dob-primary w-fit" onClick={() => nav(reportLink)} data-testid="dob-prepare-report"><FileText size={18} /> Preparar relatório da especialidade</button></div>}
          </div>
          <p className="dob-hint"><Info size={13} /> Distinção visível: extraído de documento · introduzido manualmente · inferido (a confirmar).</p>
        </section>
        <section className="dob-card dob-card-pad flex flex-wrap items-center gap-3">
          <FileText size={26} aria-hidden="true" />
          <div className="flex-1 min-w-48"><p className="font-bold">Da especialidade ao dossier completo</p><p className="text-sm text-muted-foreground">Reúna as especialidades escolhidas num único documento.</p></div>
          <Link to={`${base}/compilar${qs()}`} className="dob-primary">Escolher conteúdo <ArrowRight size={16} /></Link>
        </section>
      </div>
      {assistant && <AssistantPanel chantierId={chantierId} specialty={key} specialtyLabel={s.label} fase={fase} local={local} onClose={() => setAssistant(false)} onPrepareReport={() => nav(reportLink)} />}
      <ImpactDialog impact={impact} onCancel={() => setImpact(null)} onConfirm={() => patchItem(impact.item, impact.patch, true)} />
    </>
  );
}
