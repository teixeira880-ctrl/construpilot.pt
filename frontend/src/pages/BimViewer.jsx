import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Box, Calculator, Download, FolderOpen, Layers, Loader2, Maximize, Scissors } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, num } from "@/lib/api";
import BimEditor from "@/components/bim/BimEditor";

const CLASS_LABELS = {
  IfcWall: "Paredes", IfcSlab: "Lajes", IfcColumn: "Pilares", IfcBeam: "Vigas", IfcFooting: "Sapatas",
  IfcDoor: "Portas", IfcWindow: "Janelas", IfcSpace: "Divisões", IfcCovering: "Pavimentos",
};
const WARNING_LABELS = {
  opening_without_wall: "vão sem parede",
  opening_too_small: "vão demasiado pequeno",
  wall_too_short: "parede demasiado curta",
  slab_degenerate: "laje sem área",
  column_section_suspicious: "secção de pilar suspeita",
  beam_too_short: "viga demasiado curta",
  footing_too_small: "sapata demasiado pequena",
};
const PARAM_KEYS = ["wall_height", "voile_ep", "cloison_ep", "dalle_ep", "poutre_l", "poutre_h"];
const SECTION_Z = 1.2; // corte de planta de arquitetura (m acima do pavimento)
const STATUS = {
  ok: { label: "OK", color: "#16a34a", cls: "text-emerald-700 dark:text-emerald-400" },
  atencao: { label: "Atenção", color: "#f59e0b", cls: "text-amber-700 dark:text-amber-400" },
  insuficiente: { label: "Insuficiente", color: "#dc2626", cls: "text-red-700 dark:text-red-400" },
};
const pct = (u) => `${Math.round((u || 0) * 100)} %`;

async function blobToText(blob) {
  try { return JSON.parse(await blob.text()).detail; } catch { return null; }
}

export default function BimViewer() {
  const [sp, setSp] = useSearchParams();
  const planId = sp.get("plan");
  const requestedPage = Number(sp.get("page") || 0);
  const page = Number.isSafeInteger(requestedPage) && requestedPage >= 0 ? requestedPage : 0;
  const query = PARAM_KEYS.filter((k) => sp.get(k)).map((k) => `${k}=${encodeURIComponent(sp.get(k))}`).join("&");
  const changePage = (index) => {
    const next = new URLSearchParams(sp);
    next.set("page", String(index));
    setSp(next);
  };
  return <BimPlanViewer key={`${planId || ""}:${page}:${query}`} planId={planId} page={page} query={query} onPageChange={changePage} />;
}

