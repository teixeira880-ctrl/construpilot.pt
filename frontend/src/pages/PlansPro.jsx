// Page « Analyse de plan Pro » — upload DWG/RVT/IFC/PDF/PNG + résultat Autodesk + Vision.
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { ChantierContextBar, useChantierContext } from "@/components/chantiers/ChantierContextBar";
import { toast } from "sonner";

const ACCEPT = ".dwg,.dxf,.rvt,.ifc,.nwc,.nwd,.pdf,.png,.jpg,.jpeg,.webp";
const STATUS_LABELS = {
  queued: "En file d'attente", autodesk_translating: "A ler o ficheiro CAD…", autodesk_done: "Fichier CAO lu",
  running_vision: "A ler a planta…", done: "Bem-sucedido", needs_review: "A verificar", partial: "Partiel",
  failed: "Falhado", cancelled: "Anulado", autodesk_error: "Falhado (CAD)", error: "Falhado",
};
const FINAL = ["done", "needs_review", "partial", "failed", "cancelled", "autodesk_error", "error"];
const STATUS_TONE = { done: "text-emerald-700", needs_review: "text-amber-700", partial: "text-amber-700", failed: "text-red-700", error: "text-red-700", autodesk_error: "text-red-700" };
const HAS_RESULT = ["done", "needs_review", "partial"];

