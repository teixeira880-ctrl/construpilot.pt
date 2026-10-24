import { CadUnitPicker, CadImportInfo } from "@/components/planTakeoff/CadImportInfo";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Upload, Loader2, Ruler, ExternalLink, FileText, Layers, FileDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api, uploadPlan } from "@/lib/api";
import CotesCheckPanel from "@/components/planTakeoff/CotesCheckPanel";
import { runCotesJob } from "@/lib/cotesJobs";
import { InteriorPanel } from "@/components/planTakeoff/InteriorPanel";
import { ReportIssueButton, VersionHistory } from "@/components/planTakeoff/ReportIssue";

const VERDICT = { ok: ["Conforme", "text-emerald-700"], warn: ["A verificar", "text-orange-700"], ko: ["Incoerências", "text-red-700"] };

async function fetchBlobUrl(path) {
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}`, {
     credentials: "include",
  });
  if (!res.ok) throw new Error("image");
  return URL.createObjectURL(await res.blob());
}

function PlanPreview({ plan, pageIndex, highlight, interiorId, mode }) {
  const [src, setSrc] = useState(null);
  const report = plan?.cotes_checks?.[String(pageIndex)];
  useEffect(() => {
    let alive = true;
    setSrc(null);
    if (!plan) return undefined;
    const load = async () => {
      try {
        if (report && mode === "interior") { setSrc(await fetchBlobUrl(`/takeoffs/${plan.plan_id}/cotes/interior-overlay.png?page_index=${pageIndex}&highlight=${interiorId || ""}`)); return; }
        if (report) { setSrc(await fetchBlobUrl(`/takeoffs/${plan.plan_id}/cotes/overlay.png?page_index=${pageIndex}`)); return; }
        const { data } = await api.get(`/takeoffs/${plan.plan_id}/page/${pageIndex}`);
        if (alive && data?.image_png_b64) setSrc(`data:image/png;base64,${data.image_png_b64}`);
      } catch { /* aperçu indisponible */ }
    };
    load();
    return () => { alive = false; };
  }, [plan?.plan_id, pageIndex, report?.recomputed_at, report?.created_at, mode, interiorId]);
  const page = plan?.pages?.[pageIndex];
  const box = mode !== "interior" && highlight && page?.width_px ? {
    left: `${(Math.min(highlight.x1, highlight.x2) / page.width_px) * 100}%`,
    top: `${(Math.min(highlight.y1, highlight.y2) / page.height_px) * 100}%`,
    width: `${(Math.max(4, Math.abs(highlight.x2 - highlight.x1)) / page.width_px) * 100}%`,
    height: `${(Math.max(4, Math.abs(highlight.y2 - highlight.y1)) / page.height_px) * 100}%`,
  } : null;
  return (
    <div className="relative border rounded-sm bg-white overflow-hidden min-h-[320px] flex items-center justify-center" data-testid="cotes-page-preview">
      {src ? <img src={src} alt="Planta" className="w-full h-auto" data-testid="cotes-page-img" />
           : <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {box && <div className="absolute border-4 border-amber-400 rounded-sm pointer-events-none animate-pulse"
                   style={{ ...box, boxShadow: "0 0 0 9999px rgba(15,23,42,0.25)", padding: 12, margin: -12 }} data-testid="cotes-page-highlight" />}
    </div>
  );
}

export default function CotesControl() {
  const [cadFile, setCadFile] = useState(null);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [plans, setPlans] = useState([]);
  const [plan, setPlan] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [interiorId, setInteriorId] = useState(null);
  const [mode, setMode] = useState("cotes");
  const [issueKey, setIssueKey] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [highlight, setHighlight] = useState(null);
  const fileRef = useRef(null);

  const loadPlans = useCallback(async () => {
    const { data } = await api.get("/takeoffs");
    setPlans(data.plans || []);
    return data.plans || [];
  }, []);
  const loadPlan = useCallback(async (id) => {
    if (!id) return;
    const { data } = await api.get(`/takeoffs/${id}`);
    setPlan(data);
  }, []);

  useEffect(() => {
    loadPlans().then((list) => {
      const id = params.get("plan") || list[0]?.plan_id;
      if (id) { loadPlan(id); if (!params.get("plan")) setParams({ plan: id }, { replace: true }); }
    }).catch(() => toast.error("Carregamento das plantas impossível"));
  }, []); // eslint-disable-line

  const select = (id) => { setPlan(null); setPageIndex(0); setHighlight(null); setParams({ plan: id }); loadPlan(id); };

  const upload = async (file, cadUnit) => {
    setCadFile(null);
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (cadUnit) fd.append("cad_unit", cadUnit);
      const data = await uploadPlan(fd);
      toast.success(`Plan « ${file.name} » importada — lance o controlo das cotas`);
      await loadPlans();
      select(data.plan_id);
    } catch (e) {
      if (typeof e?.response?.data?.detail === "string" && e.response.data.detail.includes("CAD_UNIT_REQUIRED")) { setCadFile(file); return; } toast.error(e?.response?.data?.detail || "Não foi possível importar"); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const pageCount = plan?.pages?.length || 0;
  const report = plan?.cotes_checks?.[String(pageIndex)];
  const checkedPages = plan ? Object.keys(plan.cotes_checks || {}).length : 0;
  const [allBusy, setAllBusy] = useState(false);

  const checkAll = async () => {
    setAllBusy(true);
    try {
      const data = await runCotesJob(`/takeoffs/${plan.plan_id}/cotes/check-all`, { tol_pct: 2, tol_cm: 3 });
      const s = data.summary;
      if (s) toast.success(`${s.pages} página(s) controlada(s) — ${s.total} cotas, ${s.ko} incoerência(s)` +
        (data.errors?.length ? ` · ${data.errors.length} página(s) sem cota legível` : ""), { duration: 8000 });
      else toast.error(data.errors?.[0]?.error || "Nenhuma cota legível");
      await loadPlan(plan.plan_id);
    } catch (e) { toast.error(e?.response?.data?.detail || e?.message || "Controlo multipágina impossível"); }
    finally { setAllBusy(false); }
  };

  const downloadAll = async () => {
    try {
      const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/takeoffs/${plan.plan_id}/cotes/report-all.pdf`, {
         credentials: "include",
      });
      if (!res.ok) throw new Error((await res.json().catch(() => ({}))).detail || "Erro do servidor");
      const a = document.createElement("a");
      a.href = URL.createObjectURL(await res.blob());
      a.download = `controlo-cotas-global.pdf`;
      a.click();
      toast.success("Relatório PDF global transferido");
    } catch (e) { toast.error(e.message); }
  };

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 grid gap-5" data-testid="cotes-control-page">
      <CadImportInfo info={plan?.cad_import} />
      {cadFile && <CadUnitPicker file={cadFile} onChoose={unit => upload(cadFile, unit)} onCancel={() => setCadFile(null)} />}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline text-primary">Análise de plantas</p>
          <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2"><Ruler className="h-6 w-6 text-primary" /> Analisar as cotas das plantas</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Importe uma planta (PDF, imagem ou DXF): cada cota inscrita é relida, medida à escala e comparada com o seu valor. As incoerências e as cadeias de cotas erradas são assinaladas, com planta anotada e relatório PDF para enviar.
          </p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.dxf,.dwg" className="hidden"
                 onChange={(e) => upload(e.target.files?.[0])} data-testid="cotes-upload-input" />
          <Button className="rounded-sm gap-2" disabled={uploading} onClick={() => fileRef.current?.click()} data-testid="cotes-upload-btn">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importar uma planta
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={plan?.plan_id || ""} onValueChange={select}>
          <SelectTrigger className="w-full sm:w-[380px] rounded-sm" data-testid="cotes-plan-select"><SelectValue placeholder="Escolher uma planta…" /></SelectTrigger>
          <SelectContent>
            {plans.map((p) => {
              const r = p.cotes_checks?.["0"];
              return (
                <SelectItem key={p.plan_id} value={p.plan_id} data-testid={`cotes-plan-option-${p.plan_id}`}>
                  {p.filename || p.plan_id}{r ? ` — ${VERDICT[r.summary.verdict][0]} (${r.summary.ko} KO)` : " — não controlado"}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
        {pageCount > 1 && (
          <Select value={String(pageIndex)} onValueChange={(v) => { setPageIndex(Number(v)); setHighlight(null); }}>
            <SelectTrigger className="w-[150px] rounded-sm" data-testid="cotes-page-select"><SelectValue /></SelectTrigger>
            <SelectContent>{plan.pages.map((_, i) => <SelectItem key={i} value={String(i)}>Página {i + 1}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {plan && (
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => navigate(`/plan?open=${plan.plan_id}`)} data-testid="cotes-open-editor">
            <ExternalLink className="h-3.5 w-3.5" /> Abrir no editor de plantas
          </Button>
        )}
        {plan && pageCount > 1 && (
          <Button size="sm" className="rounded-sm gap-2" disabled={allBusy} onClick={checkAll} data-testid="cotes-check-all-btn">
            {allBusy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
            {allBusy ? `Controlo das ${pageCount} páginas…` : `Controlar as ${pageCount} pages`}
          </Button>
        )}
        {plan && checkedPages > 1 && (
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={downloadAll} data-testid="cotes-pdf-all-btn">
            <FileDown className="h-3.5 w-3.5" /> PDF global ({checkedPages} páginas)
          </Button>
        )}
        {report && <span className={`text-sm font-medium ${VERDICT[report.summary.verdict][1]}`} data-testid="cotes-control-verdict">{VERDICT[report.summary.verdict][0]}</span>}
        {report?.under_review && <span className="text-xs px-2 py-0.5 rounded-sm bg-orange-500/15 text-orange-700 border border-orange-400" data-testid="cotes-under-review">A rever · {report.open_issues} ocorrência(s) em aberto</span>}
        {report && <ReportIssueButton plan={plan} pageIndex={pageIndex} target={interiorId || (highlight ? `Cota n.º ${highlight.index}` : "")} onReported={() => { setIssueKey((k) => k + 1); loadPlan(plan.plan_id); }} />}
        {report?.interior && (
          <div className="inline-flex rounded-sm border overflow-hidden text-xs" data-testid="cotes-view-mode">
            <button className={`px-2.5 py-1 transition-colors ${mode === "cotes" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`} onClick={() => setMode("cotes")} data-testid="cotes-mode-cotes">Cotas</button>
            <button className={`px-2.5 py-1 transition-colors ${mode === "interior" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`} onClick={() => setMode("interior")} data-testid="cotes-mode-interior">Dimensões interiores</button>
          </div>
        )}
      </div>

      {!plans.length && !uploading && (
        <div className="border border-dashed rounded-sm p-10 text-center text-sm text-muted-foreground" data-testid="cotes-empty">
          <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" /> Nenhuma planta por agora — importe uma planta para começar.
        </div>
      )}

      {plan && (
        <div className="grid lg:grid-cols-[1fr_400px] gap-4 items-start">
          <PlanPreview plan={plan} pageIndex={pageIndex} highlight={highlight} interiorId={interiorId} mode={mode} />
          <CotesCheckPanel plan={plan} pageIndex={pageIndex} refreshPlan={() => loadPlan(plan.plan_id)}
                           selectedIndex={highlight?.index ?? null} onFocusCote={(it) => { setHighlight(it); setMode("cotes"); }} />
        </div>
      )}
      {plan && report && (
        <InteriorPanel interior={report.interior} selected={interiorId} aiInterior={plan?.studies?.[String(pageIndex)]?.interior} planId={plan.plan_id} pageIndex={pageIndex}
                       onSelect={(id) => { setInteriorId(id); setMode("interior"); }}
                       onFocusCote={(idx) => { const it = report.items?.find((x) => x.index === idx); if (it) { setHighlight(it); setMode("cotes"); } }} />
      )}
      {plan && report && <VersionHistory plan={plan} pageIndex={pageIndex} refreshKey={issueKey} onChanged={() => loadPlan(plan.plan_id)} />}
    </div>
  );
}