function BimPlanViewer({ planId, page, query, onPageChange }) {
  const navigate = useNavigate();
  const hostRef = useRef(null);
  const viewerRef = useRef(null);
  const fileRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [selected, setSelected] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const [calcBusy, setCalcBusy] = useState(false);
  const [section, setSection] = useState(false);
  const [ortho, setOrtho] = useState(false);
  const [ifcBytes, setIfcBytes] = useState(null);
  const [modelName, setModelName] = useState(null);
  const [sourcePlan, setSourcePlan] = useState(null);
  const [availablePlans, setAvailablePlans] = useState([]);
  const [studioEnabled, setStudioEnabled] = useState(false);
  const [studioBusy, setStudioBusy] = useState(false);
  const sectionRef = useRef(false);
  const selectedRef = useRef(null);
  const planUrl = planId && `/plan?open=${encodeURIComponent(planId)}&page=${page}`;

  useEffect(() => {
    let active = true;
    if (planId) {
      api.get(`/takeoffs/${encodeURIComponent(planId)}`).then(({ data }) => {
        if (active) setSourcePlan(data);
      }).catch(() => {});
      api.get("/bim/config").then(({ data }) => {
        if (active) setStudioEnabled(data?.enabled === true);
      }).catch(() => {});
    } else {
      api.get("/takeoffs").then(({ data }) => {
        if (active) setAvailablePlans(data.plans || []);
      }).catch(() => {});
    }
    return () => { active = false; };
  }, [planId]);

  // Arranque do motor 3D (import dinâmico: That Open Engine + web-ifc só são descarregados nesta página).
  useEffect(() => {
    let disposed = false;
    let viewer = null;
    (async () => {
      try {
        const { createBimViewer } = await import("@/components/bim/bimEngine");
        if (disposed || !hostRef.current) return;
        viewer = await createBimViewer(hostRef.current, { onSelect: (item) => {
          selectedRef.current = item;
          setSelected(item);
        } });
        if (disposed) { viewer.dispose(); return; }
        viewerRef.current = viewer;
        setReady(true);
      } catch (e) {
        console.error(e);
        setError("Não foi possível iniciar o visualizador 3D neste navegador (WebGL indisponível?).");
      }
    })();
    return () => { disposed = true; viewerRef.current = null; viewer?.dispose(); };
  }, []);

  const showBytes = useCallback(async (bytes, name, selectedGuid = null) => {
    setBusy(true);
    selectedRef.current = null;
    setSelected(null);
    try {
      await viewerRef.current.loadIfc(bytes, name);
      setIfcBytes(bytes);
      setModelName(name);
      if (sectionRef.current) viewerRef.current.setSection(SECTION_Z);
      if (selectedGuid) await viewerRef.current.selectByGuid(selectedGuid);
    } catch (e) {
      console.error(e);
      toast.error("Ficheiro IFC ilegível.");
    } finally { setBusy(false); }
  }, []);

  // Modelo gerado a partir da planta lida.
  const loadFromPlan = useCallback(async (keepSelection = false) => {
    if (!planId || !viewerRef.current) return;
    const selectedGuid = keepSelection ? selectedRef.current?.guid : null;
    setBusy(true);
    setError(null);
    try {
      const base = `/bim/takeoffs/${encodeURIComponent(planId)}/${page}`;
      const suffix = query ? `?${query}` : "";
      const [{ data: sum }, { data: blob }] = await Promise.all([
        api.get(`${base}/summary${suffix}`),
        api.get(`${base}/ifc${suffix}`, { responseType: "blob" }),
      ]);
      if (!viewerRef.current) return;
      setSummary(sum);
      await showBytes(await blob.arrayBuffer(), `Planta p.${page + 1}`, selectedGuid);
    } catch (e) {
      const data = e?.response?.data;
      const detail = data instanceof Blob ? await blobToText(data) : data?.detail;
      setError(detail || "Não foi possível gerar o modelo BIM desta planta.");
      setBusy(false);
    }
  }, [planId, page, query, showBytes]);

  useEffect(() => { if (ready && planId) loadFromPlan(); }, [ready, planId, loadFromPlan]);

  const openLocal = async (file) => {
    if (!file) return;
    if (!/\.ifc$/i.test(file.name)) { toast.error("Escolha um ficheiro .ifc"); return; }
    setSummary(null);
    setAnalysis(null);
    await showBytes(await file.arrayBuffer(), file.name.replace(/\.ifc$/i, ""));
  };

  // Pré-dimensionamento do pórtico (vigas e pilares) e cores por taxa de utilização.
  // Planta lida → modelo gerado no servidor ; IFC aberto (Revit, Archicad…) → ficheiro enviado e calculado no servidor.
  const runAnalysis = async (storey = null) => {
    if (!planId && !ifcBytes) return;
    setCalcBusy(true);
    try {
      let data;
      if (planId) {
        ({ data } = await api.get(`/bim/takeoffs/${encodeURIComponent(planId)}/${page}/analysis${query ? `?${query}` : ""}`));
      } else {
        const form = new FormData();
        form.append("file", new Blob([ifcBytes], { type: "application/x-step" }), `${modelName || "modelo"}.ifc`);
        ({ data } = await api.post(`/bim/ifc/analysis${storey !== null ? `?storey=${storey}` : ""}`, form));
      }
      setAnalysis(data);
      const colors = {};
      [...data.beams, ...data.columns].forEach((e) => { colors[e.guid] = STATUS[e.status]?.color || "#64748b"; });
      await viewerRef.current?.colorByGuid(colors);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cálculo impossível para este modelo.");
    } finally { setCalcBusy(false); }
  };

  const clearAnalysis = async () => {
    setAnalysis(null);
    await viewerRef.current?.colorByGuid({});
  };

  const download = () => {
    if (!ifcBytes) return;
    const url = URL.createObjectURL(new Blob([ifcBytes], { type: "application/x-step" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = `${(modelName || "modelo").replace(/[^\w.-]+/g, "_")}.ifc`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  const copyToStudio = async () => {
    if (!ifcBytes || studioBusy) return;
    setStudioBusy(true);
    try {
      const name = `${sourcePlan?.filename?.replace(/\.[^.]+$/, "") || "Planta"} · pág. ${page + 1}`;
      const form = new FormData();
      form.append("file", new Blob([ifcBytes], { type: "application/x-step" }), "modelo.ifc");
      form.append("name", name);
      const { data } = await api.post("/bim/models", form);
      navigate(`/bim-studio?model=${encodeURIComponent(data.model_id)}&version=${data.version}`);
    } catch (error) {
      toast.error(error?.response?.data?.detail || "Não foi possível copiar o modelo para o BIM Studio.");
    } finally {
      setStudioBusy(false);
    }
  };

  const toggleSection = () => {
    const next = !section;
    sectionRef.current = next;
    setSection(next);
    viewerRef.current?.setSection(next ? SECTION_Z : null);
  };

  const toggleOrtho = async () => {
    const next = !ortho;
    setOrtho(next);
    await viewerRef.current?.setProjection(next ? "ortho" : "perspective");
  };

  const totals = summary?.totals || {};
  const picked = selected?.guid ? summary?.elements?.find((element) => element.guid === selected.guid) : null;
  const selectedElement = picked?.ifc_class === "IfcCovering"
    ? summary.elements.find((element) => element.ifc_class === "IfcSlab" && element.source_id === picked.source_id)
    : picked;

  return (
    <div className="flex flex-col h-[calc(100dvh-4rem)] min-h-[480px]" data-testid="bim-viewer-page">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b bg-background">
        {planId && (
          <Button size="sm" variant="ghost" className="h-8 gap-1" data-testid="bim-back-to-plan" onClick={() => navigate(planUrl)}>
            <ArrowLeft className="h-4 w-4" /> Planta
          </Button>
        )}
        <h1 className="font-display text-base font-semibold flex items-center gap-2 mr-auto">
          <Box className="h-4 w-4 text-primary" /> Modelo BIM
          {modelName && <span className="text-muted-foreground font-normal text-sm truncate max-w-[40vw]">· {modelName}</span>}
          {summary?.schema && <Badge variant="outline" className="text-[10px]">{summary.schema}</Badge>}
        </h1>
        <input ref={fileRef} type="file" accept=".ifc" className="hidden" data-testid="bim-open-input"
               onChange={(e) => { openLocal(e.target.files?.[0]); e.target.value = ""; }} />
        <Button size="sm" variant="outline" className="h-8 gap-1" disabled={!ready || busy} onClick={() => fileRef.current?.click()} data-testid="bim-open-file">
          <FolderOpen className="h-4 w-4" /> Abrir IFC
        </Button>
        <Button size="sm" variant="outline" className="h-8 gap-1" disabled={!ifcBytes || busy} onClick={() => viewerRef.current?.fit()} data-testid="bim-fit">
          <Maximize className="h-4 w-4" /> Ajustar
        </Button>
        <Button size="sm" variant={section ? "default" : "outline"} className="h-8 gap-1" disabled={!ifcBytes} onClick={toggleSection} data-testid="bim-section">
          <Scissors className="h-4 w-4" /> Corte {SECTION_Z.toLocaleString("pt-PT")} m
        </Button>
        <Button size="sm" variant={ortho ? "default" : "outline"} className="h-8 gap-1" disabled={!ifcBytes} onClick={toggleOrtho} data-testid="bim-ortho">
          <Layers className="h-4 w-4" /> {ortho ? "Ortogonal" : "Perspetiva"}
        </Button>
        {(planId || ifcBytes) && (
          <Button size="sm" variant={analysis ? "default" : "outline"} className="h-8 gap-1" disabled={!ifcBytes || busy || calcBusy}
                  onClick={analysis ? clearAnalysis : () => runAnalysis()} data-testid="bim-analysis">
            {calcBusy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Calculator className="h-4 w-4" />}
            {analysis ? "Ocultar cálculo" : "Calcular estrutura"}
          </Button>
        )}
        {planId && (
          <Button size="sm" variant="outline" className="h-8 gap-1" disabled={busy} onClick={() => navigate(`/construcao-tradicional?plan=${encodeURIComponent(planId)}&page=${page}`)} data-testid="bim-alvenaria">
            <Layers className="h-4 w-4" /> Calcular alvenaria
          </Button>
        )}
        <Button size="sm" className="h-8 gap-1" disabled={!ifcBytes} onClick={download} data-testid="bim-download">
          <Download className="h-4 w-4" /> IFC
        </Button>
        {planId && studioEnabled && (
          <Button size="sm" variant="outline" className="h-8" disabled={!ifcBytes || busy || studioBusy} onClick={copyToStudio} data-testid="bim-copy-to-studio">
            {studioBusy ? "A copiar…" : "Copiar para o BIM Studio"}
          </Button>
        )}
      </div>
      {sourcePlan && (
        <div className="flex flex-wrap items-center gap-3 border-b bg-background px-3 py-2 text-sm" data-testid="bim-source-plan">
          <span className="min-w-0 truncate font-medium" title={sourcePlan.filename}>{sourcePlan.filename}</span>
          <label className="ms-auto flex items-center gap-2">Página
            <select className="rounded border bg-background p-1" value={page} onChange={(event) => onPageChange(Number(event.target.value))} data-testid="bim-plan-page">
              {Array.from({ length: sourcePlan.page_count || sourcePlan.pages?.length || 1 }, (_, index) => (
                <option value={index} key={index}>{index + 1}{sourcePlan.pages?.[index]?.level_label ? ` · ${sourcePlan.pages[index].level_label}` : ""}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      {!planId && availablePlans.length > 0 && (
        <label className="flex flex-wrap items-center gap-3 border-b bg-background px-3 py-2 text-sm">Planta guardada
          <select className="min-w-0 rounded border bg-background p-1" value="" data-testid="bim-select-plan"
            onChange={(event) => { if (event.target.value) navigate(`/bim?plan=${encodeURIComponent(event.target.value)}&page=0`); }}>
            <option value="">Escolher planta…</option>
            {availablePlans.map((plan) => <option value={plan.plan_id} key={plan.plan_id}>{plan.filename || plan.plan_id}</option>)}
          </select>
        </label>
      )}

      <div className="flex flex-1 min-h-0 flex-col md:flex-row">
        <div className="relative flex-1 min-h-[320px]"
             onDragOver={(e) => e.preventDefault()}
             onDrop={(e) => { e.preventDefault(); openLocal(e.dataTransfer.files?.[0]); }}>
          <div ref={hostRef} className="absolute inset-0" data-testid="bim-canvas" />
          {(busy || (!ready && !error)) && (
            <div className="absolute inset-0 flex items-center justify-center bg-background/60 pointer-events-none">
              <Loader2 className="h-6 w-6 animate-spin text-primary" />
            </div>
          )}
          {!busy && ready && !ifcBytes && !error && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <p className="text-sm text-muted-foreground text-center px-6">
                Arraste um ficheiro .ifc para aqui, ou gere o modelo a partir de uma planta analisada.
              </p>
            </div>
          )}
          {error && (
            <div className="absolute inset-x-4 top-4 rounded-md border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-700 dark:text-red-300" data-testid="bim-error">
              <p>{error}</p>
              {planUrl && (
                <Button size="sm" variant="outline" className="mt-2" onClick={() => navigate(planUrl)}>
                  Preparar esta página no Editor de Plantas
                </Button>
              )}
            </div>
          )}
        </div>

        <aside className="md:w-80 border-t md:border-t-0 md:border-l overflow-y-auto p-3 space-y-4 text-sm max-h-[45vh] md:max-h-none" data-testid="bim-panel">
          {planId && summary && <BimEditor key={`${planId}:${page}`} planId={planId} page={page} disabled={busy}
            selected={selectedElement} elements={summary.elements} onSelect={(guid) => viewerRef.current?.selectByGuid(guid)}
            onChanged={() => { setAnalysis(null); loadFromPlan(true); }} />}
          {summary?.params?.verified_outline && (
            <section className="text-xs" data-testid="bim-verified-floor-outline">
              <strong>Área bruta cotada {summary.params.verified_outline.area_m2.toLocaleString("pt-PT", { minimumFractionDigits: 2 })} m²</strong>
              <p>{summary.params.verified_outline.width_m} × {summary.params.verified_outline.depth_m} m · recorte {summary.params.verified_outline.recess_m.join(" × ")} m</p>
            </section>
          )}
          {summary && (
            <section>
              <h2 className="font-semibold mb-2">Elementos</h2>
              <table className="w-full text-xs">
                <tbody>
                  {Object.entries(CLASS_LABELS).filter(([c]) => totals[c]).map(([c, label]) => (
                    <tr key={c} className="border-b last:border-0">
                      <td className="py-1">{label}</td>
                      <td className="py-1 text-right tabular-nums">{totals[c].count}</td>
                      <td className="py-1 text-right tabular-nums text-muted-foreground">
                        {totals[c].volume_m3 ? `${num(totals[c].volume_m3, 2)} m³` : totals[c].area_m2 ? `${num(totals[c].area_m2, 1)} m²` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs">Betão armado: <strong className="tabular-nums">{num(summary.concrete_volume_m3, 2)} m³</strong></p>
              <p className="text-[11px] text-muted-foreground">
                Pé-direito {num(summary.params?.wall_height, 2)} m · paredes {num(summary.params?.voile_ep * 100)} cm · laje {num(summary.params?.dalle_ep * 100)} cm
              </p>
              {summary.valid && <Badge variant="outline" className="mt-2 text-[10px] text-emerald-700 border-emerald-600/40">IFC validado (esquema)</Badge>}
            </section>
          )}

          {summary?.warnings?.length > 0 && (
            <section>
              <h2 className="font-semibold mb-1">A verificar ({summary.warnings.length})</h2>
              <ul className="text-xs text-amber-700 dark:text-amber-300 space-y-0.5">
                {summary.warnings.slice(0, 30).map((w, i) => (
                  <li key={`${w.source_id}-${i}`}>{WARNING_LABELS[w.code] || w.code} · {w.source_id}</li>
                ))}
              </ul>
              <p className="text-[11px] text-muted-foreground mt-1">Corrija estes elementos na planta e volte a gerar o modelo.</p>
            </section>
          )}

          {analysis && (
            <section data-testid="bim-analysis-panel">
              <h2 className="font-semibold mb-1">Pré-dimensionamento</h2>
              {analysis.storeys?.length > 0 && (
                <label className="flex items-center gap-2 text-[11px] mb-1">
                  Piso
                  <select className="h-7 rounded border bg-background px-1 text-[11px]" value={analysis.storey?.index ?? 0}
                          disabled={calcBusy} onChange={(e) => runAnalysis(Number(e.target.value))} data-testid="bim-analysis-storey">
                    {analysis.storeys.map((s) => (
                      <option key={s.index} value={s.index}>
                        {s.name} · {num(s.elevation, 2)} m · {s.beams} vigas, {s.columns} pilares
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <p className={`text-xs font-medium ${STATUS[analysis.status]?.cls || ""}`}>
                Taxa máxima {pct(analysis.max_utilization)} · {STATUS[analysis.status]?.label}
              </p>
              <div className="flex gap-3 text-[11px] my-1">
                {Object.entries(STATUS).map(([k, v]) => (
                  <span key={k} className="flex items-center gap-1">
                    <span className="inline-block h-2 w-2 rounded-full" style={{ background: v.color }} />{v.label}
                  </span>
                ))}
              </div>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-muted-foreground"><th className="text-left font-normal">Elem.</th><th className="text-right font-normal">Esforço</th><th className="text-right font-normal">As</th><th className="text-right font-normal">Taxa</th></tr>
                </thead>
                <tbody>
                  {analysis.beams.map((b, i) => (
                    <tr key={b.guid} className="border-b last:border-0" title={`Flexão ${pct(b.utilization_parts.flexao)} · Corte ${pct(b.utilization_parts.esforco_transverso)} · Flecha ${pct(b.utilization_parts.flecha)} (${num(b.deflection_mm, 1)} / ${num(b.deflection_limit_mm, 1)} mm)`}>
                      <td className="py-0.5">Viga {i + 1} <span className="text-muted-foreground">{num(b.b_m * 100)}×{num(b.h_m * 100)}</span></td>
                      <td className="text-right tabular-nums">M {num(Math.max(b.m_span_knm, b.m_support_knm), 0)} kN·m</td>
                      <td className="text-right tabular-nums">{num(Math.max(b.as_span_cm2, b.as_support_cm2), 1)} cm²</td>
                      <td className={`text-right tabular-nums font-medium ${STATUS[b.status]?.cls}`}>{pct(b.utilization)}</td>
                    </tr>
                  ))}
                  {analysis.columns.map((c, i) => (
                    <tr key={c.guid} className="border-b last:border-0" title={c.warnings.join(" ")}>
                      <td className="py-0.5">Pilar {i + 1} <span className="text-muted-foreground">{num(c.b_m * 100)}×{num(c.h_m * 100)}</span></td>
                      <td className="text-right tabular-nums">N {num(c.n_ed_kn, 0)} kN</td>
                      <td className="text-right tabular-nums">{num(c.as_min_cm2, 1)} cm²</td>
                      <td className={`text-right tabular-nums font-medium ${STATUS[c.status]?.cls}`}>{pct(c.utilization)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[11px] text-muted-foreground mt-1">
                Laje: G {num(analysis.slab_loads.g_kn_m2, 1)} + Q {num(analysis.slab_loads.q_kn_m2, 1)} kN/m² · ELU {analysis.combinations.ELU}.
                {" "}{analysis.scope} A validar por um engenheiro.
              </p>
              {(analysis.model_warnings?.length || 0) + analysis.warnings.length > 0 && (
                <ul className="text-[11px] text-amber-700 dark:text-amber-300 mt-1 space-y-0.5">
                  {[...(analysis.model_warnings || []), ...analysis.warnings].slice(0, 10).map((w, i) => <li key={i}>{w.detail}{w.source_id ? ` · ${w.source_id}` : ""}</li>)}
                </ul>
              )}
            </section>
          )}

          <section data-testid="bim-selection">
            <h2 className="font-semibold mb-1">Elemento selecionado</h2>
            {!selected ? (
              <p className="text-xs text-muted-foreground">Clique num elemento do modelo.</p>
            ) : (
              <div className="space-y-2">
                <div>
                  <div className="font-medium">{selected.name || "Sem nome"}</div>
                  <div className="text-[11px] text-muted-foreground">{selected.ifcClass}{selected.material ? ` · ${selected.material}` : ""}</div>
                  {selected.guid && <div className="text-[10px] font-mono text-muted-foreground break-all">{selected.guid}</div>}
                </div>
                {selected.psets.map((ps) => (
                  <details key={ps.name} open={ps.name.startsWith("Qto_") || ps.name.startsWith("Pset_")}>
                    <summary className="text-xs font-medium cursor-pointer">{ps.name}</summary>
                    <table className="w-full text-[11px] mt-1">
                      <tbody>
                        {ps.props.map((p) => (
                          <tr key={p.name}>
                            <td className="pr-2 text-muted-foreground align-top">{p.name}</td>
                            <td className="text-right tabular-nums break-all">
                              {typeof p.value === "number" ? num(p.value, 3) : typeof p.value === "boolean" ? (p.value ? "Sim" : "Não") : String(p.value ?? "")}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </details>
                ))}
              </div>
            )}
          </section>
        </aside>
      </div>
    </div>
  );
}