export default function PlansPro() {
  const [file, setFile] = useState(null);
  const [job, setJob] = useState(null);
  const [result, setResult] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [history, setHistory] = useState([]);
  const pollRef = useRef(null);
  const [netIssue, setNetIssue] = useState(false);
  const { chantierId, chantier } = useChantierContext();

  const loadHistory = () => api.get("/plans-pro/history?limit=8").then(({ data }) => setHistory(data.items || [])).catch(() => {});

  useEffect(() => {
    loadHistory();
    const jobParam = new URLSearchParams(window.location.search).get("job");
    if (jobParam) api.get(`/plans-pro/job/${jobParam}`).then(({ data }) => openJob(data)).catch(() => toast.error("Analyse introuvable"));
    return () => clearTimeout(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const loadResult = async (jobId) => {
    const { data: res } = await api.get(`/plans-pro/job/${jobId}/result`);
    setResult(res);
  };

  const openJob = async (h) => {
    setResult(null);
    setJob(h);
    setNetIssue(false);
    if (HAS_RESULT.includes(h.status)) await loadResult(h.job_id);
    else if (!FINAL.includes(h.status)) startPolling(h.job_id);
  };

  const retry = async (jobId) => {
    try {
      const { data } = await api.post(`/plans-pro/job/${jobId}/retry`);
      toast.success("Análise relançada");
      setResult(null);
      setJob(data);
      startPolling(data.job_id);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Relançamento impossível");
    }
  };

  const upload = async (e) => {
    e.preventDefault();
    if (!file) return;
    setResult(null);
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (chantierId) fd.append("chantier_id", chantierId);
      const { data } = await api.post("/plans-pro/upload", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setJob(data);
      startPolling(data.job_id);
    } catch (err) {
      toast.error(err?.response?.status === 429 ? "Limite atteinte : 20 analyses par heure." : err?.response?.data?.detail || "Envio impossível");
    } finally {
      setUploading(false);
    }
  };

  // A10 — polling sans chevauchement (setTimeout chaîné), perte réseau ≠ échec du traitement
  const startPolling = (jobId) => {
    clearTimeout(pollRef.current);
    let failures = 0;
    const tick = async () => {
      try {
        const { data } = await api.get(`/plans-pro/job/${jobId}`);
        failures = 0;
        setNetIssue(false);
        setJob(data);
        if (HAS_RESULT.includes(data.status)) {
          await loadResult(jobId);
          loadHistory();
          if (data.status !== "done") toast.warning(data.help || "Resultado a verificar");
          return;
        }
        if (FINAL.includes(data.status)) {
          loadHistory();
          toast.error(data.error || "A análise falhou");
          return;
        }
      } catch (err) {
        if (err?.response?.status === 404 || err?.response?.status === 401) { toast.error("Análise não encontrada ou sessão expirada"); return; }
        failures += 1;
        if (failures >= 3) { setNetIssue(true); return; }
      }
      pollRef.current = setTimeout(tick, 3000);
    };
    pollRef.current = setTimeout(tick, 1500);
  };

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-8 space-y-6" data-testid="plans-pro-page">
      <ChantierContextBar chantierId={chantierId} chantier={chantier} />
      <header>
        <h1 className="text-2xl md:text-3xl font-semibold">Análise de planta Pro</h1>
        <p className="text-sm text-slate-500">
          Autodesk (DWG / RVT / IFC / PDF) + cascata Visão IA Assistente Construção + verificação de normas Perplexity.
        </p>
      </header>

      <form onSubmit={upload} data-testid="plans-pro-form" className="rounded-2xl border border-slate-200 dark:border-slate-800 p-6 flex flex-col md:flex-row items-center gap-4">
        <input type="file" accept={ACCEPT} data-testid="plans-pro-file-input"
               onChange={(e) => setFile(e.target.files?.[0] || null)}
               className="flex-1 text-sm" />
        <button type="submit" disabled={!file || uploading} data-testid="plans-pro-submit-btn"
                className="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60">
          {uploading ? "Envoi…" : "Analyser"}
        </button>
      </form>

      {job && !result && (
        <div data-testid="plans-pro-job-status" className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-6 space-y-2">
          <div className="text-sm">
            <span className="font-medium">Statut : </span><span className={STATUS_TONE[job.status] || ""} data-testid="plans-pro-status-label">{STATUS_LABELS[job.status] || job.status}</span>
            {job.progress && !FINAL.includes(job.status) && <span className="ml-2 text-slate-500">({job.progress})</span>}
          </div>
          {job.help && <p className="text-xs text-slate-500">{job.help}</p>}
          {netIssue && (
            <div className="flex items-center gap-3 text-xs text-amber-700" data-testid="plans-pro-net-issue">
              Ligação perdida: a análise continua do lado do servidor, mas o seu acompanhamento foi interrompido.
              <button type="button" className="underline" onClick={() => { setNetIssue(false); startPolling(job.job_id); }} data-testid="plans-pro-resume-btn">Retomar o acompanhamento</button>
            </div>
          )}
          {["failed", "error", "autodesk_error"].includes(job.status) && (
            <div className="text-xs text-red-700 space-y-1" data-testid="plans-pro-failed">
              <p>{job.error || "Nenhum resultado utilizável."}</p>
              {(job.checks || []).length > 0 && <ul className="list-disc ml-4">{job.checks.map((c, i) => <li key={i}>{c}</li>)}</ul>}
              <button type="button" className="mt-1 px-3 py-1.5 rounded-lg bg-slate-900 text-white hover:bg-slate-700" onClick={() => retry(job.job_id)} data-testid="plans-pro-retry-btn">Relancer l'analyse</button>
            </div>
          )}
          <div className="w-full bg-slate-200 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
            <div className="h-full bg-emerald-500 transition-all" style={{
              width: (job.progress || "0%"),
            }} />
          </div>
        </div>
      )}

      {result && (
        <section className="space-y-6" data-testid="plans-pro-result">
          {result.status && result.status !== "done" && (
            <div className={`rounded-xl border p-4 text-sm ${result.status === "failed" ? "border-red-300 bg-red-50 dark:bg-red-950/30" : "border-amber-300 bg-amber-50 dark:bg-amber-950/30"}`} data-testid="plans-pro-result-status">
              <p className="font-medium">{STATUS_LABELS[result.status]} — {result.help}</p>
              {result.error && <p className="text-xs mt-1">{result.error}</p>}
              {(result.checks || []).length > 0 && <ul className="text-xs mt-1 list-disc ml-4">{result.checks.map((c, i) => <li key={i}>{c}</li>)}</ul>}
              {result.can_retry && <button type="button" className="mt-2 px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs hover:bg-slate-700" onClick={() => retry(result.job_id)} data-testid="plans-pro-result-retry-btn">Relancer l'analyse</button>}
            </div>
          )}
          {result.status === "done" && (result.checks || []).length > 0 && (
            <p className="text-xs text-emerald-700" data-testid="plans-pro-result-checks">{result.checks.join(" · ")}</p>
          )}
          <div className="grid md:grid-cols-3 gap-4">
            {result.autodesk?.thumbnail && (
              <img src={result.autodesk.thumbnail} alt="Pré-visualização Autodesk" data-testid="plans-pro-thumbnail"
                   className="rounded-lg border border-slate-200 dark:border-slate-800 object-contain w-full aspect-square bg-white" />
            )}
            <div className="md:col-span-2 space-y-2">
              <h2 className="font-semibold">Resumo</h2>
              <div className="text-sm space-y-1">
                <div><span className="text-slate-500">Fichier :</span> {result.filename}</div>
                {result.autodesk?.urn && <div><span className="text-slate-500">URN :</span> {result.autodesk.urn.slice(0, 40)}…</div>}
                {result.autodesk?.elements_count != null && (
                  <div><span className="text-slate-500">Elementos extraídos:</span> {result.autodesk.elements_count}</div>
                )}
                {result.vision?.plan_type && (
                  <div><span className="text-slate-500">Tipo de planta:</span> {result.vision.plan_type}</div>
                )}
                {result.vision?.providers_used && (
                  <div><span className="text-slate-500">IA vision :</span> {result.vision.providers_used.join(", ")}</div>
                )}
              </div>
            </div>
          </div>

          {result.autodesk?.quantities && Object.keys(result.autodesk.quantities).length > 0 && (
            <div data-testid="plans-pro-quantities">
              <div className="flex items-center justify-between gap-2 mb-2">
                <h2 className="font-semibold">Quantidades agregadas (Autodesk)</h2>
                <a href={`${process.env.REACT_APP_BACKEND_URL}/api/plans-pro/job/${job?.job_id}/quantities.xlsx`} data-testid="plans-pro-xlsx-btn"
                   className="inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-medium hover:bg-slate-700 dark:bg-emerald-600 dark:hover:bg-emerald-700">
                  Exportar em Excel (medição)
                </a>
              </div>
              {Object.values(result.autodesk.quantities).some((q) => q.source === "layers") && (
                <p className="text-xs text-slate-500 mb-2">Ficheiro DWG: contagem das entidades por camada (nomenclatura AIA / portuguesa), agrupadas por elemento. Áreas e volumes só estão disponíveis para os modelos Revit / IFC.</p>
              )}
              <div className="overflow-x-auto">
                <table className="min-w-full text-sm border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
                  <thead className="bg-slate-100 dark:bg-slate-900/60">
                    <tr>
                      <th className="text-left p-2">Categoria</th>
                      <th className="text-right p-2">Elementos</th>
                      <th className="text-right p-2">Superfície (m²)</th>
                      <th className="text-right p-2">Volume (m³)</th>
                      <th className="text-right p-2">Comprimento (m)</th>
                    </tr>
                  </thead>
                  <tbody>
                    {Object.entries(result.autodesk.quantities).map(([cat, q]) => (
                      <tr key={cat} className="border-t border-slate-200 dark:border-slate-800">
                        <td className="p-2 font-medium">{cat}
                          {q.layers?.length > 0 && <div className="text-[11px] text-slate-500 font-normal">{q.layers.slice(0, 4).map((l) => `${l.layer} (${l.count})`).join(" · ")}{q.layers.length > 4 ? " …" : ""}</div>}
                        </td>
                        <td className="p-2 text-right">{q.count}</td>
                        <td className="p-2 text-right">{q.total_area_m2 ?? "—"}</td>
                        <td className="p-2 text-right">{q.total_volume_m3 ?? "—"}</td>
                        <td className="p-2 text-right">{q.total_length_m ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {result.vision?.elements?.length > 0 && (
            <div data-testid="plans-pro-vision-elements">
              <h2 className="font-semibold mb-2">Elementos detetados (Visão IA fundida)</h2>
              {result.vision.source === "autodesk_thumbnail" && (
                <p className="text-xs text-slate-500 mb-2" data-testid="plans-pro-vision-source">Leitura IA efetuada na pré-visualização Autodesk (400 px): completa a contagem por camada, sem a substituir.</p>
              )}
              {(result.vision.warnings || []).length > 0 && (
                <ul className="text-xs text-amber-700 mb-2 list-disc ml-4" data-testid="plans-pro-vision-warnings">{result.vision.warnings.map((w, i) => <li key={i}>{w}</li>)}</ul>
              )}
              <div className="flex flex-wrap gap-2">
                {result.vision.elements.map((el, i) => (
                  <details key={i} className={`text-xs rounded border ${el.disagreement ? "border-amber-400 bg-amber-50 dark:bg-amber-950/30" : "border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60"}`} data-testid={`plans-pro-element-${el.kind}`}>
                    <summary className="px-2 py-1 cursor-pointer">
                      {el.kind} × {el.count != null ? el.count : (el.count_range ? `${el.count_range[0]}–${el.count_range[1]}(a verificar)` : (el.sources_agreed != null ? "?" : "?"))}
                      <span className="text-slate-500 ml-1">
                        {el.observations ? `(${el.contributions}/${el.providers_total} lectures${el.disagreement ? "em desacordo" : " concordantes"})` : `(${el.sources_agreed ?? "?"} lectures — ancien format)`}
                      </span>
                    </summary>
                    {el.observations && (
                      <ul className="px-3 pb-2 text-slate-600 dark:text-slate-400">
                        {el.observations.map((o, j) => <li key={j}>{o.provider} : {o.count}{o.declared_confidence != null ? `(confiança declarada${(o.declared_confidence * 100).toFixed(0)} %)` : ""}{o.notes ? ` — ${o.notes}` : ""}</li>)}
                      </ul>
                    )}
                  </details>
                ))}
              </div>
            </div>
          )}

          {result.vision?.pathologies?.length > 0 && (
            <div>
              <h2 className="font-semibold mb-2 text-amber-700">Patologias detetadas</h2>
              <ul className="text-sm list-disc list-inside">
                {result.vision.pathologies.map((p, i) => <li key={i}>{p}</li>)}
              </ul>
            </div>
          )}

          {result.vision?.applicable_norms?.text && (
            <div>
              <h2 className="font-semibold mb-2">Normes / DTU applicables</h2>
              <div className="rounded-lg border border-slate-200 dark:border-slate-800 p-4 text-sm whitespace-pre-wrap">
                {result.vision.applicable_norms.text}
              </div>
              {result.vision.applicable_norms.citations?.length > 0 && (
                <ul className="text-xs mt-2 space-y-1">
                  {result.vision.applicable_norms.citations.slice(0, 8).map((c, i) => (
                    <li key={i}><a href={c.url} target="_blank" rel="noreferrer" className="text-emerald-700 hover:underline">{c.title || c.url}</a></li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {result.vision?.ok === false && (
            <p data-testid="plans-pro-vision-error" className="text-sm text-amber-700">Análise de visão momentaneamente indisponível: {result.vision.error}</p>
          )}
        </section>
      )}

      {history.length > 0 && (
        <section data-testid="plans-pro-history" className="space-y-2">
          <h2 className="font-semibold">As minhas análises recentes</h2>
          <ul className="grid md:grid-cols-2 gap-2">
            {history.map((h) => (
              <li key={h.job_id}>
                <button type="button" data-testid={`plans-pro-history-${h.job_id}`} onClick={() => openJob(h)}
                        className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-800 p-3 text-sm hover:border-emerald-500/50 flex items-center justify-between gap-2">
                  <span className="font-medium truncate">{h.filename}</span>
                  <span className={`text-xs ${h.status?.endsWith("error") ? "text-amber-700" : "text-slate-500"}`}>{STATUS_LABELS[h.status] || h.status}</span>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
