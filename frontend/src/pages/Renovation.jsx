import React, { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, eur } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";
import {
  Leaf, Plus, ArrowRight, ArrowLeft, Trash2, FileText, AlertTriangle,
  Info, CheckCircle2, HelpCircle, Gauge, Hammer, Mic, Upload, Download, Sparkles, Ruler,
  PiggyBank, Landmark, Loader2,
} from "lucide-react";

const STEPS = ["Descrever", "Compreender", "Comparar", "Preparar"];
const ASSESS_STYLE = {
  "provavelmente com perdas": "text-red-600 border-red-300 bg-red-50",
  "a verificar": "text-amber-600 border-amber-300 bg-amber-50",
  "a peritar": "text-amber-600 border-amber-300 bg-amber-50",
  "correto (declarado)": "text-emerald-600 border-emerald-300 bg-emerald-50",
};

export default function Renovation() {
  const nav = useNavigate();
  const [projects, setProjects] = useState([]);
  const [fieldsSpec, setFieldsSpec] = useState([]);
  const [project, setProject] = useState(null);
  const [inputs, setInputs] = useState({});
  const [step, setStep] = useState(0);
  const [baseline, setBaseline] = useState(null);
  const [missing, setMissing] = useState(null);
  const [scenarios, setScenarios] = useState([]);
  const [activeScenario, setActiveScenario] = useState(null);
  const [busy, setBusy] = useState(false);
  const [freeText, setFreeText] = useState("");
  const [listening, setListening] = useState(false);
  const recognitionRef = React.useRef(null);
  const [plansList, setPlansList] = useState([]);
  const [selPlan, setSelPlan] = useState("");
  const [dpeNumber, setDpeNumber] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const [pl, qs] = await Promise.all([
          api.get("/renovation/projects"),
          api.get("/renovation/questionnaire"),
        ]);
        setProjects(pl.data.projects || []);
        setFieldsSpec(qs.data.fields || []);
      } catch { /* non connecté */ }
    })();
  }, []);

  const sections = useMemo(() => {
    const map = {};
    for (const f of fieldsSpec) (map[f.section] = map[f.section] || []).push(f);
    return map;
  }, [fieldsSpec]);

  const openProject = async (pid) => {
    setBusy(true);
    try {
      const { data } = await api.get(`/renovation/projects/${pid}`);
      setProject(data);
      setInputs(data.inputs || {});
      setBaseline(data.baseline || null);
      setScenarios(data.scenarios || []);
      setStep(0);
      try { const r = await api.get("/renovation/plans"); setPlansList(r.data.plans || []); } catch { /* */ }
    } catch { toast.error("Abertura impossível"); }
    finally { setBusy(false); }
  };

  const pullSurfaces = async () => {
    if (!selPlan || !project) { toast.error("Escolha uma planta"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${project.project_id}/pull-surfaces`, { plan_id: selPlan });
      const { data: fresh } = await api.get(`/renovation/projects/${project.project_id}`);
      setInputs(fresh.inputs || {}); setProject(fresh);
      toast.success(`${data.count} área(s) recuperada(s) da planta (estado medido)`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Recuperação impossível"); }
    finally { setBusy(false); }
  };

  const createProject = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/renovation/projects", { title: "Novo projeto de reabilitação", bien_type: "maison" });
      setProjects((p) => [{ ...data }, ...p]);
      await openProject(data.project_id);
      toast.success("Projeto criado");
    } catch { toast.error("Criação impossível"); }
    finally { setBusy(false); }
  };

  const deleteProject = async (pid) => {
    try {
      await api.delete(`/renovation/projects/${pid}`);
      setProjects((p) => p.filter((x) => x.project_id !== pid));
      if (project?.project_id === pid) setProject(null);
      toast.success("Projeto eliminado");
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const setField = (path, value, unknown = false) => {
    setInputs((s) => ({ ...s, [path]: { ...(s[path] || {}), value: unknown ? null : value, status: unknown ? "inconnu" : "déclaré" } }));
  };

  const applyProposals = (proposals) => {
    setInputs((s) => {
      const next = { ...s };
      for (const pr of proposals) next[pr.path] = { value: pr.value, status: pr.status || "déclaré", source: pr.source || "ia" };
      return next;
    });
  };

  const describeWithAI = async () => {
    if (!project || !freeText.trim()) { toast.error("Descreva primeiro o edifício"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${project.project_id}/describe`, { text: freeText });
      if (!data.count) { toast.message("Nenhum dado reconhecido — precise a sua descrição"); }
      else { applyProposals(data.proposals); toast.success(`${data.count} campo(s) pré-preenchido(s) — a confirmar`); }
    } catch { toast.error("Extração impossível"); }
    finally { setBusy(false); }
  };

  const toggleDictation = () => {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast.error("Ditado não suportado por este navegador"); return; }
    if (listening) { recognitionRef.current?.stop(); setListening(false); return; }
    const rec = new SR();
    rec.lang = "pt-PT"; rec.continuous = true; rec.interimResults = false;
    rec.onresult = (e) => {
      let t = "";
      for (let i = e.resultIndex; i < e.results.length; i++) t += e.results[i][0].transcript + " ";
      setFreeText((prev) => (prev ? prev + " " : "") + t.trim());
    };
    rec.onend = () => setListening(false);
    rec.onerror = () => setListening(false);
    recognitionRef.current = rec; rec.start(); setListening(true);
  };

  const importDpe = async (fileList) => {
    const f = fileList?.[0];
    if (!f || !project) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", f);
      const { data } = await api.post(`/renovation/projects/${project.project_id}/import-dpe`, fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      const { data: fresh } = await api.get(`/renovation/projects/${project.project_id}`);
      setInputs(fresh.inputs || {});
      setProject(fresh);
      if (data.ademe) {
        const d = data.dpe || {};
        toast.success(`N.º de certificado energético detetado (${data.numero_dpe}) — certificado energético oficial importado: ${d.etiquette_energie}/${d.etiquette_climat}${(data.audits || []).length ? ` · ${data.audits.length} audit(s)` : ""}`);
      } else {
        const cls = data.imported_class ? ` · classe lida: ${data.imported_class}` : "";
        toast.success(`${data.count} campo(s) importado(s) do documento${cls}`);
      }
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível importar"); }
    finally { setBusy(false); }
  };

  const importDpeNumber = async () => {
    if (!project || !dpeNumber.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${project.project_id}/import-dpe-number`, { numero_dpe: dpeNumber.trim() });
      const { data: fresh } = await api.get(`/renovation/projects/${project.project_id}`);
      setInputs(fresh.inputs || {});
      setProject(fresh);
      const d = data.dpe || {};
      toast.success(`DPE ${d.numero_dpe} importado — ${d.etiquette_energie}/${d.etiquette_climat}${(data.audits || []).length ? ` · ${data.audits.length} audit(s)` : ""}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Número de certificado energético não encontrado nos dados abertos"); }
    finally { setBusy(false); }
  };

  const auditToDevis = async (auditIndex, stepIndex) => {
    if (!project) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${project.project_id}/audit-to-devis`, { audit_index: auditIndex, step_index: stepIndex });
      toast.success(data.message || "Orçamento criado a partir do cenário de auditoria");
      if (data.doc_id) nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível criar o orçamento"); }
    finally { setBusy(false); }
  };

  const importDpeImmeuble = async () => {
    if (!project) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${project.project_id}/import-dpe-immeuble`, {});
      const { data: fresh } = await api.get(`/renovation/projects/${project.project_id}`);
      setProject(fresh);
      toast.success(data.message || "Certificado energético do edifício importado (partes comuns)");
    } catch (e) { toast.error(e?.response?.data?.detail || "Certificado energético do edifício indisponível"); }
    finally { setBusy(false); }
  };

  const downloadReport = async () => {
    if (!project) return;
    try {
      const res = await api.get(`/renovation/projects/${project.project_id}/report.pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([res.data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `RenoPilot_${(project.title || "relatório").replace(/\s+/g, "_")}.pdf`;
      document.body.appendChild(a); a.click(); a.remove(); URL.revokeObjectURL(url);
    } catch { toast.error("Relatório indisponível"); }
  };


  const saveInputs = async () => {
    if (!project) return;
    setBusy(true);
    try {
      const payload = fieldsSpec
        .filter((f) => inputs[f.path] !== undefined)
        .map((f) => ({ path: f.path, value: inputs[f.path]?.value ?? null, status: inputs[f.path]?.status || "déclaré" }));
      await api.patch(`/renovation/projects/${project.project_id}/inputs`, { fields: payload });
      toast.success("Dados guardados");
    } catch { toast.error("Não foi possível guardar"); }
    finally { setBusy(false); }
  };

  const goUnderstand = async () => {
    if (!project) return;
    setBusy(true);
    try {
      await saveInputs();
      const [b, m] = await Promise.all([
        api.post(`/renovation/projects/${project.project_id}/analyze-baseline`),
        api.get(`/renovation/projects/${project.project_id}/missing-data`),
      ]);
      setBaseline(b.data); setMissing(m.data); setStep(1);
    } catch { toast.error("Análise impossível"); }
    finally { setBusy(false); }
  };

  const goCompare = async () => {
    if (!project) return;
    setBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${project.project_id}/scenarios`);
      setScenarios(data.scenarios || []); setStep(2);
    } catch { toast.error("Geração dos cenários impossível"); }
    finally { setBusy(false); }
  };

  const createEstimate = async (key) => {
    setBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${project.project_id}/scenarios/${key}/create-estimate`);
      toast.success("Orçamento criado no editor ConstruPilot");
      if (data.doc_id) nav(`/devis-editeur/${data.doc_id}`);
    } catch { toast.error("Não foi possível criar o orçamento"); }
    finally { setBusy(false); }
  };

  // ------- Écran liste de projets -------
  if (!project) {
    return (
      <div className="max-w-5xl mx-auto px-4 py-8" data-testid="reno-home">
        <div className="flex items-center gap-3 mb-2">
          <div className="h-11 w-11 rounded-lg bg-emerald-600 text-white grid place-items-center"><Leaf className="h-6 w-6" /></div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">RenoPilot — Reabilitação energética</h1>
            <p className="text-sm text-muted-foreground">Descreva o seu edifício. O ConstruPilot prepara o seu percurso de reabilitação: trabalhos, quantidades e orçamento.</p>
          </div>
        </div>
        <div className="rounded-md border border-amber-300 bg-amber-50 text-amber-800 text-xs p-3 my-4 flex gap-2" data-testid="reno-disclaimer">
          <Info className="h-4 w-4 shrink-0 mt-0.5" />
          <span>Estimativa de reabilitação — <b>não substitui um certificado energético nem uma auditoria regulamentar</b>. O cálculo energético (classe, kWh) requer um motor certificado ainda não ligado: nesta fase só é produzida uma análise qualitativa.</span>
        </div>
        <Button onClick={createProject} disabled={busy} className="rounded-md gap-2 bg-emerald-600 hover:bg-emerald-700" data-testid="reno-new-project">
          <Plus className="h-4 w-4" /> Novo projeto
        </Button>
        <div className="grid gap-2 mt-6">
          {projects.length === 0 && <p className="text-sm text-muted-foreground">Nenhum projeto por agora.</p>}
          {projects.map((p) => (
            <Card key={p.project_id} className="p-3 flex items-center justify-between hover:border-emerald-400 transition" data-testid={`reno-project-${p.project_id}`}>
              <button className="text-left flex-1" onClick={() => openProject(p.project_id)}>
                <p className="font-medium text-sm">{p.title}</p>
                <p className="text-[11px] text-muted-foreground">Estado: {p.status} · maj {new Date(p.updated_at).toLocaleDateString("pt-PT")}</p>
              </button>
              <div className="flex gap-1">
                <Button size="sm" variant="ghost" onClick={() => openProject(p.project_id)} className="h-8 gap-1 text-xs">Abrir <ArrowRight className="h-3 w-3" /></Button>
                <Button size="icon" variant="ghost" onClick={() => deleteProject(p.project_id)} className="h-8 w-8 text-red-500" data-testid={`reno-delete-${p.project_id}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  // ------- Éditeur projet (wizard) -------
  return (
    <div className="max-w-5xl mx-auto px-4 py-6" data-testid="reno-editor">
      <div className="flex items-center justify-between mb-4">
        <button onClick={() => setProject(null)} className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1" data-testid="reno-back">
          <ArrowLeft className="h-4 w-4" /> Os meus projetos
        </button>
        <div className="flex items-center gap-2">
          <h2 className="font-semibold truncate">{project.title}</h2>
          <Button size="sm" variant="outline" onClick={downloadReport} className="rounded-md gap-1 h-8 text-xs" data-testid="reno-report-pdf">
            <Download className="h-3.5 w-3.5" /> Relatório PDF
          </Button>
        </div>
      </div>

      {/* Stepper */}
      <div className="flex items-center gap-1 mb-6 text-xs">
        {STEPS.map((s, i) => (
          <React.Fragment key={s}>
            <button onClick={() => i <= step && setStep(i)}
                    className={`px-3 py-1.5 rounded-full border ${i === step ? "bg-emerald-600 text-white border-emerald-600" : i < step ? "border-emerald-300 text-emerald-700" : "border-border text-muted-foreground"}`}
                    data-testid={`reno-step-${i}`}>
              {i + 1}. {s}
            </button>
            {i < STEPS.length - 1 && <div className="h-px w-4 bg-border" />}
          </React.Fragment>
        ))}
      </div>

      {/* Étape Décrire */}
      {step === 0 && (
        <div className="grid gap-5" data-testid="reno-describe">
          <Card className="p-4 border-sky-200 bg-sky-50/40" data-testid="reno-dpe-official">
            <p className="overline text-sky-700 mb-2 flex items-center gap-1"><FileText className="h-3.5 w-3.5" /> Estado atual oficial — Número do certificado energético (ADENE)</p>
            <div className="flex flex-wrap items-center gap-2">
              <Input value={dpeNumber} onChange={(e) => setDpeNumber(e.target.value.toUpperCase())}
                     placeholder="Ex : 2606E0017721A" className="h-8 w-56 font-mono text-sm" data-testid="reno-dpe-number-input" />
              <Button size="sm" onClick={importDpeNumber} disabled={busy || !dpeNumber.trim()}
                      className="rounded-sm gap-1 h-8 bg-sky-600 hover:bg-sky-700" data-testid="reno-dpe-number-fetch">
                <Download className="h-3.5 w-3.5" /> Obter o certificado energético oficial
              </Button>
              <span className="text-[10px] text-muted-foreground">Número indicado na 1.ª página do certificado energético. Dados oficiais (não vinculativos).</span>
            </div>

            {project.ademe_dpe && (
              <div className="mt-3 grid gap-3" data-testid="reno-dpe-state">
                <div className="flex flex-wrap items-center gap-2 text-xs">
                  <EtiquetteBadge letter={project.ademe_dpe.etiquette_energie} kind="energia" />
                  <EtiquetteBadge letter={project.ademe_dpe.etiquette_climat} kind="climat" />
                  <Badge variant="outline">{project.ademe_dpe.conso_ep_m2} kWh/m²/an (EP)</Badge>
                  <Badge variant="outline">{project.ademe_dpe.ges_m2} kgCO₂/m²/ano</Badge>
                  {project.ademe_dpe.cout_annuel && <Badge variant="outline">≈ {eur(project.ademe_dpe.cout_annuel)}/an</Badge>}
                </div>
                <div className="text-[11px] text-muted-foreground grid sm:grid-cols-2 gap-x-4">
                  <p><b className="text-foreground">Imóvel:</b> {project.ademe_dpe.type_batiment} · {project.ademe_dpe.surface_m2} m² · {project.ademe_dpe.periode_construction}</p>
                  <p><b className="text-foreground">Morada:</b> {project.ademe_dpe.adresse}</p>
                  <p><b className="text-foreground">Chauffage :</b> {project.ademe_dpe.chauffage_energie} — {project.ademe_dpe.chauffage_desc}</p>
                  <p><b className="text-foreground">AQS:</b> {project.ademe_dpe.ecs_generateur || "—"}</p>
                  <p><b className="text-foreground">Isolamento das paredes:</b> {project.ademe_dpe.isolation?.murs || "—"} · <b className="text-foreground">menuiseries :</b> {project.ademe_dpe.isolation?.menuiseries || "—"}</p>
                  <p><b className="text-foreground">DPE n° :</b> <span className="font-mono">{project.ademe_dpe.numero_dpe}</span> ({project.ademe_dpe.date_dpe})</p>
                </div>

                {project.ademe_dpe?.numero_dpe_immeuble && !project.ademe_dpe_immeuble && (
                  <Button size="sm" variant="outline" onClick={importDpeImmeuble} disabled={busy}
                          className="h-7 w-fit text-[11px] gap-1 border-violet-300 text-violet-700" data-testid="reno-import-immeuble">
                    <FileText className="h-3 w-3" /> Importar o certificado energético do edifício (partes comuns)
                  </Button>
                )}
                {project.ademe_dpe_immeuble && (
                  <div className="rounded-md border border-violet-200 bg-violet-50/40 p-3" data-testid="reno-immeuble-card">
                    <p className="text-xs font-semibold text-violet-700 mb-2">Comparação fração / partes comuns (condomínio)</p>
                    <div className="grid grid-cols-2 gap-3">
                      {[["Fração (privada)", project.ademe_dpe], ["Edifício (partes comuns)", project.ademe_dpe_immeuble]].map(([t, dd]) => (
                        <div key={t} className="rounded-md border border-border bg-white p-2">
                          <p className="text-[10px] font-semibold text-muted-foreground mb-1">{t}</p>
                          <div className="flex items-center gap-1 mb-1">
                            <EtiquetteBadge letter={dd?.etiquette_energie} small />
                            <EtiquetteBadge letter={dd?.etiquette_climat} small />
                          </div>
                          <p className="text-[11px]">{dd?.conso_ep_m2 ?? "—"} kWh/m²·an · {dd?.ges_m2 ?? "—"} kgCO₂</p>
                          <p className="text-[10px] text-muted-foreground">{dd?.surface_m2 ?? "—"} m² · n° {dd?.numero_dpe}</p>
                        </div>
                      ))}
                    </div>
                    <p className="text-[10px] text-muted-foreground mt-1">Classes apresentadas separadamente — nunca em média. Útil para enquadrar as obras comuns vs privadas.</p>
                  </div>
                )}

                {(project.ademe_audits || []).length > 0 && (
                  <div className="rounded-md border border-sky-200 bg-white p-3" data-testid="reno-audit-scenarios">
                    <p className="text-xs font-semibold text-sky-700 mb-2 flex items-center gap-1"><Hammer className="h-3.5 w-3.5" /> Cenários de reabilitação oficiais (auditoria energética)</p>
                    {(project.ademe_audits || []).map((a, ai) => (
                      <div key={a.n_audit} className="mb-2">
                        <p className="text-[10px] text-muted-foreground mb-1">Auditoria {a.n_audit} · {a.date}</p>
                        <div className="space-y-1">
                          {a.steps.map((s, i) => (
                            <div key={i} className="flex items-start justify-between gap-2 text-[11px] border-b border-sky-100 pb-1" data-testid={`reno-audit-step-${i}`}>
                              <span className="flex items-center gap-1.5">
                                <EtiquetteBadge letter={s.etiquette_energie} small />
                                <span className="capitalize">{s.etape}</span>
                                {s.travaux ? <span className="text-muted-foreground">— {s.travaux}</span> : null}
                              </span>
                              <span className="shrink-0 flex items-center gap-2">
                                <span className="font-medium">{s.cout_travaux ? `${eur(s.cout_travaux)}` : "—"}{s.gain_relatif_ep != null ? ` · ${Math.round(Math.abs(s.gain_relatif_ep) * 100)}% conso` : ""}</span>
                                {s.cout_travaux ? (
                                  <Button size="sm" variant="outline" disabled={busy} onClick={() => auditToDevis(ai, i)}
                                          className="h-6 px-2 text-[10px] rounded-sm gap-1" data-testid={`reno-audit-to-devis-${i}`}>
                                    <FileText className="h-3 w-3" /> Orçamento
                                  </Button>
                                ) : null}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    ))}
                    <p className="text-[10px] text-amber-700 mt-1">Dados oficiais — retomados tal como estão, não vinculativos.</p>
                  </div>
                )}
              </div>
            )}
          </Card>
          <Card className="p-4 border-emerald-200 bg-emerald-50/40">
            <p className="overline text-emerald-700 mb-2 flex items-center gap-1"><Sparkles className="h-3.5 w-3.5" /> Descrever em texto livre ou importar um documento</p>
            <textarea value={freeText} onChange={(e) => setFreeText(e.target.value)}
                      rows={3} data-testid="reno-freetext"
                      placeholder="Ex.: Moradia de 1965, 110 m² em 2 pisos, paredes de tijolo sem isolamento, 8 janelas de vidro simples, aquecimento a gás, ventilação natural, orçamento 30 000 €…"
                      className="w-full rounded-sm border border-border bg-background p-2 text-sm" />
            <div className="flex flex-wrap items-center gap-2 mt-2">
              <Button size="sm" onClick={describeWithAI} disabled={busy} className="rounded-sm gap-1 bg-emerald-600 hover:bg-emerald-700" data-testid="reno-describe-ai">
                <Sparkles className="h-3.5 w-3.5" /> Preencher com a IA
              </Button>
              <Button size="sm" variant={listening ? "default" : "outline"} onClick={toggleDictation} className={`rounded-sm gap-1 ${listening ? "bg-red-600 hover:bg-red-700 animate-pulse" : ""}`} data-testid="reno-dictation">
                <Mic className="h-3.5 w-3.5" /> {listening ? "A ditar… (parar)" : "Ditar"}
              </Button>
              <label className="inline-flex items-center gap-1 h-8 px-3 rounded-sm border border-border text-xs cursor-pointer hover:bg-secondary" data-testid="reno-import-dpe-label">
                <Upload className="h-3.5 w-3.5" /> Importar um certificado energético / auditoria (PDF/XML)
                <input type="file" accept=".pdf,.xml" className="hidden" data-testid="reno-import-dpe"
                       onChange={(e) => importDpe(e.target.files)} />
              </label>
              <span className="text-[10px] text-muted-foreground">Os campos pré-preenchidos continuam <b>a confirmar</b>.</span>
            </div>
            <div className="flex flex-wrap items-center gap-2 mt-2 border-t border-emerald-200 pt-2">
              <span className="text-[11px] text-muted-foreground">A partir do Editor de plantas:</span>
              <select value={selPlan} onChange={(e) => setSelPlan(e.target.value)}
                      data-testid="reno-plan-select"
                      className="h-8 rounded-sm border border-border bg-background px-2 text-xs max-w-[220px]">
                <option value="">— escolher uma planta medida —</option>
                {plansList.map((pl) => <option key={pl.plan_id} value={pl.plan_id}>{pl.name}</option>)}
              </select>
              <Button size="sm" variant="outline" onClick={pullSurfaces} disabled={busy || !selPlan}
                      className="rounded-sm gap-1 h-8 text-xs" data-testid="reno-pull-surfaces">
                <Ruler className="h-3.5 w-3.5" /> Recuperar as áreas
              </Button>
              <a href="/plan" className="text-[11px] text-emerald-700 hover:underline">Abrir o Editor de plantas →</a>
            </div>
            {(project.documents || []).length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5" data-testid="reno-imported-docs">
                {(project.documents || []).map((d) => (
                  <Badge key={d.doc_id} variant="outline" className="text-[10px] rounded-sm">
                    {d.filename}{d.imported_class ? ` · classe lida ${d.imported_class} (document)` : ""}
                  </Badge>
                ))}
              </div>
            )}
          </Card>
          {Object.entries(sections).map(([section, fs]) => (
            <Card key={section} className="p-4">
              <p className="overline text-emerald-700 mb-3">{section}</p>
              <div className="grid sm:grid-cols-2 gap-3">
                {fs.map((f) => {
                  const ev = inputs[f.path] || {};
                  const unknown = ev.status === "inconnu";
                  return (
                    <div key={f.path} className="grid gap-1">
                      <label className="text-[11px] text-muted-foreground flex items-center gap-1">{f.label}{f.unit ? ` (${f.unit})` : ""}</label>
                      <div className="flex gap-1.5 items-center">
                        {f.type === "enum" ? (
                          <select value={unknown ? "" : (ev.value ?? "")} disabled={unknown}
                                  onChange={(e) => setField(f.path, e.target.value)}
                                  data-testid={`reno-field-${f.path}`}
                                  className="h-9 flex-1 rounded-sm border border-border bg-background px-2 text-sm disabled:opacity-40">
                            <option value="">—</option>
                            {(f.options || []).map((o) => <option key={o} value={o}>{o}</option>)}
                          </select>
                        ) : (
                          <Input type={f.type === "number" ? "number" : "text"} value={unknown ? "" : (ev.value ?? "")}
                                 disabled={unknown}
                                 onChange={(e) => setField(f.path, f.type === "number" ? e.target.value : e.target.value)}
                                 data-testid={`reno-field-${f.path}`}
                                 className="h-9 text-sm flex-1 disabled:opacity-40" />
                        )}
                        <button type="button" onClick={() => setField(f.path, null, !unknown)}
                                title="Não sei"
                                data-testid={`reno-unknown-${f.path}`}
                                className={`h-9 px-2 rounded-sm border text-[10px] shrink-0 inline-flex items-center gap-1 ${unknown ? "bg-amber-100 border-amber-300 text-amber-700" : "border-border text-muted-foreground"}`}>
                          <HelpCircle className="h-3 w-3" /> ?
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            </Card>
          ))}
          <div className="flex justify-between">
            <Button variant="outline" onClick={saveInputs} disabled={busy} className="rounded-md" data-testid="reno-save">Guardar</Button>
            <Button onClick={goUnderstand} disabled={busy} className="rounded-md gap-2 bg-emerald-600 hover:bg-emerald-700" data-testid="reno-to-understand">
              Compreender o estado <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Étape Comprendre */}
      {step === 1 && baseline && (
        <div className="grid gap-4" data-testid="reno-understand">
          <Card className="p-4 border-slate-300 bg-slate-50">
            <div className="flex items-center gap-2 mb-1"><Gauge className="h-4 w-4 text-slate-500" /><p className="font-semibold text-sm">Estado energético — motor não configurado</p></div>
            <p className="text-xs text-muted-foreground" data-testid="reno-energy-message">{baseline.energy?.message}</p>
            <div className="mt-2 flex gap-4 text-xs">
              <span>Cobertura dos dados: <b>{baseline.coverage_pct}%</b></span>
              <span>Classe simulada: <b>não calculada</b></span>
              <span>kWh : <b>não calculados</b></span>
            </div>
          </Card>

          <Card className="p-4">
            <p className="overline text-emerald-700 mb-3">Rubricas de perdas e dados a verificar</p>
            <div className="grid gap-2">
              {baseline.posts.map((pt) => (
                <div key={pt.component} className="flex items-start justify-between gap-3 border border-border rounded-sm p-2" data-testid={`reno-post-${pt.component}`}>
                  <div className="min-w-0">
                    <p className="text-sm font-medium">{pt.component}</p>
                    <p className="text-[11px] text-muted-foreground">{pt.reason}</p>
                  </div>
                  <Badge variant="outline" className={`text-[10px] rounded-sm shrink-0 ${ASSESS_STYLE[pt.assessment] || ""}`}>{pt.assessment}</Badge>
                </div>
              ))}
            </div>
          </Card>

          {missing?.missing_high_priority?.length > 0 && (
            <Card className="p-4 border-amber-300 bg-amber-50">
              <div className="flex items-center gap-2 mb-2"><AlertTriangle className="h-4 w-4 text-amber-600" /><p className="font-semibold text-sm text-amber-800">Dados importantes em falta</p></div>
              <div className="flex flex-wrap gap-1.5">
                {missing.missing_high_priority.map((m) => (
                  <Badge key={m.path} variant="outline" className="text-[10px] rounded-sm border-amber-400 text-amber-700">{m.label}</Badge>
                ))}
              </div>
            </Card>
          )}

          <div className="flex justify-between">
            <Button variant="outline" onClick={() => setStep(0)} className="rounded-md gap-1"><ArrowLeft className="h-4 w-4" /> Completar</Button>
            <Button onClick={goCompare} disabled={busy} className="rounded-md gap-2 bg-emerald-600 hover:bg-emerald-700" data-testid="reno-to-compare">
              Comparar os cenários <ArrowRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Étape Comparer */}
      {step === 2 && (
        <div className="grid gap-4" data-testid="reno-compare">
          <div className="grid md:grid-cols-3 gap-3">
            {scenarios.map((s) => (
              <Card key={s.key} className="p-4 flex flex-col gap-2 hover:border-emerald-400 transition" data-testid={`reno-scenario-${s.key}`}>
                <div className="flex items-center justify-between">
                  <Badge className="bg-emerald-600">{s.key}</Badge>
                  {s.budget_flag && <span className={`text-[10px] ${s.budget_flag.includes("au-dessus") ? "text-red-600" : "text-emerald-600"}`}>{s.budget_flag}</span>}
                </div>
                <p className="font-semibold text-sm">{s.name}</p>
                <p className="text-[11px] text-muted-foreground min-h-[48px]">{s.description}</p>
                <p className="text-lg font-bold">{eur(s.total_ht_chiffrable)} <span className="text-[11px] font-normal text-muted-foreground">s/ IVA orçamentável</span></p>
                {s.a_chiffrer.length > 0 && <p className="text-[10px] text-amber-600">{s.a_chiffrer.length} artigo(s) a orçamentar</p>}
                <p className="text-[10px] text-slate-500 italic">{s.energy_gain.message}</p>
                <Button size="sm" onClick={() => { setActiveScenario(s.key); setStep(3); }}
                        className="rounded-sm mt-1 gap-1" variant="outline" data-testid={`reno-scenario-${s.key}-open`}>
                  Ver os trabalhos <Hammer className="h-3 w-3" />
                </Button>
              </Card>
            ))}
          </div>
          {(project.ademe_audits || []).some((a) => (a.steps || []).some((s) => s.cout_travaux)) && (
            <div className="grid gap-2" data-testid="reno-audit-cards">
              <p className="text-xs font-semibold text-sky-700 flex items-center gap-1"><Hammer className="h-3.5 w-3.5" /> Cenários de auditoria oficiais (comparáveis)</p>
              <div className="grid md:grid-cols-3 gap-3">
                {(project.ademe_audits || []).flatMap((a, ai) =>
                  (a.steps || []).map((s, i) => ({ s, ai, i })).filter((x) => x.s.cout_travaux)
                ).map(({ s, ai, i }) => (
                  <Card key={`${ai}-${i}`} className="p-4 flex flex-col gap-2 border-sky-200 bg-sky-50/40 hover:border-sky-400 transition" data-testid={`reno-audit-card-${ai}-${i}`}>
                    <div className="flex items-center justify-between">
                      <Badge className="bg-sky-600">Auditoria energética</Badge>
                      <span className="flex items-center gap-1">
                        <EtiquetteBadge letter={project.ademe_dpe?.etiquette_energie} small />
                        <ArrowRight className="h-3 w-3 text-muted-foreground" />
                        <EtiquetteBadge letter={s.etiquette_energie} small />
                      </span>
                    </div>
                    <p className="font-semibold text-sm capitalize">{s.etape}</p>
                    <p className="text-[11px] text-muted-foreground min-h-[48px]">{s.travaux}</p>
                    <p className="text-lg font-bold">{eur(s.cout_travaux)} <span className="text-[11px] font-normal text-muted-foreground">custo das obras (auditoria)</span></p>
                    {s.gain_relatif_ep != null && <p className="text-[10px] text-sky-700">Gain conso ≈ {Math.round(Math.abs(s.gain_relatif_ep) * 100)} %</p>}
                    <p className="text-[10px] text-slate-500 italic">Dados oficiais — não vinculativos.</p>
                    <Button size="sm" disabled={busy} onClick={() => auditToDevis(ai, i)}
                            className="rounded-sm mt-1 gap-1 bg-sky-600 hover:bg-sky-700" data-testid={`reno-audit-card-devis-${ai}-${i}`}>
                      Transformar em orçamento <FileText className="h-3 w-3" />
                    </Button>
                  </Card>
                ))}
              </div>
            </div>
          )}
          <AidesPanel projectId={project.project_id} scenarios={scenarios} audits={project.ademe_audits || []} ademeDpe={project.ademe_dpe} />
          <div className="flex justify-start">
            <Button variant="outline" onClick={() => setStep(1)} className="rounded-md gap-1"><ArrowLeft className="h-4 w-4" /> Voltar</Button>
          </div>
        </div>
      )}

      {/* Étape Préparer */}
      {step === 3 && activeScenario && (
        <PrepareScenario
          scenario={scenarios.find((s) => s.key === activeScenario)}
          onBack={() => setStep(2)}
          onEstimate={() => createEstimate(activeScenario)}
          busy={busy}
        />
      )}
    </div>
  );
}

function PrepareScenario({ scenario, onBack, onEstimate, busy }) {
  if (!scenario) return null;
  return (
    <div className="grid gap-3" data-testid="reno-prepare">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold">{scenario.name} — descritivo por capítulo</h3>
        <Button onClick={onEstimate} disabled={busy} className="rounded-md gap-2 bg-emerald-600 hover:bg-emerald-700" data-testid="reno-create-estimate">
          <FileText className="h-4 w-4" /> Criar o orçamento
        </Button>
      </div>
      {scenario.work_items.map((it) => (
        <Card key={it.code} className="p-4" data-testid={`reno-workitem-${it.code}`}>
          <div className="flex items-center justify-between gap-2 mb-1">
            <p className="font-medium text-sm">{it.lot} — {it.label}</p>
            <Badge variant="outline" className="text-[10px] rounded-sm shrink-0">
              {it.metre.quantity != null ? `${it.metre.quantity} ${it.metre.unit}` : `${it.metre.unit} a confirmar`}
            </Badge>
          </div>
          <div className="grid sm:grid-cols-2 gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <p><b className="text-foreground">Objetivo:</b> {it.descriptif.objectif}</p>
            <p><b className="text-foreground">Performance :</b> {it.descriptif.performance_cible}</p>
            <p><b className="text-foreground">Medição:</b> {it.descriptif.metre}</p>
            <p><b className="text-foreground">Execução:</b> {it.descriptif.mise_en_oeuvre}</p>
            <p><b className="text-foreground">Interfaces :</b> {it.descriptif.interfaces}</p>
            <p><b className="text-foreground">Controlos:</b> {it.descriptif.controles}</p>
            <p className="sm:col-span-2"><b className="text-foreground">Reservas:</b> {it.descriptif.prerequis_reserves}</p>
          </div>
          <div className="mt-2 flex items-center gap-2">
            {it.chiffrage.total_ht != null ? (
              <Badge className="bg-emerald-600 text-[11px]">{eur(it.chiffrage.total_ht)} HT</Badge>
            ) : (
              <Badge variant="outline" className="text-[11px] border-amber-400 text-amber-700">a orçamentar</Badge>
            )}
            <span className="text-[10px] text-muted-foreground">{it.chiffrage.status}</span>
          </div>
        </Card>
      ))}
      <div className="flex justify-between">
        <Button variant="outline" onClick={onBack} className="rounded-md gap-1"><ArrowLeft className="h-4 w-4" /> Cenários</Button>
        <Button onClick={onEstimate} disabled={busy} className="rounded-md gap-2 bg-emerald-600 hover:bg-emerald-700">
          <FileText className="h-4 w-4" /> Criar o orçamento
        </Button>
      </div>
    </div>
  );
}


const DPE_LETTERS = ["A", "B", "C", "D", "E", "F", "G"];

const GESTES_CATALOGUE = [
  { code: "pac_air_eau", label: "Bomba de calor ar/água", unit: null },
  { code: "vmc_double_flux", label: "VMC double flux", unit: null },
  { code: "iso_rampants", label: "Isolamento de vertentes / sob a cobertura", unit: "m²" },
  { code: "iso_toiture_terrasse", label: "Isolamento de cobertura em terraço", unit: "m²" },
  { code: "fenetres", label: "Substituição de janelas (vidro simples)", unit: "equipamentos" },
  { code: "iso_murs_ext", label: "Isolamento das paredes pelo exterior (ETICS)", unit: "m²" },
  { code: "iso_murs_int", label: "Isolamento das paredes pelo interior", unit: "m²" },
  { code: "iso_plancher_bas", label: "Isolamento do pavimento térreo", unit: "m²" },
];

const ETIQUETTE_COLORS = {
  A: "#319834", B: "#33cc31", C: "#cbfc34", D: "#fbfe06",
  E: "#fbcc05", F: "#fc9935", G: "#fc0205",
};

function EtiquetteBadge({ letter, kind, small }) {
  if (!letter) return null;
  const bg = ETIQUETTE_COLORS[String(letter).toUpperCase()] || "#94a3b8";
  const dark = ["A", "B", "F", "G"].includes(String(letter).toUpperCase());
  return (
    <span className={`inline-flex items-center gap-1 rounded-md font-bold ${small ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-0.5 text-xs"}`}
          style={{ backgroundColor: bg, color: dark ? "#fff" : "#1f2937" }}
          data-testid={`etiquette-${kind || "x"}-${letter}`}>
      {letter}{kind ? <span className="font-normal opacity-80">· {kind}</span> : null}
    </span>
  );
}

function AidesPanel({ projectId, scenarios, audits = [], ademeDpe }) {
  const nav = useNavigate();
  const targets = useMemo(() => {
    const list = (scenarios || []).map((s) => ({
      id: `reno:${s.key}`, group: "Cenários RenoPilot",
      label: `${s.key} — ${s.name} (${eur(s.total_ht_chiffrable)})`,
      type: "reno", scenario_key: s.key,
    }));
    const initial = ademeDpe?.etiquette_energie
      || (audits[0]?.steps || []).find((s) => (s.etape || "").toLowerCase().includes("initial"))?.etiquette_energie;
    (audits || []).forEach((a, ai) => {
      (a.steps || []).forEach((s, i) => {
        if (!s.cout_travaux) return;
        list.push({
          id: `audit:${ai}:${i}`, group: "Cenários de auditoria energética",
          label: `Auditoria ${s.etape} (${s.etiquette_energie}) — ${eur(s.cout_travaux)}`,
          type: "audit", travaux_ht: s.cout_travaux,
          dpe_actuel: initial || "", dpe_vise: s.etiquette_energie || "",
        });
      });
    });
    return list;
  }, [scenarios, audits, ademeDpe]);

  const [form, setForm] = useState({
    revenu: "", personnes: "", proprietaire_occupant: true, residence_principale: true,
    dpe_actuel: "", dpe_vise: "", target: "",
  });
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);
  const [communeOptions, setCommuneOptions] = useState([]);
  const [commune, setCommune] = useState("");
  const [gSel, setGSel] = useState({});
  const [gRes, setGRes] = useState(null);
  const [gBusy, setGBusy] = useState(false);
  const [gPrices, setGPrices] = useState({});

  const runGestes = async () => {
    const items = GESTES_CATALOGUE.filter((g) => gSel[g.code]?.on)
      .map((g) => ({ code: g.code, value: gSel[g.code]?.value ? Number(gSel[g.code].value) : null }));
    if (!items.length) return toast.error("Selecione pelo menos uma intervenção");
    setGBusy(true);
    try {
      const { data } = await api.post(`/renovation/projects/${projectId}/aides-gestes`, {
        revenu: form.revenu ? Number(form.revenu) : null,
        personnes: form.personnes ? Number(form.personnes) : null,
        proprietaire_occupant: !!form.proprietaire_occupant,
        residence_principale: !!form.residence_principale,
        commune_insee: commune || null, gestes: items,
      });
      if (data.need_commune) { toast.error("Freguesia obrigatória (código postal do projeto em falta)"); return; }
      setGRes(data);
    } catch (e) { toast.error(e?.response?.data?.detail || "Simulação por intervenção indisponível"); }
    finally { setGBusy(false); }
  };

  const gesteToDevis = async (g) => {
    try {
      const priceRaw = gPrices[g.code];
      const { data } = await api.post(`/renovation/projects/${projectId}/geste-to-devis`, {
        geste_code: g.code,
        value: g.value != null && g.value !== "" ? Number(g.value) : null,
        mpr: typeof g.mpr === "number" ? g.mpr : null,
        cee: typeof g.cee === "number" ? g.cee : null,
        price_ht: priceRaw !== undefined && priceRaw !== "" ? Number(priceRaw) : null,
      });
      toast.success(data.message || "Orçamento criado a partir da intervenção");
      if (data.doc_id) nav(`/devis-editeur/${data.doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível criar o orçamento"); }
  };

  const resteFor = (g) => {
    const price = Number(gPrices[g.code]);
    if (!gPrices[g.code] || Number.isNaN(price)) return null;
    const aide = (typeof g.mpr === "number" ? g.mpr : 0) + (typeof g.cee === "number" ? g.cee : 0);
    return Math.round((price - aide) * 100) / 100;
  };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e?.target ? e.target.value : e }));

  useEffect(() => {
    if (!form.target && targets[0]) setForm((f) => ({ ...f, target: targets[0].id }));
  }, [targets]); // eslint-disable-line

  const run = async (communeInsee) => {
    setBusy(true);
    try {
      const tgt = targets.find((t) => t.id === form.target);
      const body = {
        revenu: form.revenu ? Number(form.revenu) : null,
        personnes: form.personnes ? Number(form.personnes) : null,
        proprietaire_occupant: !!form.proprietaire_occupant,
        residence_principale: !!form.residence_principale,
        dpe_actuel: (tgt?.type === "audit" ? tgt.dpe_actuel : form.dpe_actuel) || null,
        dpe_vise: (tgt?.type === "audit" ? tgt.dpe_vise : form.dpe_vise) || null,
        scenario_key: tgt?.type === "reno" ? tgt.scenario_key : null,
        travaux_ht_override: tgt?.type === "audit" ? tgt.travaux_ht : null,
        label_override: tgt?.type === "audit" ? tgt.label : null,
        commune_insee: communeInsee || commune || null,
      };
      const { data } = await api.post(`/renovation/projects/${projectId}/aides`, body);
      if (data.need_commune) {
        setCommuneOptions(data.commune_options || []);
        setRes(null);
        if (!(data.commune_options || []).length)
          toast.error("Indique o código postal do projeto (etapa Descrever) para simular os apoios.");
        return;
      }
      setRes(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Simulação dos apoios indisponível");
    } finally {
      setBusy(false);
    }
  };

  const fmt = (n) => (typeof n === "number" ? eur(n) : "—");

  return (
    <Card className="p-4 border-emerald-200 bg-emerald-50/30" data-testid="reno-aides-panel">
      <div className="flex items-center gap-2 mb-1">
        <PiggyBank className="h-5 w-5 text-emerald-600" />
        <h3 className="font-semibold text-sm">Apoios financeiros <span className="font-normal text-muted-foreground">(indicativo)</span></h3>
        <Badge variant="outline" className="text-[10px] border-emerald-300 text-emerald-700">Apoios à reabilitação · Fundo Ambiental</Badge>
      </div>
      <p className="text-[11px] text-muted-foreground mb-3">
        Simulação indicativa. Indique a situação do agregado familiar para estimar os apoios disponíveis (Fundo Ambiental, IFRRU, benefícios fiscais…).
      </p>

      <div className="grid sm:grid-cols-3 gap-3">
        <label className="grid gap-1 text-[11px]">Rendimento coletável (€)
          <Input type="number" value={form.revenu} onChange={set("revenu")} placeholder="ex. 25000" className="h-8" data-testid="aides-revenu" />
        </label>
        <label className="grid gap-1 text-[11px]">Pessoas no agregado
          <Input type="number" value={form.personnes} onChange={set("personnes")} placeholder="ex. 3" className="h-8" data-testid="aides-personnes" />
        </label>
        <label className="grid gap-1 text-[11px]">Alvo (montante das obras)
          <select value={form.target} onChange={set("target")} className="h-8 rounded-md border border-border bg-background px-2 text-xs" data-testid="aides-scenario">
            {["Cenários RenoPilot", "Cenários de auditoria energética"].map((g) => {
              const opts = targets.filter((t) => t.group === g);
              if (!opts.length) return null;
              return <optgroup key={g} label={g}>{opts.map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}</optgroup>;
            })}
          </select>
        </label>
        <label className="grid gap-1 text-[11px]">Certificado energético atual
          <select value={form.dpe_actuel} onChange={set("dpe_actuel")} disabled={targets.find((t) => t.id === form.target)?.type === "audit"} className="h-8 rounded-md border border-border bg-background px-2 text-xs disabled:opacity-60" data-testid="aides-dpe-actuel">
            <option value="">—</option>{DPE_LETTERS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        <label className="grid gap-1 text-[11px]">Classe energética pretendida
          <select value={form.dpe_vise} onChange={set("dpe_vise")} disabled={targets.find((t) => t.id === form.target)?.type === "audit"} className="h-8 rounded-md border border-border bg-background px-2 text-xs disabled:opacity-60" data-testid="aides-dpe-vise">
            <option value="">—</option>{DPE_LETTERS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </label>
        {targets.find((t) => t.id === form.target)?.type === "audit" && (
          <p className="text-[10px] text-sky-700 sm:col-span-3 -mt-1">Montante e classes retomados do cenário de auditoria oficial (classe {targets.find((t) => t.id === form.target)?.dpe_actuel || "?"} → {targets.find((t) => t.id === form.target)?.dpe_vise || "?"}).</p>
        )}
        <div className="grid gap-1 text-[11px]">Auto de medição
          <div className="flex gap-3 items-center h-8">
            <label className="flex items-center gap-1"><input type="checkbox" checked={form.proprietaire_occupant} onChange={(e) => set("proprietaire_occupant")(e.target.checked)} data-testid="aides-proprietaire" /> Proprietário residente</label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={form.residence_principale} onChange={(e) => set("residence_principale")(e.target.checked)} data-testid="aides-residence" /> Habitação própria permanente</label>
          </div>
        </div>
      </div>

      {communeOptions.length > 1 && (
        <div className="mt-3 grid gap-1 text-[11px]">Várias freguesias para este código postal — especifique:
          <select value={commune} onChange={(e) => setCommune(e.target.value)} className="h-8 rounded-md border border-border bg-background px-2 text-xs" data-testid="aides-commune">
            <option value="">—</option>{communeOptions.map((c) => <option key={c.code} value={c.code}>{c.nom} ({c.code})</option>)}
          </select>
        </div>
      )}

      <div className="mt-3">
        <Button size="sm" onClick={() => run()} disabled={busy} className="rounded-md gap-1 bg-emerald-600 hover:bg-emerald-700" data-testid="aides-calculer">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <PiggyBank className="h-4 w-4" />} Calcular os apoios
        </Button>
      </div>

      {res && res.ok && (
        <div className="mt-4 grid gap-3" data-testid="aides-result">
          <div className="flex flex-wrap items-center gap-2 text-xs">
            {res.revenu_classe && <Badge className="bg-emerald-600 capitalize">Rendimento: {res.revenu_classe}</Badge>}
            {res.scenario_name && <Badge variant="outline">Travaux : {fmt(res.travaux_ht)} HT — {res.scenario_name}</Badge>}
          </div>

          <div className="grid sm:grid-cols-3 gap-2 text-xs">
            <div className="rounded-md border border-emerald-200 bg-white p-2">
              <div className="text-[10px] uppercase text-muted-foreground">Total de apoios (indicativo)</div>
              <div className="text-lg font-bold text-emerald-700" data-testid="aides-total-subventions">{fmt(res.total_subventions_indicatif)}</div>
            </div>
            <div className="rounded-md border border-emerald-200 bg-white p-2">
              <div className="text-[10px] uppercase text-muted-foreground">Valor a cargo (indicativo)</div>
              <div className="text-lg font-bold" data-testid="aides-reste">{fmt(res.reste_a_charge_indicatif)}</div>
            </div>
            <div className="rounded-md border border-emerald-200 bg-white p-2 flex items-center gap-2">
              <Landmark className="h-4 w-4 text-emerald-600" />
              <div>
                <div className="text-[10px] uppercase text-muted-foreground">Empréstimo bonificado</div>
                <div className="font-semibold">{res.eco_ptz?.formattedValue || "—"}</div>
              </div>
            </div>
          </div>

          <div className="rounded-md border border-border bg-white divide-y divide-border">
            {(res.aides || []).map((a, i) => (
              <div key={i} className="flex items-start justify-between gap-2 px-3 py-1.5 text-xs" data-testid={`aides-item-${i}`}>
                <span className="flex items-start gap-1.5">
                  {a.status ? <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 mt-0.5 shrink-0" /> : <Info className="h-3.5 w-3.5 text-muted-foreground mt-0.5 shrink-0" />}
                  <span className={a.status ? "" : "text-muted-foreground"}>{a.label}{a.type ? <span className="text-[10px] text-muted-foreground"> · {a.type}</span> : null}</span>
                </span>
                <span className={`shrink-0 font-medium ${a.status ? "text-emerald-700" : "text-muted-foreground"}`}>{a.value}</span>
              </div>
            ))}
          </div>

          <p className="text-[10px] text-amber-700 flex items-start gap-1">
            <AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" /> {res.disclaimer}
          </p>
        </div>
      )}

      {/* Parcours par geste — MPR + CEE par poste */}
      <div className="mt-4 border-t border-emerald-200 pt-3" data-testid="aides-gestes-section">
        <p className="text-xs font-semibold mb-2 flex items-center gap-1"><Hammer className="h-3.5 w-3.5 text-emerald-600" /> Apoios por intervenção</p>
        <div className="grid gap-1.5">
          {GESTES_CATALOGUE.map((g) => (
            <div key={g.code} className="flex items-center gap-2 text-[11px]">
              <label className="flex items-center gap-1 flex-1">
                <input type="checkbox" checked={!!gSel[g.code]?.on}
                       onChange={(e) => setGSel((s) => ({ ...s, [g.code]: { ...s[g.code], on: e.target.checked } }))}
                       data-testid={`aides-geste-${g.code}`} />
                {g.label}
              </label>
              {g.unit && gSel[g.code]?.on && (
                <span className="flex items-center gap-1">
                  <Input type="number" value={gSel[g.code]?.value || ""} placeholder={g.unit}
                         onChange={(e) => setGSel((s) => ({ ...s, [g.code]: { ...s[g.code], value: e.target.value } }))}
                         className="h-7 w-20 text-xs" data-testid={`aides-geste-val-${g.code}`} />
                  <span className="text-muted-foreground">{g.unit}</span>
                </span>
              )}
            </div>
          ))}
        </div>
        <Button size="sm" variant="outline" onClick={runGestes} disabled={gBusy} className="rounded-sm mt-2 gap-1 h-7 text-[11px]" data-testid="aides-gestes-calculer">
          {gBusy ? <Loader2 className="h-3 w-3 animate-spin" /> : <PiggyBank className="h-3 w-3" />} Calcular por intervenção
        </Button>

        {gRes && gRes.ok && (
          <div className="mt-3" data-testid="aides-gestes-result">
            <table className="w-full text-[11px] border border-border rounded-md overflow-hidden">
              <thead className="bg-emerald-50 text-left text-[10px] uppercase text-muted-foreground">
                <tr><th className="px-2 py-1">Intervenção</th><th className="px-2 py-1 text-right">Preço estimado</th><th className="px-2 py-1 text-right">MPR</th><th className="px-2 py-1 text-right">Certificados de poupança</th><th className="px-2 py-1 text-right">Valor a cargo</th><th className="px-2 py-1 text-right">Orçamento</th></tr>
              </thead>
              <tbody>
                {gRes.gestes.map((g, i) => {
                  const reste = resteFor(g);
                  return (
                  <tr key={i} className="border-t border-border" data-testid={`aides-geste-row-${g.code}`}>
                    <td className="px-2 py-1">
                      {g.label}{g.value ? <span className="text-muted-foreground"> · {g.value} {g.unit}</span> : null}
                      {g.source === "repli" && (
                        <span className="ml-1 inline-flex items-center rounded-sm bg-amber-100 text-amber-800 px-1 text-[9px] font-medium">repli</span>
                      )}
                      {g.note && <div className="text-[9px] text-amber-700 mt-0.5">{g.note}</div>}
                    </td>
                    <td className="px-2 py-1 text-right">
                      <Input type="number" value={gPrices[g.code] ?? ""} placeholder="€ HT"
                             onChange={(e) => setGPrices((s) => ({ ...s, [g.code]: e.target.value }))}
                             className="h-7 w-20 text-xs text-right ml-auto" data-testid={`aides-geste-price-${g.code}`} />
                    </td>
                    <td className="px-2 py-1 text-right">{typeof g.mpr === "number" ? eur(g.mpr) : "—"}</td>
                    <td className="px-2 py-1 text-right">{typeof g.cee === "number" ? eur(g.cee) : "—"}</td>
                    <td className="px-2 py-1 text-right font-semibold" data-testid={`aides-geste-reste-${g.code}`}>
                      {reste !== null ? <span className={reste < 0 ? "text-emerald-600" : ""}>{eur(reste)}</span> : "—"}
                    </td>
                    <td className="px-2 py-1 text-right">
                      <Button size="sm" variant="outline" onClick={() => gesteToDevis(g)}
                              className="h-6 px-2 text-[10px] rounded-sm gap-1" data-testid={`aides-geste-to-devis-${g.code}`}>
                        <FileText className="h-3 w-3" /> Orçamento
                      </Button>
                    </td>
                  </tr>
                  );
                })}
                <tr className="border-t-2 border-emerald-300 font-semibold bg-emerald-50/50">
                  <td className="px-2 py-1">Total (indicativo)</td>
                  <td className="px-2 py-1 text-right">{eur(gRes.gestes.reduce((s, g) => s + (Number(gPrices[g.code]) || 0), 0))}</td>
                  <td className="px-2 py-1 text-right">{eur(gRes.total_mpr_indicatif)}</td>
                  <td className="px-2 py-1 text-right">{eur(gRes.total_cee_indicatif)}</td>
                  <td className="px-2 py-1 text-right">{eur(Math.max(0, gRes.gestes.reduce((s, g) => s + (Number(gPrices[g.code]) || 0), 0) - gRes.total_aides_indicatif))}</td>
                  <td className="px-2 py-1 text-right"></td>
                </tr>
              </tbody>
            </table>
            <p className="text-[10px] text-amber-700 mt-1 flex items-start gap-1"><AlertTriangle className="h-3 w-3 mt-0.5 shrink-0" /> {gRes.disclaimer}</p>
          </div>
        )}
      </div>
    </Card>
  );
}
