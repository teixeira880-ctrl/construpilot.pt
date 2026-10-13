// Page « Résoudre un problème BTP » — diagnostic + solutions + graphiques provisionnels.
// Utilise l'API POST /api/btp-solver/solve.
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { api } from "@/lib/api";
import { ChantierContextBar, useChantierContext } from "@/components/chantiers/ChantierContextBar";
import { useAuth } from "@/context/AuthContext";
import { toast } from "sonner";
import { SolverCharts } from "@/components/btpSolver/SolverCharts";

const DOMAIN_LABELS = {
  fissures: "Fissures", humidite: "Humidade", thermique: "Thermique",
  structure: "Structure", sinistre: "Sinistre", reception: "Receção",
  autre: "Autre",
};
const URGENCY_LABELS = { informative: "Informative", planned: "Planeada", urgent: "Urgente", immediate: "Imediata" };
const URGENCY_STYLES = {
  informative: "bg-slate-500/15 text-slate-600 border-slate-500/30",
  planned: "bg-blue-500/15 text-blue-600 border-blue-500/30",
  urgent: "bg-amber-500/15 text-amber-600 border-amber-500/30",
  immediate: "bg-red-500/15 text-red-700 border-red-500/40",
};

export default function BtpSolver() {
  const [params] = useSearchParams();
  const { chantierId, chantier } = useChantierContext();
  const [description, setDescription] = useState("");
  const [region, setRegion] = useState("");
  const [typeBat, setTypeBat] = useState("");
  const [surface, setSurface] = useState("");
  const [age, setAge] = useState("");
  const [budget, setBudget] = useState("");
  const [urgence, setUrgence] = useState("");
  const [loading, setLoading] = useState(false);
  const [photos, setPhotos] = useState([]);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const [quoting, setQuoting] = useState(false);
  const { user } = useAuth();
  const navigate = useNavigate();
  const isPro = user?.account_type !== "particulier" || user?.role === "admin";

  const toQuote = async (solutionId) => {
    setQuoting(true);
    try {
      const { data } = await api.post(`/btp-solver/${result.problem_id}/to-quote`, { solution_id: solutionId || null });
      toast.success(`Rascunho de orçamento criado (${data.lines} ligne${data.lines > 1 ? "s" : ""}, ${Math.round(data.total_ht || 0)} € HT)`, {
        action: { label: "Ouvrir", onClick: () => navigate(data.url) },
      });
      navigate(data.url);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Não foi possível criar o orçamento");
    } finally {
      setQuoting(false);
    }
  };
  const photoRef = useRef(null);

  const addPhotos = async (files) => {
    const list = Array.from(files || []).slice(0, 3 - photos.length);
    if (!list.length) return toast.error("3 photos maximum");
    setUploadingPhoto(true);
    for (const f of list) {
      const fd = new FormData();
      fd.append("file", f);
      try {
        const { data } = await api.post("/btp-solver/photos", fd, { headers: { "Content-Type": "multipart/form-data" } });
        setPhotos((p) => [...p, { ...data, name: f.name, preview: URL.createObjectURL(f) }]);
      } catch (err) {
        toast.error(err?.response?.data?.detail || `Photo « ${f.name}» recusada`);
      }
    }
    setUploadingPhoto(false);
  };
  const photoUrl = (id) => `${process.env.REACT_APP_BACKEND_URL}/api/btp-solver/photos/${id}`;
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const pollRef = useRef(null);

  const loadHistory = () => api.get("/btp-solver/history?limit=8").then(({ data }) => setHistory(data.items || [])).catch(() => {});

  useEffect(() => {
    loadHistory();
    const id = params.get("id");
    if (id) openProblem(id);
    return () => clearTimeout(pollRef.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const openProblem = async (id) => {
    try {
      const { data } = await api.get(`/btp-solver/${id}`);
      if (data.status === "running") { setLoading(true); startPolling(id); return; }
      setResult(data);
    } catch { toast.error("Diagnostic introuvable"); }
  };

  // A10 — polling sans chevauchement ; perte réseau ≠ échec de l'analyse
  const [netIssue, setNetIssue] = useState(null);
  const startPolling = (id) => {
    clearTimeout(pollRef.current);
    setNetIssue(null);
    let failures = 0;
    const tick = async () => {
      try {
        const { data } = await api.get(`/btp-solver/${id}`);
        failures = 0;
        if (data.status === "done") { setResult(data); setLoading(false); loadHistory(); return; }
        if (data.status === "error") { setLoading(false); toast.error(data.error || "Análise impossível de momento"); return; }
      } catch (err) {
        if (err?.response?.status === 404 || err?.response?.status === 401) { setLoading(false); toast.error("Diagnóstico não encontrado ou sessão expirada"); return; }
        failures += 1;
        if (failures >= 3) { setNetIssue(id); return; }
      }
      pollRef.current = setTimeout(tick, 3000);
    };
    pollRef.current = setTimeout(tick, 2000);
  };

  const submit = async (e) => {
    e.preventDefault();
    if (description.trim().length < 10) {
      toast.error("Descreva o problema (mínimo 10 caracteres)");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.post("/btp-solver/solve", {
        description,
        region: region || null,
        type_batiment: typeBat || null,
        surface_m2: surface ? Number(surface) : null,
        age_annees: age ? Number(age) : null,
        urgence_ressentie: urgence || null,
        budget_max_eur: budget ? Number(budget) : null,
        photo_ids: photos.map((p) => p.photo_id),
        chantier_id: chantierId || null,
      });
      setPhotos([]);
      startPolling(data.problem_id);
    } catch (err) {
      const msg = err?.response?.status === 429
        ? "Limite atingido: 10 diagnósticos por hora. Tente novamente mais tarde."
        : err?.response?.data?.detail || "Análise impossível de momento";
      toast.error(typeof msg === "string" ? msg : "Análise impossível de momento");
      setLoading(false);
    }
  };

  return (
    <div className="max-w-6xl mx-auto p-4 md:p-8 space-y-6" data-testid="btp-solver-page">
      <ChantierContextBar chantierId={chantierId} chantier={chantier} />
      <header className="space-y-1">
        <h1 className="text-2xl md:text-3xl font-semibold">Resolver um problema de construção</h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Diagnóstico provisório + soluções orçamentadas + referências normativas (NP/EN, LNEC), em segundos.
        </p>
      </header>

      <form onSubmit={submit} data-testid="btp-solver-form" className="grid gap-4 rounded-2xl border border-slate-200 dark:border-slate-800 p-4 md:p-6 bg-white dark:bg-slate-900/40">
        <label className="grid gap-1">
          <span className="text-sm font-medium">Descreva com precisão o problema *</span>
          <textarea
            data-testid="solver-description-input"
            className="min-h-[110px] rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent p-3 text-sm"
            placeholder="Ex.: fissura horizontal de 3 mm no 1.º andar de uma moradia em blocos de betão de 1985, surgida depois do verão…"
            value={description} onChange={(e) => setDescription(e.target.value)}
            maxLength={4000}
          />
        </label>
        <div className="grid md:grid-cols-3 gap-3">
          <label className="grid gap-1 text-sm">
            <span>Região</span>
            <input data-testid="solver-region-input" className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent p-2" placeholder="Île-de-France" value={region} onChange={(e) => setRegion(e.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            <span>Tipo de edifício</span>
            <input className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent p-2" placeholder="Maison individuelle" value={typeBat} onChange={(e) => setTypeBat(e.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            <span>Superfície (m²)</span>
            <input type="number" className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent p-2" value={surface} onChange={(e) => setSurface(e.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            <span>Idade (anos)</span>
            <input type="number" className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent p-2" value={age} onChange={(e) => setAge(e.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            <span>Budget max (€)</span>
            <input type="number" className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent p-2" value={budget} onChange={(e) => setBudget(e.target.value)} />
          </label>
          <label className="grid gap-1 text-sm">
            <span>Urgence ressentie</span>
            <select className="rounded-lg border border-slate-300 dark:border-slate-700 bg-transparent p-2" value={urgence} onChange={(e) => setUrgence(e.target.value)}>
              <option value="">—</option>
              <option value="informative">Informative</option>
              <option value="planned">Planeada</option>
              <option value="urgent">Urgente</option>
              <option value="immediate">Imediata</option>
            </select>
          </label>
        </div>
        <div className="flex flex-wrap items-center gap-3" data-testid="solver-photos">
          <input ref={photoRef} type="file" accept="image/png,image/jpeg,image/webp" multiple className="hidden" data-testid="solver-photo-input"
                 onChange={(e) => { addPhotos(e.target.files); e.target.value = ""; }} />
          <button type="button" data-testid="solver-add-photo-btn" disabled={loading || uploadingPhoto || photos.length >= 3} onClick={() => photoRef.current?.click()}
                  className="px-3 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-sm hover:border-emerald-500/60 disabled:opacity-50">
            {uploadingPhoto ? "A enviar a fotografia…" : `Anexar uma fotografia da patologia (${photos.length}/3)`}
          </button>
          <span className="text-xs text-slate-500">JPG, PNG ou WEBP · 8 MB máx. · a IA de visão lê as fotografias para afinar o diagnóstico</span>
          {photos.map((p) => (
            <span key={p.photo_id} className="relative inline-block" data-testid={`solver-photo-${p.photo_id}`}>
              <img src={p.preview} alt={p.name} className="h-16 w-16 object-cover rounded-lg border border-slate-200 dark:border-slate-700" />
              <button type="button" aria-label="Remover a fotografia" data-testid={`solver-photo-remove-${p.photo_id}`}
                      onClick={() => setPhotos((ps) => ps.filter((x) => x.photo_id !== p.photo_id))}
                      className="absolute -top-2 -right-2 h-5 w-5 rounded-full bg-slate-800 text-white text-xs leading-5 text-center">×</button>
            </span>
          ))}
        </div>
        <div className="flex justify-end">
          <button type="submit" data-testid="solver-submit-btn" disabled={loading} className="px-5 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-medium disabled:opacity-60">
            {loading ? "Analyse en cours…" : "Analyser"}
          </button>
        </div>
      </form>

      {loading && (
        <div data-testid="solver-loading" className="rounded-xl border border-dashed border-slate-300 dark:border-slate-700 p-6 text-sm text-slate-500">
          O solucionador consulta as fontes técnicas (Diário da República, LNEC, IPQ) e depois estrutura a resposta. Pode demorar 1 a 2 minutos; pode ficar nesta página.
          {netIssue && (
            <div className="mt-2 flex items-center gap-3 text-amber-700" data-testid="solver-net-issue">
              Ligação perdida: a análise continua do lado do servidor, mas o seu acompanhamento foi interrompido.
              <button type="button" className="underline" onClick={() => startPolling(netIssue)} data-testid="solver-resume-btn">Retomar o acompanhamento</button>
            </div>
          )}
        </div>
      )}

      {result && (
        <section className="space-y-6" data-testid="solver-result">
          <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 md:p-6 bg-slate-50/60 dark:bg-slate-900/40 space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <span data-testid="solver-domain" className="inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border bg-emerald-500/10 text-emerald-700 border-emerald-500/30">
                {DOMAIN_LABELS[result.domain] || result.domain}
              </span>
              <span data-testid="solver-urgency" className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${URGENCY_STYLES[result.urgency] || ""}`}>
                {URGENCY_LABELS[result.urgency] || result.urgency}
              </span>
              <span className="text-xs text-slate-500">ID : {result.problem_id}</span>
              <a href={`${process.env.REACT_APP_BACKEND_URL}/api/btp-solver/${result.problem_id}/report.pdf`} target="_blank" rel="noreferrer"
                 data-testid="solver-pdf-btn"
                 className="ml-auto inline-flex items-center px-3 py-1.5 rounded-lg bg-slate-900 text-white text-xs font-medium hover:bg-slate-700 dark:bg-emerald-600 dark:hover:bg-emerald-700">
                Transferir o diagnóstico em PDF
              </a>
              {isPro && (
                <button type="button" data-testid="solver-to-quote-btn" disabled={quoting} onClick={() => toQuote()}
                        className="inline-flex items-center px-3 py-1.5 rounded-lg border border-emerald-600 text-emerald-700 dark:text-emerald-400 text-xs font-medium hover:bg-emerald-50 dark:hover:bg-emerald-900/30 disabled:opacity-60">
                  {quoting ? "A criar o orçamento…" : "Criar um rascunho de orçamento"}
                </button>
              )}
            </div>
            <p className="text-base leading-relaxed">{result.summary}</p>
            {result.photo_ids?.length > 0 && (
              <div className="flex flex-wrap gap-2" data-testid="solver-result-photos">
                {result.photo_ids.map((id) => <img key={id} src={photoUrl(id)} alt="Fotografia da patologia" className="h-24 w-24 object-cover rounded-lg border border-slate-200 dark:border-slate-700" />)}
              </div>
            )}
            {result.photo_analysis && (
              <details className="text-sm" data-testid="solver-photo-analysis">
                <summary className="cursor-pointer font-medium">Leitura das fotografias pela IA de visão</summary>
                <p className="mt-2 whitespace-pre-wrap text-slate-600 dark:text-slate-400">{result.photo_analysis}</p>
              </details>
            )}
            <p className="text-xs text-slate-500 italic">{result.disclaimer}</p>
          </div>

          {result.causes?.length > 0 && (
            <div data-testid="solver-causes">
              <h2 className="text-lg font-semibold mb-3">Causes probables</h2>
              <ul className="space-y-2">
                {result.causes.map((c, i) => (
                  <li key={i} className="rounded-lg border border-slate-200 dark:border-slate-800 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-medium">{c.label}</span>
                      <span className={`text-xs px-2 py-0.5 rounded border ${
                        c.confidence === "high" ? "text-emerald-700 border-emerald-500/30 bg-emerald-500/10" :
                        c.confidence === "medium" ? "text-amber-700 border-amber-500/30 bg-amber-500/10" :
                        "text-slate-600 border-slate-400/30 bg-slate-400/10"
                      }`}>{c.confidence}</span>
                    </div>
                    <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">{c.explanation}</p>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {result.solutions?.length > 0 && (
            <div data-testid="solver-solutions">
              <h2 className="text-lg font-semibold mb-3">Soluções propostas</h2>
              <div className="grid md:grid-cols-2 gap-4">
                {result.solutions.map((s) => (
                  <article key={s.id} className={`rounded-xl border p-4 space-y-2 ${
                    s.recommended ? "border-emerald-500/50 bg-emerald-50/40 dark:bg-emerald-900/10" : "border-slate-200 dark:border-slate-800"
                  }`}>
                    <div className="flex items-start justify-between gap-2">
                      <h3 className="font-semibold">{s.label}</h3>
                      <div className="flex items-center gap-2">
                        {s.recommended && <span className="text-xs px-2 py-0.5 rounded bg-emerald-600 text-white">Recomendado</span>}
                        {isPro && (
                          <button type="button" data-testid={`solver-solution-quote-${s.id}`} disabled={quoting} onClick={() => toQuote(s.id)}
                                  className="text-xs px-2 py-0.5 rounded border border-slate-300 dark:border-slate-700 hover:border-emerald-500 disabled:opacity-60">
                            → Orçamento
                          </button>
                        )}
                      </div>
                    </div>
                    <p className="text-sm text-slate-600 dark:text-slate-400">{s.description}</p>
                    <div className="grid grid-cols-2 gap-2 text-sm">
                      {s.cost_min_eur != null && (
                        <div><span className="text-slate-500">Custo:</span> {Math.round(s.cost_min_eur)}–{Math.round(s.cost_max_eur || s.cost_min_eur)} € HT</div>
                      )}
                      {s.duration_days_min != null && (
                        <div><span className="text-slate-500">Duração:</span> {s.duration_days_min}–{s.duration_days_max || s.duration_days_min} j</div>
                      )}
                      <div><span className="text-slate-500">Risque :</span> {s.risk}</div>
                      {s.warranty_years && <div><span className="text-slate-500">Garantie :</span> {s.warranty_years} ans</div>}
                    </div>
                    {s.steps?.length > 0 && (
                      <details className="text-sm">
                        <summary className="cursor-pointer text-slate-500">Etapas ({s.steps.length})</summary>
                        <ol className="list-decimal list-inside mt-2 space-y-1">
                          {s.steps.map((st, i) => <li key={i}>{st.text}</li>)}
                        </ol>
                      </details>
                    )}
                  </article>
                ))}
              </div>
            </div>
          )}

          {result.charts?.length > 0 && (
            <div data-testid="solver-charts">
              <h2 className="text-lg font-semibold mb-3">Comparatifs visuels</h2>
              <SolverCharts charts={result.charts} />
            </div>
          )}

          {result.references?.length > 0 && (
            <div data-testid="solver-references">
              <h2 className="text-lg font-semibold mb-3">Referências</h2>
              <ul className="text-sm space-y-1">
                {result.references.map((r, i) => (
                  <li key={i}>
                    <span className="text-xs uppercase text-slate-500 mr-2">{r.kind}</span>
                    {r.url ? <a href={r.url} target="_blank" rel="noreferrer" className="text-emerald-700 hover:underline">{r.code}</a> : <span>{r.code}</span>}
                    {r.title && <span className="text-slate-500"> — {r.title}</span>}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </section>
      )}

      {history.length > 0 && (
        <section data-testid="solver-history" className="space-y-2">
          <h2 className="text-lg font-semibold">Os meus diagnósticos recentes</h2>
          <ul className="grid md:grid-cols-2 gap-2">
            {history.map((h) => (
              <li key={h.problem_id}>
                <button type="button" data-testid={`solver-history-${h.problem_id}`} onClick={() => openProblem(h.problem_id)}
                        className="w-full text-left rounded-lg border border-slate-200 dark:border-slate-800 p-3 text-sm hover:border-emerald-500/50">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium truncate">{DOMAIN_LABELS[h.domain] || h.domain || "Diagnostic"}</span>
                    <span className="text-xs text-slate-500">{h.status === "done" ? new Date(h.generated_at_iso).toLocaleDateString("fr-FR") : h.status === "error" ? "Erro" : "En cours…"}</span>
                  </div>
                  <p className="text-xs text-slate-500 line-clamp-2 mt-1">{h.summary || h.description}</p>
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
