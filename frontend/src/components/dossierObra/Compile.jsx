import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { FileText, Eye, Check, ArrowLeft, AlertCircle, Info, Download, ShieldCheck, Layers, ChevronDown, ChevronUp, Image as ImageIcon, Coins, Link2, User, Home } from "lucide-react";
import { api } from "@/lib/api";
import { errMsg, useDossierContext, Loading, withPaths } from "./common";
import { AREA_SHORT, ModuleIcon } from "./icons";
import { Crumbs, DossierHeader, ContextSelects, FormatIcon } from "./layout";
import { AssistantPanel } from "./AssistantPanel";
import { CompleteBudget } from "./BudgetPanel";

const FORMATS = [["pdf", "PDF", "Dossier completo"], ["docx", "Word", "Relatório editável"], ["xlsx", "Excel", "Medições e custos"], ["zip", "ZIP", "Dossier e anexos"]];
// Grupos visíveis (como no ecrã de referência) → tipos de informação da API.
const GROUPS = [
  ["registos", "Registos e fotografias", ImageIcon, ["registos", "fotografias", "verificacoes"]],
  ["financeiro", "Custos e informação financeira", Coins, ["financeiro"]],
  ["pendencias", "Pendências e anexos", Link2, ["pendencias", "anexos", "alteracoes"]],
];

