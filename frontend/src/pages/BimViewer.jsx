import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, Box, Download, FolderOpen, Layers, Loader2, Maximize, Scissors } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api, num } from "@/lib/api";

const CLASS_LABELS = {
  IfcWall: "Paredes", IfcSlab: "Lajes", IfcColumn: "Pilares", IfcBeam: "Vigas", IfcFooting: "Sapatas",
  IfcDoor: "Portas", IfcWindow: "Janelas", IfcSpace: "Divisões",
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

async function blobToText(blob) {
  try { return JSON.parse(await blob.text()).detail; } catch { return null; }
}

export default function BimViewer() {
  const [sp] = useSearchParams();
  const navigate = useNavigate();
  const planId = sp.get("plan");
  const page = Number(sp.get("page") || 0);
  const query = PARAM_KEYS.filter((k) => sp.get(k)).map((k) => `${k}=${encodeURIComponent(sp.get(k))}`).join("&");

  const hostRef = useRef(null);
  const viewerRef = useRef(null);
  const fileRef = useRef(null);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [summary, setSummary] = useState(null);
  const [selected, setSelected] = useState(null);
  const [section, setSection] = useState(false);
  const [ortho, setOrtho] = useState(false);
  const [ifcBytes, setIfcBytes] = useState(null);
  const [modelName, setModelName] = useState(null);
  const sectionRef = useRef(false);

  // Arranque do motor 3D (import dinâmico: That Open Engine + web-ifc só são descarregados nesta página).
  useEffect(() => {
    let disposed = false;
    let viewer = null;
    (async () => {
      try {
        const { createBimViewer } = await import("@/components/bim/bimEngine");
        if (disposed || !hostRef.current) return;
        viewer = await createBimViewer(hostRef.current, { onSelect: setSelected });
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

  const showBytes = useCallback(async (bytes, name) => {
    setBusy(true);
    setSelected(null);
    try {
      await viewerRef.current.loadIfc(bytes, name);
      setIfcBytes(bytes);
      setModelName(name);
      if (sectionRef.current) viewerRef.current.setSection(SECTION_Z);
    } catch (e) {
      console.error(e);
      toast.error("Ficheiro IFC ilegível.");
    } finally { setBusy(false); }
  }, []);

  // Modelo gerado a partir da planta lida.
  const loadFromPlan = useCallback(async () => {
    if (!planId || !viewerRef.current) return;
    setBusy(true);
    setError(null);
    try {
      const base = `/bim/takeoffs/${encodeURIComponent(planId)}/${page}`;
      const [{ data: sum }, { data: blob }] = await Promise.all([
        api.get(`${base}/summary${query ? `?${query}` : ""}`),
        api.get(`${base}/ifc${query ? `?${query}` : ""}`, { responseType: "blob" }),
      ]);
      setSummary(sum);
      await showBytes(await blob.arrayBuffer(), `Planta p.${page + 1}`);
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
    await showBytes(await file.arrayBuffer(), file.name.replace(/\.ifc$/i, ""));
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

  return (
    <div className="flex flex-col h-[calc(100dvh-4rem)] min-h-[480px]" data-testid="bim-viewer-page">
      <div className="flex flex-wrap items-center gap-2 px-3 py-2 border-b bg-background">
        {planId && (
          <Button size="sm" variant="ghost" className="h-8 gap-1" onClick={() => navigate(`/plan?open=${encodeURIComponent(planId)}`)}>
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
        <Button size="sm" className="h-8 gap-1" disabled={!ifcBytes} onClick={download} data-testid="bim-download">
          <Download className="h-4 w-4" /> IFC
        </Button>
      </div>

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
              {error}
            </div>
          )}
        </div>

        <aside className="md:w-80 border-t md:border-t-0 md:border-l overflow-y-auto p-3 space-y-4 text-sm max-h-[45vh] md:max-h-none" data-testid="bim-panel">
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
