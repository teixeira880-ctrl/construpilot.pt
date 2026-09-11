import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Upload, Loader2, Ruler, ExternalLink, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import CotesCheckPanel from "@/components/planTakeoff/CotesCheckPanel";

const VERDICT = { ok: ["Conforme", "text-emerald-700"], warn: ["À vérifier", "text-orange-700"], ko: ["Incohérences", "text-red-700"] };

async function fetchBlobUrl(path) {
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api${path}`, {
    headers: { Authorization: `Bearer ${localStorage.getItem("construpilot_token")}` }, credentials: "include",
  });
  if (!res.ok) throw new Error("image");
  return URL.createObjectURL(await res.blob());
}

function PlanPreview({ plan, pageIndex, highlight }) {
  const [src, setSrc] = useState(null);
  const report = plan?.cotes_checks?.[String(pageIndex)];
  useEffect(() => {
    let alive = true;
    setSrc(null);
    if (!plan) return undefined;
    const load = async () => {
      try {
        if (report) { setSrc(await fetchBlobUrl(`/takeoffs/${plan.plan_id}/cotes/overlay.png?page_index=${pageIndex}`)); return; }
        const { data } = await api.get(`/takeoffs/${plan.plan_id}/page/${pageIndex}`);
        if (alive && data?.image_png_b64) setSrc(`data:image/png;base64,${data.image_png_b64}`);
      } catch { /* aperçu indisponible */ }
    };
    load();
    return () => { alive = false; };
  }, [plan?.plan_id, pageIndex, report?.recomputed_at, report?.created_at]);
  const page = plan?.pages?.[pageIndex];
  const box = highlight && page?.width_px ? {
    left: `${(Math.min(highlight.x1, highlight.x2) / page.width_px) * 100}%`,
    top: `${(Math.min(highlight.y1, highlight.y2) / page.height_px) * 100}%`,
    width: `${(Math.max(4, Math.abs(highlight.x2 - highlight.x1)) / page.width_px) * 100}%`,
    height: `${(Math.max(4, Math.abs(highlight.y2 - highlight.y1)) / page.height_px) * 100}%`,
  } : null;
  return (
    <div className="relative border rounded-sm bg-white overflow-hidden min-h-[320px] flex items-center justify-center" data-testid="cotes-page-preview">
      {src ? <img src={src} alt="Plan" className="w-full h-auto" data-testid="cotes-page-img" />
           : <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {box && <div className="absolute border-4 border-amber-400 rounded-sm pointer-events-none animate-pulse"
                   style={{ ...box, boxShadow: "0 0 0 9999px rgba(15,23,42,0.25)", padding: 12, margin: -12 }} data-testid="cotes-page-highlight" />}
    </div>
  );
}

export default function CotesControl() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [plans, setPlans] = useState([]);
  const [plan, setPlan] = useState(null);
  const [pageIndex, setPageIndex] = useState(0);
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
    }).catch(() => toast.error("Chargement des plans impossible"));
  }, []); // eslint-disable-line

  const select = (id) => { setPlan(null); setPageIndex(0); setHighlight(null); setParams({ plan: id }); loadPlan(id); };

  const upload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/takeoffs/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`Plan « ${file.name} » importé — lancez le contrôle des cotes`);
      await loadPlans();
      select(data.plan_id);
    } catch (e) { toast.error(e?.response?.data?.detail || "Import impossible"); }
    finally { setUploading(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const pageCount = plan?.pages?.length || 0;
  const report = plan?.cotes_checks?.[String(pageIndex)];

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 grid gap-5" data-testid="cotes-control-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="overline text-primary">Analyse de plans</p>
          <h1 className="text-2xl sm:text-3xl font-bold flex items-center gap-2"><Ruler className="h-6 w-6 text-primary" /> Analyser les cotes des plans</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-2xl">
            Importez un plan (PDF, image ou DXF) : chaque cote inscrite est relue, mesurée à l'échelle et comparée à sa valeur.
            Les incohérences et les chaînes de cotes fausses sont signalées, avec plan annoté et rapport PDF envoyable.
          </p>
        </div>
        <div className="flex gap-2">
          <input ref={fileRef} type="file" accept=".pdf,.png,.jpg,.jpeg,.dxf,.dwg" className="hidden"
                 onChange={(e) => upload(e.target.files?.[0])} data-testid="cotes-upload-input" />
          <Button className="rounded-sm gap-2" disabled={uploading} onClick={() => fileRef.current?.click()} data-testid="cotes-upload-btn">
            {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importer un plan
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-3">
        <Select value={plan?.plan_id || ""} onValueChange={select}>
          <SelectTrigger className="w-full sm:w-[380px] rounded-sm" data-testid="cotes-plan-select"><SelectValue placeholder="Choisir un plan…" /></SelectTrigger>
          <SelectContent>
            {plans.map((p) => {
              const r = p.cotes_checks?.["0"];
              return (
                <SelectItem key={p.plan_id} value={p.plan_id} data-testid={`cotes-plan-option-${p.plan_id}`}>
                  {p.filename || p.plan_id}{r ? ` — ${VERDICT[r.summary.verdict][0]} (${r.summary.ko} KO)` : " — non contrôlé"}
                </SelectItem>
              );
            })}
          </SelectContent>
        </Select>
        {pageCount > 1 && (
          <Select value={String(pageIndex)} onValueChange={(v) => { setPageIndex(Number(v)); setHighlight(null); }}>
            <SelectTrigger className="w-[150px] rounded-sm" data-testid="cotes-page-select"><SelectValue /></SelectTrigger>
            <SelectContent>{plan.pages.map((_, i) => <SelectItem key={i} value={String(i)}>Page {i + 1}</SelectItem>)}</SelectContent>
          </Select>
        )}
        {plan && (
          <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => navigate(`/plan?open=${plan.plan_id}`)} data-testid="cotes-open-editor">
            <ExternalLink className="h-3.5 w-3.5" /> Ouvrir dans l'éditeur de plan
          </Button>
        )}
        {report && <span className={`text-sm font-medium ${VERDICT[report.summary.verdict][1]}`} data-testid="cotes-control-verdict">{VERDICT[report.summary.verdict][0]}</span>}
      </div>

      {!plans.length && !uploading && (
        <div className="border border-dashed rounded-sm p-10 text-center text-sm text-muted-foreground" data-testid="cotes-empty">
          <FileText className="h-8 w-8 mx-auto mb-2 opacity-50" /> Aucun plan pour l'instant — importez un plan pour commencer.
        </div>
      )}

      {plan && (
        <div className="grid lg:grid-cols-[1fr_400px] gap-4 items-start">
          <PlanPreview plan={plan} pageIndex={pageIndex} highlight={highlight} />
          <CotesCheckPanel plan={plan} pageIndex={pageIndex} refreshPlan={() => loadPlan(plan.plan_id)}
                           selectedIndex={highlight?.index ?? null} onFocusCote={(it) => setHighlight(it)} />
        </div>
      )}
    </div>
  );
}