async function download(chantierId, em, fmt) {
  const res = await api.get(`/dossier-obra/${chantierId}/emissoes/${em.emission_id}/ficheiro`, { params: { formato: fmt }, responseType: "blob" });
  const cd = res.headers?.["content-disposition"] || "";
  const name = (cd.match(/filename="([^"]+)"/) || [])[1] || `dossier_v${em.version}.${fmt}`;
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function Box({ checked, onChange, label, test, indeterminate }) {
  return <input type="checkbox" className="dob-cb" checked={checked} aria-label={label} onChange={onChange} data-testid={test}
    ref={(el) => { if (el) el.indeterminate = !!indeterminate; }} />;
}

export function Compile({ ov, cat }) {
  const { chantierId, fase, local, setCtx, base, qs } = useDossierContext();
  const [params] = useSearchParams();
  const espParam = params.get("esp");
  const single = params.get("scope") === "especialidade" && espParam;
  const [chosen, setChosen] = useState(() => new Set(single ? [espParam] : ov.enabled));
  const [groups, setGroups] = useState(new Set(["registos", "pendencias"]));
  const [openAreas, setOpenAreas] = useState({});
  const [recipient, setRecipient] = useState("dono_obra");
  const [content, setContent] = useState("validado_pendencias");
  const [formats, setFormats] = useState(new Set(["pdf"]));
  const [preview, setPreview] = useState(null);
  const [pstate, setPstate] = useState("idle");
  const [emissions, setEmissions] = useState([]);
  const [generated, setGenerated] = useState(null);
  const [busy, setBusy] = useState(false);
  const step = generated ? 3 : 2;

  const include = useMemo(() => ["medicoes", "materiais", ...GROUPS.filter(([k]) => groups.has(k)).flatMap(([, , , inc]) => inc)], [groups]);
  const selection = useMemo(() => ({
    scope: single && chosen.size === 1 ? "especialidade" : (fase || local) ? "fase_local" : "global",
    specialties: [...chosen], phases: fase ? [fase] : [], locations: local ? [local] : [], content, include, recipient,
  }), [single, chosen, fase, local, content, include, recipient]);

  const loadEmissions = () => api.get(`/dossier-obra/${chantierId}/emissoes`).then(({ data }) => setEmissions(data.emissions)).catch(() => {});
  useEffect(() => { loadEmissions(); }, [chantierId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!chosen.size) { setPreview(null); setPstate("empty"); return undefined; }
    setPstate("loading");
    const t = setTimeout(() => api.post(`/dossier-obra/${chantierId}/compilar/previsualizar`, selection)
      .then(({ data }) => { setPreview(data); setPstate("ready"); }).catch((e) => { setPstate("error"); setPreview({ error: errMsg(e) }); }), 250);
    return () => clearTimeout(t);
  }, [chantierId, selection, chosen.size]);

  const toggle = (set, setter, k) => { const n = new Set(set); if (n.has(k)) n.delete(k); else n.add(k); setter(n); };
  const toggleArea = (a) => { const keys = a.specialties.map((s) => s.key); const all = keys.every((k) => chosen.has(k)); const n = new Set(chosen); keys.forEach((k) => (all ? n.delete(k) : n.add(k))); setChosen(n); };
  const generate = async () => {
    if (!formats.size) { toast.error("Escolha pelo menos um formato."); return; }
    setBusy(true);
    try {
      const { data: em } = await api.post(`/dossier-obra/${chantierId}/emissoes`, selection);
      setGenerated(em); loadEmissions();
      for (const f of formats) { await download(chantierId, em, f); }
      toast.success(`Emissão versão ${String(em.version).padStart(2, "0")} guardada`);
    } catch (e) { toast.error(errMsg(e, "Não foi possível gerar o dossier.")); } finally { setBusy(false); }
  };

  const areas = ov.areas.filter((a) => a.specialties.length);
  const p = preview && !preview.error ? preview : null;
  const nextVersion = String((emissions[0]?.version || 0) + 1).padStart(2, "0");
  return (
    <div className="dob-page" data-testid="dob-compile">
      <Crumbs items={[{ label: "Dossier de obra", to: `${base}${qs()}` }, { label: "Documento final" }]} />
      <DossierHeader icon={FileText} title={single && chosen.size === 1 ? "Relatório da especialidade" : "Compilar dossier de obra"} demo={ov.chantier.demo}
        subtitle="Escolha o conteúdo e reveja antes de gerar." extra={<p className="dob-sub-line"><Home size={17} aria-hidden="true" /> {ov.chantier.name.replace(/ \(exemplo demonstrativo\)$/, "")}</p>}
        side={<ContextSelects cat={cat} locations={withPaths(ov.config.locations)} fase={fase} local={local} onChange={setCtx} testPrefix="dob-compile" />} />

      <div className="dob-card dob-steps-card"><ol className="dob-steps" aria-label="Etapas da compilação">
        {[[1, "1. Selecionar conteúdo"], [2, "Rever"], [3, "Gerar"]].map(([n, l], i) => (
          <li key={n} className="dob-step-li">{i > 0 && <span className="dob-step-line" aria-hidden="true" />}
            <span className="dob-step" aria-current={step === n ? "step" : undefined} data-testid={`dob-step-${n}`}>
              <span className={`dob-step-n ${step > n ? "done" : ""}`}>{step > n ? <Check size={15} /> : n}</span>{l}</span></li>))}
      </ol></div>

      <div className="dob-compile-grid">
        <section className="dob-card dob-card-pad dob-gap" aria-label="Conteúdo a incluir" data-testid="dob-compile-select">
          <div className="dob-card-title"><span className="dob-tile dob-tile-sm"><Layers size={22} /></span><h2>Conteúdo a incluir</h2></div>
          {areas.length === 0 && <p className="text-sm text-muted-foreground">Ainda não há especialidades ativas. <Link className="underline" to={`${base}${qs()}`}>Escolha por onde começar</Link>.</p>}
          <div className="dob-tree-box">
            {areas.map((a) => {
              const keys = a.specialties.map((s) => s.key);
              const all = keys.every((k) => chosen.has(k));
              const some = keys.some((k) => chosen.has(k));
              const isOpen = openAreas[a.key] ?? true;
              return (
                <div key={a.key} className="dob-tree-group">
                  <div className="dob-tree-row dob-tree-head">
                    <Box checked={all} indeterminate={!all && some} onChange={() => toggleArea(a)} label={AREA_SHORT[a.key]} />
                    <ModuleIcon area={a.key} size={14} tile={26} /><span className="flex-1">{AREA_SHORT[a.key]}</span>
                    <button type="button" aria-expanded={isOpen} aria-label={`${isOpen ? "Recolher" : "Expandir"} ${AREA_SHORT[a.key]}`} onClick={() => setOpenAreas({ ...openAreas, [a.key]: !isOpen })}>{isOpen ? <ChevronUp size={18} /> : <ChevronDown size={18} />}</button>
                  </div>
                  {isOpen && <div className="dob-tree-children">{a.specialties.map((s) => (
                    <label key={s.key} className="dob-tree-row">
                      <Box checked={chosen.has(s.key)} onChange={() => toggle(chosen, setChosen, s.key)} label={s.label} test={`dob-compile-${s.key}`} />
                      <ModuleIcon k={s.key} area={s.area} size={12} tile={22} /><span>{s.short || s.label}</span>{s.counts.pending > 0 && <small className="text-muted-foreground">· {s.counts.pending} pend.</small>}
                    </label>))}</div>}
                </div>
              );
            })}
          </div>
          {GROUPS.map(([k, l, GI]) => (
            <label key={k} className="dob-tree-row dob-tree-head dob-group-row">
              <Box checked={groups.has(k)} onChange={() => toggle(groups, setGroups, k)} label={l} test={`dob-include-${k}`} /><GI size={20} aria-hidden="true" /><span>{l}</span>
            </label>))}
          <div className="dob-form-row"><span>Destinatário</span><label className="dob-pick dob-pick-full"><User size={18} aria-hidden="true" />
            <span>{{ dono_obra: "Dono de obra", fiscalizacao: "Fiscalização", equipa: "Equipa e subempreiteiros", interno: "Uso interno" }[recipient]}</span><ChevronDown size={18} aria-hidden="true" />
            <select value={recipient} onChange={(e) => setRecipient(e.target.value)} data-testid="dob-recipient" aria-label="Destinatário">
              <option value="dono_obra">Dono de obra</option><option value="fiscalizacao">Fiscalização</option><option value="equipa">Equipa e subempreiteiros</option><option value="interno">Uso interno</option></select></label></div>
          <div className="dob-form-row"><span>Conteúdo</span><label className="dob-pick dob-pick-full"><Layers size={18} aria-hidden="true" />
            <span>{{ validado_pendencias: "Informação validada e pendências", validado: "Só informação validada", tudo: "Tudo, incluindo rascunhos" }[content]}</span><ChevronDown size={18} aria-hidden="true" />
            <select value={content} onChange={(e) => setContent(e.target.value)} data-testid="dob-content" aria-label="Conteúdo">
              <option value="validado_pendencias">Informação validada e pendências</option><option value="validado">Só informação validada</option><option value="tudo">Tudo, incluindo rascunhos</option></select></label></div>
          {p?.summary?.pendente > 0 && <div className="dob-pend-notice"><AlertCircle size={26} aria-hidden="true" /><div><b>{p.summary.pendente} pendências identificadas</b><p>Os itens por validar ficam assinalados no documento.</p></div></div>}
          {p?.warnings?.map((w) => <p key={w} className="dob-pend-notice"><Info size={18} /> {w}</p>)}
        </section>

        <section className="dob-card dob-card-pad dob-gap" aria-label="Pré-visualização" data-testid="dob-preview">
          <div className="dob-card-title"><Eye size={24} aria-hidden="true" /><h2>Pré-visualização</h2></div>
          <div className="dob-paper-frame">
            {pstate === "loading" && !p && <Loading>A preparar a pré-visualização…</Loading>}
            {pstate === "empty" && <p className="text-sm text-muted-foreground p-6">Selecione pelo menos uma especialidade.</p>}
            {pstate === "error" && <p className="text-sm p-6" role="alert">{preview?.error}</p>}
            {p && (
              <div className="dob-paper" aria-busy={pstate === "loading"}>
                <p className="dob-paper-brand"><img src="/construpilot-icon.png" alt="" width="26" height="26" /> Constru<span>Pilot</span></p>
                <h3>{p.title.toUpperCase()}</h3>
                <p className="dob-paper-name">{p.obra.name.replace(/ \(exemplo demonstrativo\)$/, "")}</p>
                <p className="dob-paper-ver">Versão {nextVersion} · {p.summary.pendente || p.summary.rascunho ? "Rascunho" : "Para emissão"}</p>
                <p className="dob-paper-toc-title">Índice de conteúdos</p>
                <ol className="dob-paper-toc">{p.toc.map((t, i) => <li key={t}><b>{String(i + 1).padStart(2, "0")}</b>{t === "Resumo" ? "Resumo da obra" : t.replace(/ e elementos construtivos| e instalações/, "")}</li>)}</ol>
              </div>
            )}
          </div>
        </section>

        <div className="dob-aside">
          <AssistantPanel chantierId={chantierId} specialty="_compilacao" contextLine="Compilação" compact intro="Posso ajudar a rever o conteúdo e identificar informação em falta." />
        </div>
      </div>

      <CompleteBudget chantierId={chantierId} specialties={[...chosen]} />
      <section className="dob-card dob-formats-card" aria-label="Formato de exportação">
        <h2>Formato de exportação</h2>
        <div className="dob-formats">
          {FORMATS.map(([k, l, d]) => <button key={k} type="button" className="dob-format" aria-pressed={formats.has(k)} onClick={() => toggle(formats, setFormats, k)} data-testid={`dob-format-${k}`}>
            <FormatIcon f={k} size={28} /><span><b>{l}</b><small>{d}</small></span></button>)}
        </div>
      </section>
      <section className="dob-card dob-footer-bar">
        <Link to={`${base}${qs()}`} className="dob-outline"><ArrowLeft size={18} /> Voltar às especialidades</Link>
        <p className="dob-hint flex-1"><Info size={16} /> A emissão mantém o histórico e as revisões incluídas.</p>
        <button type="button" className="dob-primary dob-lg" disabled={busy || !p} onClick={generate} data-testid="dob-generate"><FileText size={20} /> {busy ? "A gerar…" : "Gerar dossier"}</button>
      </section>
      {generated && <p className="dob-ok" role="status" data-testid="dob-generated"><ShieldCheck size={18} /> Emissão versão {String(generated.version).padStart(2, "0")} guardada em {generated.created_at.slice(0, 16).replace("T", " ")}. A compilação não equivale à validação técnica da obra.</p>}

      <section className="dob-card dob-card-pad dob-gap" data-testid="dob-emissions">
        <h2 className="dob-h2">Emissões anteriores</h2>
        {emissions.length === 0 ? <p className="text-sm text-muted-foreground">Ainda não há emissões.</p> :
          <div className="dob-rows dob-boxed">{emissions.map((e) => (
            <div key={e.emission_id} className="dob-row flex-wrap">
              <div className="dob-row-main"><p>Versão {String(e.version).padStart(2, "0")} · {e.title}</p><p>{e.created_at.slice(0, 16).replace("T", " ")} · {e.recipient} · {e.specialties.length} especialidade(s){e.revisions?.length ? ` · revisões: ${e.revisions.join(", ")}` : ""}</p></div>
              <div className="flex gap-1">{e.formats.map((f) => <button key={f} type="button" className="dob-ghost dob-sm" onClick={() => download(chantierId, e, f).catch(() => toast.error("Transferência impossível"))} aria-label={`Descarregar ${f.toUpperCase()} da versão ${e.version}`}><Download size={14} /> {f.toUpperCase()}</button>)}</div>
            </div>))}</div>}
      </section>
    </div>
  );
}
