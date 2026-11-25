import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Layers, Ruler, Package, Camera, History, FileText, Target, Link2, Check, Plus, Info, Maximize2, Users, RefreshCw,
  Lock, ListChecks, Clock, CheckCircle2, ExternalLink, Image as ImageIcon, ClipboardCheck, ArrowRight, ShoppingCart, ImagePlus, Sparkles, Calculator } from "lucide-react";
import { api } from "@/lib/api";
import { ModeToggle, Loading, ErrorBox, errMsg, useDossierContext, STATUS_TEXT } from "./common";
import { AssistantPanel } from "./AssistantPanel";
import { ImpactDialog, AddRecord, LayersBlock, Origin, QuantitiesTable, STAGE_ICONS, fmt } from "./parts";
import { AREA_SHORT, specIcon } from "./icons";
import { DossierHeader, ContextSelects, Crumbs, FormatChip } from "./layout";
import { BudgetPanel } from "./BudgetPanel";

const DETAIL_TABS = [["plantas", "Planta e camadas", Layers], ["medicoes", "Medições", Ruler], ["orcamento", "Orçamento", Calculator], ["materiais", "Materiais", Package], ["registos", "Registos", ClipboardCheck]];
const clean = (name) => (name || "").replace(/ \(exemplo demonstrativo\)$/, "");

/** Esquema da medição a partir das dimensões registadas (não é a planta: a planta abre na ferramenta de plantas). */
function MeasureSketch({ m, planLink }) {
  const w = m?.width_m, h = m?.height_m;
  if (!w || !h) {
    return <div className="dob-sketch dob-sketch-empty"><Layers size={28} aria-hidden="true" /><p>Sem dimensões registadas para desenhar o esquema.</p><Link to={planLink} className="dob-ghost dob-sm"><Plus size={14} /> Adicionar planta</Link></div>;
  }
  const W = 460, H = 250, pad = 50;
  const k = Math.min((W - 2 * pad) / w, (H - 2 * pad) / h);
  const rw = w * k, rh = h * k, x = (W - rw) / 2, y = (H - rh) / 2 - 6;
  return (
    <figure className="dob-sketch" data-testid="dob-sketch">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={`Esquema da medição: ${fmt(w)} m por ${fmt(h)} m`}>
        <defs><pattern id="dob-hatch" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="9" height="9" fill="#dff3e4" /><line x1="0" y1="0" x2="0" y2="9" stroke="#7cc596" strokeWidth="1.4" /></pattern></defs>
        <line x1={x - 30} y1={y + rh} x2={x + rw + 30} y2={y + rh} stroke="#4b5563" strokeWidth="1.5" />
        <rect x={x} y={y} width={rw} height={rh} fill="url(#dob-hatch)" stroke="#2f7a4b" strokeWidth="2" />
        <line x1={x} y1={y + rh + 18} x2={x + rw} y2={y + rh + 18} stroke="#374151" /><line x1={x} y1={y + rh + 12} x2={x} y2={y + rh + 24} stroke="#374151" /><line x1={x + rw} y1={y + rh + 12} x2={x + rw} y2={y + rh + 24} stroke="#374151" />
        <text x={x + rw / 2} y={y + rh + 38} textAnchor="middle" fontSize="13" fill="#1f2937">{fmt(w)} m</text>
        <line x1={x + rw + 18} y1={y} x2={x + rw + 18} y2={y + rh} stroke="#374151" /><line x1={x + rw + 12} y1={y} x2={x + rw + 24} y2={y} stroke="#374151" /><line x1={x + rw + 12} y1={y + rh} x2={x + rw + 24} y2={y + rh} stroke="#374151" />
        <text x={x + rw + 26} y={y + rh / 2 + 4} fontSize="13" fill="#1f2937">{fmt(h)} m</text>
      </svg>
      <figcaption>Esquema da medição — não substitui a planta. <Link to={planLink} className="underline">Abrir planta</Link></figcaption>
    </figure>
  );
}

function StatusPill({ status }) {
  const map = { concluido: ["dob-pill-concluido", CheckCircle2, "Concluído"], pendente: ["dob-pill-pendente", Clock, "Pendente"], bloqueado: ["dob-pill-rascunho", Lock, "Aguarda verificação"],
    em_curso: ["dob-pill-em_curso", Clock, "Em curso"], por_fazer: ["dob-pill-rascunho", null, "Por fazer"], nao_aplicavel: ["dob-pill-rascunho", null, "Não aplicável"] };
  const [cls, Icon, label] = map[status] || map.por_fazer;
  return <span className={`dob-pill ${cls}`}>{Icon && <Icon size={14} aria-hidden="true" />}{label}</span>;
}

