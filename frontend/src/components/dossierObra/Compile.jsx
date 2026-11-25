import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { FileText, Eye, Check, ArrowLeft, AlertTriangle, Info, Download, FileSpreadsheet, FileArchive, FileType2, ShieldCheck, Layers } from "lucide-react";
import { api } from "@/lib/api";
import { AREA_ICONS, Breadcrumbs, PhaseLocalSelectors, errMsg, useDossierContext, Loading, withPaths } from "./common";

const FORMATS = [["pdf", "PDF", "Dossier completo", FileText], ["docx", "Word", "Relatório editável", FileType2], ["xlsx", "Excel", "Medições e custos", FileSpreadsheet], ["zip", "ZIP", "Dossier e anexos", FileArchive]];
const INCLUDES = [["medicoes", "Medições"], ["materiais", "Materiais e sistemas"], ["registos", "Registos"], ["fotografias", "Fotografias"], ["verificacoes", "Verificações"],
  ["alteracoes", "Alterações e histórico"], ["pendencias", "Pendências"], ["anexos", "Anexos"], ["financeiro", "Custos e informação financeira"]];

async function download(chantierId, em, fmt) {
  const res = await api.get(`/dossier-obra/${chantierId}/emissoes/${em.emission_id}/ficheiro`, { params: { formato: fmt }, responseType: "blob" });
  const cd = res.headers?.["content-disposition"] || "";
  const name = (cd.match(/filename="([^"]+)"/) || [])[1] || `dossier_v${em.version}.${fmt}`;
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url; a.download = name; document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

export function Compile({ ov, cat, mode }) {
  const { chantierId, fase, local, setCtx, base, qs } = useDossierContext();
  const [params] = useSearchParams();
  const espParam = params.get("esp");
  const [step, setStep] = useState(1);
  const [scope, setScope] = useState(params.get("scope") === "especialidade" && espParam ? "especialidade" : "global");
  const [chosen, setChosen] = useState(() => new Set(espParam ? [espParam] : ov.enabled));
  const [include, setInclude] = useState(new Set(["medicoes", "materiais", "registos", "fotografias", "verificacoes", "alteracoes", "pendencias", "anexos"]));
  const [recipient, setRecipient] = useState("dono_obra");
  const [content, setContent] = useState("validado_pendencias");
  const [formats, setFormats] = useState(new Set(["pdf"]));
  const [preview, setPreview] = useState(null);
  const [pstate, setPstate] = useState("idle");
  const [emissions, setEmissions] = useState([]);
  const [generated, setGenerated] = useState(null);
  const [busy, setBusy] = useState(false);

  const selection = useMemo(() => ({
    scope: scope === "global" && (fase || local) ? "fase_local" : scope,
    specialties: [...chosen], phases: fase ? [fase] : [], locations: local ? [local] : [],
    content, include: [...include], recipient,
  }), [scope, chosen, fase, local, content, include, recipient]);

  const loadEmissions = () => api.get(`/dossier-obra/${chantierId}/emissoes`).then(({ data }) => setEmissions(data.emissions)).catch(() => {});
  useEffect(() => { loadEmissions(); }, [chantierId]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!chosen.size) { setPreview(null); setPstate("empty"); return; }
    setPstate("loading");
    const t = setTimeout(() => api.post(`/dossier-obra/${chantierId}/compilar/previsualizar`, selection)
      .then(({ data }) => { setPreview(data); setPstate("ready"); }).catch((e) => { setPstate("error"); setPreview({ error: errMsg(e) }); }), 250);
    return () => clearTimeout(t);
  }, [chantierId, selection, chosen.size]);

  const toggle = (set, setter, k) => { const n = new Set(set); n.has(k) ? n.delete(k) : n.add(k); setter(n); };
  const toggleArea = (a) => { const keys = a.specialties.map((s) => s.key); const all = keys.every((k) => chosen.has(k)); const n = new Set(chosen); keys.forEach((k) => (all ? n.delete(k) : n.add(k))); setChosen(n); if (scope === "especialidade") setScope("global"); };
  const generate = async () => {
    if (!formats.size) { toast.error("Escolha pelo menos um formato."); return; }
    setBusy(true);
    try {
      const { data: em } = await api.post(`/dossier-obra/${chantierId}/emissoes`, selection);
      setGenerated(em); setStep(3); loadEmissions();
      for (const f of formats) { await download(chantierId, em, f); }
      toast.success(`Emissão versão ${String(em.version).padStart(2, "0")} guardada`);
    } catch (e) { toast.error(errMsg(e, "Não foi possível gerar o dossier.")); } finally { setBusy(false); }
  };

  const areas = ov.areas.filter((a) => a.specialties.length);
  const p = preview && !preview.error ? preview : null;
  return (
    <div className="grid gap-4 min-w-0" data-testid="dob-compile">
      <Breadcrumbs items={[{ label: "Dossier de obra", to: `${base}${qs()}` }, { label: "Documento final" }]} />
      <header className="dob-head">
        <div className="dob-title">
          <span className="dob-title-icon"><FileText size={28} aria-hidden="true" /></span>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2"><h1>{scope === "especialidade" ? "Relatório da especialidade" : "Compilar dossier de obra"}</h1>{ov.chantier.demo && <span className="dob-demo">Exemplo demonstrativo</span>}</div>
            <p className="dob-sub">Escolha o conteúdo e reveja antes de gerar. · {ov.chantier.name}</p>
          </div>
        </div>
        <div className="dob-context"><PhaseLocalSelectors phases={cat.phases} locations={withPaths(ov.config.locations)} fase={fase} local={local} onChange={setCtx} testPrefix="dob-compile" /></div>
      </header>
      <div className="dob-card dob-card-pad"><ol className="dob-steps" aria-label="Etapas da compilação">
        {[[1, "Selecionar conteúdo"], [2, "Rever"], [3, "Gerar"]].map(([n, l], i) => (
          <li key={n} className="inline-flex items-center gap-3">{i > 0 && <span className="dob-step-line" aria-hidden="true" />}
            <button type="button" className="dob-step" aria-current={step === n ? "step" : undefined} onClick={() => setStep(n === 3 && !generated ? 2 : n)} data-testid={`dob-step-${n}`}>
              <span className="dob-step-n">{step > n ? <Check size={14} /> : n}</span>{l}</button></li>))}
      </ol></div>

      <div className="dob-compile">
        <section className="dob-card dob-card-pad grid gap-3 content-start" aria-label="Conteúdo a incluir" data-testid="dob-compile-select">
          <h2 className="text-lg font-bold flex items-center gap-2"><Layers size={20} /> Conteúdo a incluir</h2>
          <div className="dob-seg w-fit" role="group" aria-label="Tipo de documento">
            <button type="button" aria-pressed={scope === "global"} onClick={() => setScope("global")}>Dossier global</button>
            <button type="button" aria-pressed={scope === "especialidade"} onClick={() => { setScope("especialidade"); if (chosen.size !== 1) setChosen(new Set([espParam || [...chosen][0] || ov.enabled[0]].filter(Boolean))); }}>Uma especialidade</button>
          </div>
          {areas.length === 0 && <p className="text-sm text-muted-foreground">Ainda não há especialidades ativas. <Link className="underline" to={`${base}${qs()}`}>Escolha por onde começar</Link>.</p>}
          {areas.map((a) => {
            const Icon = AREA_ICONS[a.key] || Layers;
            const keys = a.specialties.map((s) => s.key);
            const all = keys.every((k) => chosen.has(k));
            return (
              <fieldset key={a.key} className="grid gap-1">
                <label className="flex items-center gap-2 font-bold"><input type="checkbox" checked={all} ref={(el) => { if (el) el.indeterminate = !all && keys.some((k) => chosen.has(k)); }} onChange={() => toggleArea(a)} disabled={scope === "especialidade"} /><Icon size={18} /> {a.label.split(" e ")[0]}</label>
                <div className="grid gap-1 ms-6 border-s border-dashed ps-3">
                  {a.specialties.map((s) => <label key={s.key} className="flex items-center gap-2 text-sm">
                    <input type={scope === "especialidade" ? "radio" : "checkbox"} name="dob-esp" checked={chosen.has(s.key)} onChange={() => (scope === "especialidade" ? setChosen(new Set([s.key])) : toggle(chosen, setChosen, s.key))} data-testid={`dob-compile-${s.key}`} />
                    {s.label}{s.counts.pending > 0 && <span className="text-xs text-muted-foreground">· {s.counts.pending} pendente(s)</span>}</label>)}
                </div>
              </fieldset>
            );
          })}
          <fieldset className="grid sm:grid-cols-2 gap-1 border-t pt-3"><legend className="text-sm font-semibold mb-1">Tipos de informação</legend>
            {INCLUDES.filter(([k]) => mode === "tecnico" || ["registos", "fotografias", "financeiro", "pendencias", "anexos"].includes(k)).map(([k, l]) =>
              <label key={k} className="flex items-center gap-2 text-sm"><input type="checkbox" checked={include.has(k)} onChange={() => toggle(include, setInclude, k)} data-testid={`dob-include-${k}`} /> {l}</label>)}
          </fieldset>
          <label className="dob-field"><span>Destinatário</span><select value={recipient} onChange={(e) => setRecipient(e.target.value)} data-testid="dob-recipient">
            <option value="dono_obra">Dono de obra</option><option value="fiscalizacao">Fiscalização</option><option value="equipa">Equipa e subempreiteiros</option><option value="interno">Uso interno</option></select></label>
          <label className="dob-field"><span>Conteúdo</span><select value={content} onChange={(e) => setContent(e.target.value)} data-testid="dob-content">
            <option value="validado_pendencias">Informação validada e pendências</option><option value="validado">Só informação validada</option><option value="tudo">Tudo, incluindo rascunhos</option></select></label>
          {p?.summary?.pendente > 0 && <p className="dob-notice"><AlertTriangle size={18} /> <span><b>{p.summary.pendente} pendência(s) identificada(s)</b><br />Os itens por validar ficam assinalados no documento.</span></p>}
          {p?.warnings?.map((w) => <p key={w} className="dob-notice"><Info size={16} /> {w}</p>)}
        </section>

        <section className="dob-card dob-card-pad grid gap-3 content-start" aria-label="Pré-visualização" data-testid="dob-preview">
          <h2 className="text-lg font-bold flex items-center gap-2"><Eye size={20} /> Pré-visualização</h2>
          {pstate === "loading" && !p && <Loading>A preparar a pré-visualização…</Loading>}
          {pstate === "empty" && <p className="text-sm text-muted-foreground">Selecione pelo menos uma especialidade.</p>}
          {pstate === "error" && <p className="text-sm" role="alert">{preview?.error}</p>}
          {p && (
            <div className="dob-paper" aria-busy={pstate === "loading"}>
              <p className="font-bold" style={{ color: "#1f3d2b" }}>ConstruPilot</p>
              <h3 className="mt-3">{p.title.toUpperCase()}</h3>
              <p className="font-bold text-lg">{p.obra.name}</p>
              <p className="text-sm text-gray-600">Versão {String((emissions[0]?.version || 0) + 1).padStart(2, "0")} · {p.summary.pendente || p.summary.rascunho ? "Rascunho" : "Para emissão"} · {p.recipient}</p>
              <hr className="my-3" style={{ borderColor: "#1f3d2b" }} />
              <p className="font-bold mb-1">Índice de conteúdos</p>
              <ol className="text-sm">{p.toc.map((t, i) => <li key={t} className="flex gap-3 border-b py-1"><span className="font-bold" style={{ color: "#508662" }}>{String(i + 1).padStart(2, "0")}</span>{t}</li>)}</ol>
              <p className="text-xs text-gray-600 mt-3">{p.summary.items} registo(s) · {p.summary.validado} validado(s) · {p.summary.pendente} pendente(s) · {p.summary.rascunho} rascunho(s)</p>
              {mode === "tecnico" && p.chapters.map((ch) => <div key={ch.key} className="mt-3"><p className="font-bold">{ch.label}</p>{ch.specialties.map((s) => <p key={s.key} className="text-sm">{s.label}: {s.items.length} registo(s) — {s.status}</p>)}</div>)}
              <p className="text-xs text-gray-600 mt-3">{p.notice}</p>
            </div>
          )}
          {step === 1 && p && <button type="button" className="dob-ghost w-fit" onClick={() => setStep(2)} data-testid="dob-to-review"><Check size={16} /> Conteúdo selecionado — rever</button>}
        </section>
      </div>

      <section className="dob-card dob-card-pad grid gap-3" aria-label="Formato de exportação">
        <h2 className="font-bold">Formato de exportação</h2>
        <div className="dob-formats">
          {FORMATS.map(([k, l, d, Icon]) => <button key={k} type="button" className="dob-format" aria-pressed={formats.has(k)} onClick={() => toggle(formats, setFormats, k)} data-testid={`dob-format-${k}`}>
            <Icon size={26} aria-hidden="true" /><span><b>{l}</b><br /><span className="text-xs text-muted-foreground">{d}</span></span></button>)}
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Link to={`${base}${qs()}`} className="dob-ghost"><ArrowLeft size={16} /> Voltar às especialidades</Link>
          <p className="dob-hint flex-1"><Info size={14} /> A emissão mantém o histórico e as revisões incluídas. A compilação não equivale à validação técnica da obra.</p>
          <button type="button" className="dob-primary" disabled={busy || !p} onClick={generate} data-testid="dob-generate"><FileText size={18} /> {busy ? "A gerar…" : "Gerar dossier"}</button>
        </div>
        {generated && <p className="dob-notice" style={{ background: "#e3f3e8", borderColor: "#b9dfc6", color: "#1f6b3c" }} role="status" data-testid="dob-generated"><ShieldCheck size={18} /> Emissão versão {String(generated.version).padStart(2, "0")} guardada em {generated.created_at.slice(0, 16).replace("T", " ")}.</p>}
      </section>

      <section className="dob-card dob-card-pad grid gap-2" data-testid="dob-emissions">
        <h2 className="font-bold">Emissões anteriores</h2>
        {emissions.length === 0 ? <p className="text-sm text-muted-foreground">Ainda não há emissões.</p> :
          <div className="dob-rows">{emissions.map((e) => (
            <div key={e.emission_id} className="dob-row flex-wrap">
              <div className="dob-row-main"><p>Versão {String(e.version).padStart(2, "0")} · {e.title}</p><p>{e.created_at.slice(0, 16).replace("T", " ")} · {e.recipient} · {e.specialties.length} especialidade(s){e.revisions?.length ? ` · revisões: ${e.revisions.join(", ")}` : ""}</p></div>
              <div className="flex gap-1">{e.formats.map((f) => <button key={f} type="button" className="dob-ghost" style={{ minHeight: 32 }} onClick={() => download(chantierId, e, f).catch(() => toast.error("Transferência impossível"))} aria-label={`Descarregar ${f.toUpperCase()} da versão ${e.version}`}><Download size={14} /> {f.toUpperCase()}</button>)}</div>
            </div>))}</div>}
      </section>
    </div>
  );
}