export function Specialty({ cat, mode, setMode, reloadTree }) {
  const { key } = useParams();
  const [params, setParams] = useSearchParams();
  const secao = params.get("secao");
  const { chantierId, fase, local, setCtx, base, qs, tool } = useDossierContext();
  const nav = useNavigate();
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [adding, setAdding] = useState(null);
  const [impact, setImpact] = useState(null);
  const [assistant, setAssistant] = useState(() => typeof window === "undefined" || !window.matchMedia || window.matchMedia("(min-width: 1200px)").matches);

  const load = useCallback(() => api.get(`/dossier-obra/${chantierId}/especialidades/${key}`, { params: { fase: fase || undefined, local: local || undefined } })
    .then(({ data }) => { setData(data); setError(null); }).catch((e) => setError(errMsg(e))), [chantierId, key, fase, local]);
  useEffect(() => { load(); }, [load]);
  const refresh = () => { load(); reloadTree(); };
  const setSecao = (s) => { const n = new URLSearchParams(params); if (s) n.set("secao", s); else n.delete("secao"); setParams(n); };

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
  if (error) return <ErrorBox onRetry={load}>{error}</ErrorBox>;
  if (!data) return <Loading>A carregar a especialidade…</Loading>;

  const s = data.specialty;
  const state = data.state;
  const byKind = (k) => items.filter((i) => i.kind === k);
  const checklist = items.filter((i) => ["tarefa", "pendencia", "verificacao"].includes(i.kind));
  const meds = byKind("medicao"), mats = byKind("material");
  const kpiMode = meds.length > 0 || mats.length > 0;
  const firstMed = meds[0], firstMat = mats[0];
  const revision = items.map((i) => i.revision).filter(Boolean).sort().slice(-1)[0];
  const element = items.find((i) => i.element)?.element;
  const reportLink = `${base}/compilar${qs({ esp: key, scope: "especialidade" })}`;
  const faseLabel = cat.phases.find((p) => p.key === fase)?.label;
  const localName = data.filters.local_path ? data.filters.local_path.split(" · ").slice(-1)[0] : "";
  const ctxLine = [s.short || s.label, faseLabel, secao ? localName : null].filter(Boolean).join(" · ");
  const Icon = specIcon(key);
  const inferredLayers = mats.some((x) => x.layers?.some((l) => l.source === "inferido" && l.validation === "por_confirmar"));
  const pendingOpen = checklist.find((i) => i.status === "pendente");
  const assistantIntro = secao && inferredLayers ? "A trama sugere um revestimento. Confirme o material antes de calcular a compra."
    : !kpiMode && pendingOpen ? `Falta: ${pendingOpen.title.toLowerCase()}, antes de avançar.` : "Estou a acompanhar esta especialidade. Quer verificar o que falta antes de começar?";
  const quick = secao === "orcamento" ? [[Calculator, "Que quantidades faltam para orçamentar?"], [ListChecks, "Que preços estão por confirmar?"]]
    : secao ? [[Layers, "Explicar as camadas"], [ListChecks, "O que falta validar?"]]
    : kpiMode ? [[ListChecks, "O que falta preparar?"], [Link2, data.dependencies.some((d) => d.other_area === "engenharia") ? "Ver ligações à engenharia" : "Ver ligações a outras especialidades"]]
      : [[ListChecks, "O que devo verificar?"], [Link2, "Ver trabalhos dependentes"]];
  const sourceDoc = firstMed?.measurement?.document;
  const checkbox = (i) => i.status === "bloqueado" ? <Lock size={18} className="dob-lock" aria-label="Bloqueado" />
    : <button type="button" role="checkbox" aria-checked={i.status === "concluido"} className="dob-check" aria-label={`Concluir: ${i.title}`} onClick={() => patchItem(i, { status: i.status === "concluido" ? "por_fazer" : "concluido" })} data-testid={`dob-check-${i.item_id}`}>{i.status === "concluido" && <Check size={14} />}</button>;

  const technicalActions = mode === "tecnico" && (
    <section className="dob-card dob-card-pad flex flex-wrap gap-2" aria-label="Ações">
      <Link to={tool("/plan", key)} className="dob-ghost dob-sm"><Plus size={15} /> Adicionar planta</Link>
      <button type="button" className="dob-ghost dob-sm" onClick={() => setAdding("medicao")} data-testid="dob-action-medir"><Ruler size={15} /> Medir área</button>
      <button type="button" className="dob-ghost dob-sm" onClick={() => setSecao("materiais")}><Check size={15} /> Confirmar material</button>
      <Link to={tool("/appro", key)} className="dob-ghost dob-sm"><ShoppingCart size={15} /> Pedir preço</Link>
      <button type="button" className="dob-ghost dob-sm" onClick={() => setAdding("registo")}><ArrowRight size={15} /> Registar avanço</button>
      <Link to={tool("/suivi-chantier", key)} className="dob-ghost dob-sm"><ImagePlus size={15} /> Adicionar fotografia</Link>
      <button type="button" className="dob-ghost dob-sm" onClick={() => setSecao("historico")}><History size={15} /> Histórico</button>
      <select className="dob-select dob-sm" aria-label="Estado da especialidade" value={state.status || "por_iniciar"} onChange={(e) => setState({ status: e.target.value })} data-testid="dob-spec-status">
        {Object.entries(cat.specialty_status).map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
      <label className="dob-select dob-sm"><Users size={15} /><span className="sr-only">Responsável</span><input defaultValue={state.responsible || ""} onBlur={(e) => e.target.value !== (state.responsible || "") && setState({ responsible: e.target.value })} placeholder="Responsável" data-testid="dob-responsible" /></label>
      <button type="button" className="dob-primary dob-sm" onClick={() => setAdding("_")} data-testid="dob-add"><Plus size={15} /> Novo registo</button>
    </section>
  );

  const kpis = (
    <div className="dob-kpis">
      <div className="dob-kpi"><Maximize2 size={26} aria-hidden="true" /><div><p>{secao ? "Área medida:" : firstMed && ["confirmado", "validado", "corrigido"].includes(firstMed.validation) ? "Área validada" : "Área medida"}</p><p>{firstMed?.measurement?.quantity != null ? `${fmt(firstMed.measurement.quantity)} ${firstMed.measurement.unit}` : "Por medir"}</p></div></div>
      <div className="dob-kpi"><Layers size={26} aria-hidden="true" /><div><p>{secao ? "Material:" : "Material"}</p><p>{!firstMat ? "Por definir" : firstMat.validation === "por_confirmar" ? "Por confirmar" : STATUS_TEXT[firstMat.validation]}</p></div></div>
      {secao ? <div className="dob-kpi"><RefreshCw size={26} aria-hidden="true" /><div><p>Revisão:</p><p>{revision || "—"}</p></div></div>
        : <div className="dob-kpi"><Users size={26} aria-hidden="true" /><div><p>Equipa</p><p>{state.responsible || "Por atribuir"}</p></div></div>}
    </div>
  );
  const docs = [...byKind("documento"), ...byKind("registo"), ...byKind("nota")];

  return (
    <div className="dob-page" data-testid="dob-specialty">
      <Crumbs items={[{ label: "Dossier de obra", to: `${base}${qs()}` }, { label: AREA_SHORT[s.area] || "Área", to: `${base}${qs({ vista: "especialidades" })}` },
        { label: s.short || s.label, to: secao ? `${base}/especialidade/${key}${qs()}` : null }]} />
      <DossierHeader icon={Icon} title={s.short || s.label} testId="dob-specialty-name" demo={data.chantier.demo}
        subtitle={secao ? `Projeto: ${clean(data.chantier.name)}` : kpiMode ? "Tudo o que precisa para preparar, executar e entregar." : clean(data.chantier.name)}
        action={<Link to={`${base}/compilar${qs()}`} className="dob-primary dob-lg" data-testid="dob-compile-btn"><FileText size={22} /> Compilar dossier</Link>} />
      <div className={`dob-columns ${assistant ? "" : "no-assistant"}`}>
        <div className="dob-main">
          <div className="dob-context">
            <ModeToggle mode={mode} onChange={setMode} />
            <ContextSelects cat={cat} locations={data.locations} fase={fase} local={local} onChange={setCtx} />
          </div>
          {!assistant && <button type="button" className="dob-fab" onClick={() => setAssistant(true)} data-testid="dob-open-assistant"><Sparkles size={18} /> Assistente BTP</button>}

          {!secao && kpiMode && (
            <div className="dob-card dob-stages-card"><div className="dob-stages" role="group" aria-label="Etapa do trabalho">
              {cat.stages.map((st, i) => { const SI = STAGE_ICONS[st.key]; return (
                <span key={st.key} className="inline-flex items-center gap-2">
                  {i > 0 && <ArrowRight size={18} className="dob-stage-arrow" aria-hidden="true" />}
                  <button type="button" className="dob-stage" aria-pressed={state.stage === st.key} onClick={() => setState({ stage: st.key })} data-testid={`dob-stage-${st.key}`}><SI size={19} aria-hidden="true" /> {st.label}</button>
                </span>); })}
            </div></div>
          )}

          {technicalActions}
          {adding && <AddRecord mode={mode} data={data} cat={cat} fase={fase} local={local} initialKind={adding === "_" ? null : adding} onSave={create} onClose={() => setAdding(null)} />}

          {/* Imagem 1 — resumo da especialidade com medições/materiais */}
          {!secao && kpiMode && <>
            <section className="dob-card dob-card-pad dob-gap">
              <div className="dob-card-title"><span className="dob-tile"><Layers size={24} /></span><h2>{element || s.label}</h2>
                <span className={`dob-pill dob-pill-${state.status || "por_iniciar"} dob-dot`}>{cat.specialty_status[state.status || "por_iniciar"]}</span></div>
              {kpis}
              <div className="dob-nextbox">
                <div className="dob-next"><span className="dob-target"><Target size={26} aria-hidden="true" /></span><div><p className="font-bold text-lg">O próximo passo</p><p data-testid="dob-next-step">{data.next_step || "Sem passos em aberto."}</p></div></div>
                <div className="dob-rows" id="dob-pendencias" data-testid="dob-checklist">
                  {checklist.map((i) => {
                    const rel = i.related_specialty && data.dependencies.find((d) => d.other === i.related_specialty);
                    return (
                      <div key={i.item_id} className="dob-row">
                        {checkbox(i)}
                        <div className="dob-row-main"><p>{i.title}</p>{i.needs_review && <p>A rever: alteração noutra especialidade</p>}</div>
                        {i.related_specialty ? <Link to={`${base}/especialidade/${i.related_specialty}${qs()}`} className="dob-pill dob-pill-link" title={rel?.other_label} data-testid={`dob-related-${i.related_specialty}`}>{AREA_SHORT[rel?.other_area] || rel?.other_label || "Ligação"}</Link>
                          : <span className={`dob-pill dob-pill-${i.status}`}>{STATUS_TEXT[i.status]}</span>}
                      </div>
                    );
                  })}
                  {checklist.length === 0 && <p className="text-sm text-muted-foreground p-3">Sem tarefas nem pendências.</p>}
                </div>
              </div>
              {data.dependencies.length > 0 && (
                <div className="dob-links-row" data-testid="dob-links">
                  <span className="dob-hint"><Link2 size={17} /> Ligações a outras especialidades</span>
                  {data.dependencies.map((d) => { const DI = specIcon(d.other); return (
                    <Link key={d.dep_id} to={`${base}/especialidade/${d.other}${qs()}`} className="dob-link-chip" title={`${d.relation_label}${d.status !== "confirmada" ? " (por confirmar)" : ""}`} data-testid={`dob-link-${d.other}`}><DI size={16} /> {d.other_label}</Link>); })}
                </div>
              )}
            </section>
            <section className="dob-card dob-card-pad dob-gap">
              <h2 className="dob-h2">Informação desta especialidade</h2>
              <div className="dob-tiles">
                {[["plantas", "Plantas e camadas", Layers], ["orcamento", "Medições e custos", Calculator], ["materiais", "Materiais", Package], ["registos", "Fotografias", ImageIcon]].map(([k, l, TI]) =>
                  <button key={k} type="button" className="dob-tile-btn" onClick={() => setSecao(k)} data-testid={`dob-tab-${k}`}><TI size={22} aria-hidden="true" /> {l}</button>)}
              </div>
              <p className="dob-hint"><Info size={15} /> Identificação de tramas sujeita a confirmação.</p>
            </section>
            <section className="dob-card dob-final-card">
              <span className="dob-tile"><FileText size={24} /></span>
              <div className="flex-1 min-w-48"><p className="font-bold text-lg">Da especialidade ao dossier completo</p><p className="text-sm text-muted-foreground">Reúna as especialidades escolhidas num único documento.</p></div>
              <div className="flex gap-2"><FormatChip f="pdf" /><FormatChip f="docx" /><FormatChip f="xlsx" /></div>
              <span className="dob-vsep" aria-hidden="true" />
              <Link to={`${base}/compilar${qs()}`} className="dob-primary">Escolher conteúdo <ArrowRight size={17} /></Link>
            </section>
          </>}

          {/* Imagem 3 — especialidade de verificação/sequência */}
          {!secao && !kpiMode && <>
            <section className="dob-card dob-card-pad dob-gap">
              <div className="dob-card-title"><span className="dob-tile"><ListChecks size={24} /></span><h2>{element || "Tarefas e verificações"}</h2></div>
              <div className="dob-rows dob-boxed" id="dob-pendencias" data-testid="dob-checklist">
                {checklist.map((i) => (
                  <div key={i.item_id} className="dob-row">{checkbox(i)}<div className="dob-row-main"><p>{i.title}</p>{i.needs_review && <p>A rever: alteração noutra especialidade</p>}</div>
                    {i.related_specialty && i.status !== "bloqueado" ? <Link to={`${base}/especialidade/${i.related_specialty}${qs()}`} className="dob-pill dob-pill-link" data-testid={`dob-related-${i.related_specialty}`}>{data.dependencies.find((d) => d.other === i.related_specialty)?.other_label || "Ligação"}</Link>
                      : (i.status !== "por_fazer" || mode === "tecnico") && <StatusPill status={i.status} />}</div>))}
                {checklist.length === 0 && <p className="text-sm text-muted-foreground p-3">Sem tarefas nem verificações.</p>}
              </div>
              {data.dependencies.length > 0 && <p className="dob-hint"><Info size={15} /> Sequência a confirmar pelo responsável da obra.</p>}
            </section>
            {data.dependencies.length > 0 && (
              <section className="dob-card dob-card-pad dob-gap" data-testid="dob-links">
                <div className="dob-card-title"><span className="dob-tile"><Link2 size={24} /></span><h2>Este trabalho liga-se a…</h2></div>
                <div className="dob-timeline">
                  {data.dependencies.map((d) => { const DI = specIcon(d.other); return (
                    <Link key={d.dep_id} to={`${base}/especialidade/${d.other}${qs()}`} className="dob-tl-row" data-testid={`dob-link-${d.other}`}>
                      <DI size={20} aria-hidden="true" /><span className="flex-1">{AREA_SHORT[d.other_area]} · {d.other_label}</span>
                      {d.other_blocked > 0 ? <span className="dob-pill dob-pill-pendente"><Clock size={14} /> Aguarda validação</span>
                        : <span className="dob-pill dob-pill-rascunho"><Link2 size={14} /> {d.direction === "out" ? "Depende deste trabalho" : d.relation_label}</span>}
                    </Link>); })}
                </div>
              </section>
            )}
            <section className="dob-card dob-card-pad dob-gap" data-testid="dob-docs">
              <div className="dob-card-title"><span className="dob-tile"><FileText size={24} /></span><h2>Documentos e registos</h2></div>
              <div className="dob-rows dob-boxed">
                {docs.map((d) => {
                  const DI = d.kind === "documento" ? FileText : /foto/i.test(d.title) ? ImageIcon : ClipboardCheck;
                  const to = d.ref?.kind === "plan" ? `/plan/${d.ref.id}` : d.kind === "registo" ? tool("/suivi-chantier", key) : null;
                  return (
                    <div key={d.item_id} className="dob-row dob-doc-row">
                      <DI size={20} className={d.kind === "documento" ? "text-red-600" : ""} aria-hidden="true" />
                      <p className="dob-doc-name">{d.title}</p>
                      <span className="dob-doc-mid">{d.status === "pendente" ? <span className="dob-pill dob-pill-pendente">{d.detail || "Pendente"}</span> : (d.detail || (d.revision ? `Revisão ${d.revision}` : ""))}</span>
                      {to ? <Link to={to} className="dob-icon-btn" aria-label={`Abrir ${d.title}`}><ExternalLink size={16} /></Link> : <span className="dob-icon-btn" aria-hidden="true"><ExternalLink size={16} /></span>}
                    </div>
                  );
                })}
                {docs.length === 0 && <p className="text-sm text-muted-foreground p-3">Sem documentos nem registos.</p>}
              </div>
              <div className="flex flex-wrap gap-3">
                <button type="button" className="dob-primary" onClick={() => setAdding("_")} data-testid="dob-add-record"><Plus size={18} /> Adicionar registo</button>
                <Link to={reportLink} className="dob-outline" data-testid="dob-action-report"><FileText size={18} /> Relatório da especialidade</Link>
                <button type="button" className="dob-outline" onClick={() => setSecao("orcamento")} data-testid="dob-open-budget"><Calculator size={18} /> Orçamento desta especialidade</button>
              </div>
            </section>
          </>}

          {/* Imagem 2 — detalhe: planta e camadas, medições, materiais, registos */}
          {secao && <>
            <section className="dob-card dob-card-pad dob-gap">
              <div className="dob-card-title"><span className="dob-tile"><Layers size={24} /></span><h2>{element || s.label}</h2></div>
              {kpis}
              <div className="dob-tabbar" role="tablist" aria-label="Informação da especialidade">
                {[...DETAIL_TABS, ...(mode === "tecnico" ? [["historico", "Histórico", History]] : [])].map(([k, l, TI]) =>
                  <button key={k} type="button" role="tab" aria-selected={secao === k} onClick={() => setSecao(k)} data-testid={`dob-tab-${k}`}><TI size={19} aria-hidden="true" /> {l}</button>)}
              </div>
              <div role="tabpanel" className="dob-gap">
                {secao === "plantas" && <>
                  {meds.length === 0 && mats.length === 0 && <p className="text-sm text-muted-foreground">Sem plantas nem camadas. <Link className="underline" to={tool("/plan", key)}>Adicionar planta</Link>.</p>}
                  {(meds.length > 0 || mats.length > 0) && (
                    <div className="dob-plan-grid">
                      <div><MeasureSketch m={firstMed?.measurement} planLink={tool("/plan", key)} />
                        {mode === "tecnico" && firstMed && <div className="mt-3"><Origin m={firstMed.measurement} /></div>}</div>
                      <div className="dob-layers-card">{mats.filter((x) => x.layers?.length).map((x) => <LayersBlock key={x.item_id} item={x} mode={mode} onValidate={validate} />)}
                        {!mats.some((x) => x.layers?.length) && <p className="text-sm text-muted-foreground p-3">Sem camadas registadas.</p>}</div>
                    </div>
                  )}
                  {(inferredLayers || sourceDoc) && (
                    <div className="dob-trama" data-testid="dob-origin">
                      <span className="flex items-center gap-2"><Info size={18} /> {inferredLayers ? "Trama detetada: confirmar material e composição." : "Origem da medição"}</span>
                      {sourceDoc && <span className="dob-doc-chip"><FileText size={15} /> {sourceDoc.replace(/ \(fictício\)$/, "")}{firstMed.measurement.page ? ` · página ${firstMed.measurement.page}` : ""}{firstMed.measurement.scale ? ` · ${firstMed.measurement.scale}` : ""}{firstMed.measurement.quantity != null ? ` · ${fmt(firstMed.measurement.quantity)} ${firstMed.measurement.unit}` : ""}</span>}
                    </div>
                  )}
                </>}
                {secao === "medicoes" && (meds.length === 0 ? <p className="text-sm text-muted-foreground">Sem medições. <button type="button" className="underline" onClick={() => setAdding("medicao")}>Medir área</button>.</p> :
                  meds.map((m) => <div key={m.item_id} className="dob-boxed dob-card-pad dob-gap"><div className="flex flex-wrap items-center gap-2"><p className="font-semibold flex-1">{m.title}</p><span className={`dob-pill dob-pill-${m.display_status}`}>{STATUS_TEXT[m.display_status]}</span></div>
                    <Origin m={m.measurement} />{mode === "tecnico" && <QuantitiesTable item={m} cat={cat} onSave={patchItem} />}</div>))}
                {secao === "orcamento" && <BudgetPanel chantierId={chantierId} specialty={key} specialtyLabel={s.short || s.label} measurements={meds} fase={fase} local={local} onChanged={reloadTree} />}
                {secao === "materiais" && (mats.length === 0 ? <p className="text-sm text-muted-foreground">Sem materiais registados.</p> :
                  mats.map((m) => <div key={m.item_id} className="dob-boxed dob-card-pad dob-gap" data-testid="dob-material">
                    <div className="flex flex-wrap items-center gap-2"><p className="font-semibold flex-1">{m.title}</p><span className={`dob-pill dob-pill-${m.validation}`}>{STATUS_TEXT[m.validation]}</span><span className="text-xs text-muted-foreground">{cat.sources[m.source]}</span></div>
                    {m.detail && <p className="text-sm">{m.detail}</p>}
                    {m.layers?.length ? <LayersBlock item={m} mode={mode} onValidate={validate} /> : m.validation === "por_confirmar" && <div className="flex gap-2"><button type="button" className="dob-ghost" onClick={() => validate(m, { action: "confirmar" })}>Confirmar</button><button type="button" className="dob-ghost" onClick={() => validate(m, { action: "rejeitar" })}>Rejeitar</button></div>}
                    <Link to={tool("/appro", key)} className="dob-hint underline w-fit"><ShoppingCart size={13} /> Pedir preço deste material</Link></div>))}
                {secao === "registos" && <><div className="dob-rows dob-boxed">{[...byKind("registo"), ...byKind("verificacao"), ...byKind("alteracao"), ...byKind("nota")].map((r) => <div key={r.item_id} className="dob-row"><div className="dob-row-main"><p>{r.title}</p><p>{[cat.item_kinds[r.kind], (r.created_at || "").slice(0, 10)].join(" · ")}</p></div><span className={`dob-pill dob-pill-${r.display_status}`}>{STATUS_TEXT[r.display_status]}</span></div>)}
                  {[...byKind("registo"), ...byKind("verificacao")].length === 0 && <p className="text-sm text-muted-foreground p-3">Sem registos.</p>}</div>
                  <Link to={tool("/suivi-chantier", key)} className="dob-ghost w-fit"><Camera size={16} /> Fotografias e relatórios de obra</Link></>}
                {secao === "historico" && <ol className="dob-rows dob-boxed" data-testid="dob-history">{items.flatMap((i) => (i.history || []).map((h) => ({ ...h, title: i.title }))).sort((a, b) => (b.at || "").localeCompare(a.at || "")).slice(0, 80).map((h, i) =>
                  <li key={i} className="dob-row"><div className="dob-row-main"><p>{h.title} — {h.action.replace(/_/g, " ")}</p><p>{(h.at || "").slice(0, 16).replace("T", " ")} · {h.by}{h.note ? ` · ${h.note}` : ""}</p></div></li>)}</ol>}
              </div>
            </section>
            <section className="dob-card dob-card-pad dob-before">
              <div className="dob-gap"><div className="dob-card-title"><span className="dob-tile dob-tile-sm"><ClipboardCheck size={20} /></span><h2>Antes de começar</h2></div>
                <div className="dob-plain-list" id="dob-pendencias">{checklist.map((i) => <div key={i.item_id} className="dob-row">{checkbox(i)}<p>{i.title}</p></div>)}
                  {checklist.length === 0 && <p className="text-sm text-muted-foreground">Sem pendências.</p>}</div></div>
              {data.dependencies.length > 0 && <div className="dob-before-links">{data.dependencies.map((d) => { const DI = specIcon(d.other); return <Link key={d.dep_id} to={`${base}/especialidade/${d.other}${qs()}`} className="dob-link-chip" data-testid={`dob-link-${d.other}`}><DI size={16} /> Ligação a {d.other_label.toLowerCase()}</Link>; })}</div>}
            </section>
          </>}
        </div>
        {assistant && (
          <div className="dob-aside">
            <AssistantPanel chantierId={chantierId} specialty={key} contextLine={ctxLine} fase={fase} local={local} intro={assistantIntro} quick={quick}
              onClose={() => setAssistant(false)} onPrepareReport={() => nav(reportLink)} />
            {secao && <Link to={reportLink} className="dob-primary dob-lg dob-report-btn" data-testid="dob-prepare-report"><FileText size={22} /> Relatório da especialidade</Link>}
          </div>
        )}
      </div>
      <ImpactDialog impact={impact} onCancel={() => setImpact(null)} onConfirm={() => patchItem(impact.item, impact.patch, true)} />
    </div>
  );
}
