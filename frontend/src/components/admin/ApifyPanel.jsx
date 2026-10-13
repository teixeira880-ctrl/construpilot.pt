import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Play, Database, RefreshCw, Download, AlertTriangle, Save, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

const POLL_MS = 4000;
const RUNNING_STATUSES = new Set(["RUNNING", "READY", "RUNNING..."]);

function ResultsTable({ items }) {
  if (!items?.length) return null;
  const cols = [...new Set(items.flatMap((x) => Object.keys(x)))].slice(0, 12);
  const cell = (v) => {
    if (v == null) return "";
    const s = typeof v === "object" ? JSON.stringify(v) : String(v);
    return s.length > 80 ? s.slice(0, 80) + "…" : s;
  };
  return (
    <div className="overflow-x-auto border border-border rounded-sm" data-testid="apify-results-table">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-left text-muted-foreground border-b border-border bg-muted/40">
            {cols.map((c) => <th key={c} className="py-1.5 px-2 font-medium whitespace-nowrap">{c}</th>)}
          </tr>
        </thead>
        <tbody>
          {items.map((r, i) => (
            <tr key={i} className="border-b border-border/40" data-testid={`apify-row-${i}`}>
              {cols.map((c) => <td key={c} className="py-1.5 px-2 align-top">{cell(r[c])}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function ApifyPanel() {
  const [configured, setConfigured] = useState(true);
  const [presets, setPresets] = useState({});
  const [useCase, setUseCase] = useState("leads");
  const [actorId, setActorId] = useState("");
  const [inputJson, setInputJson] = useState("{}");
  const [maxItems, setMaxItems] = useState(50);
  const [persist, setPersist] = useState(true);
  const [emailsOnly, setEmailsOnly] = useState(true);
  const [status, setStatus] = useState("");
  const [items, setItems] = useState([]);
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const pollRef = useRef(null);

  const loadHistory = () => api.get("/admin/apify/history").then(({ data }) => setHistory(data.jobs || [])).catch(() => {});

  useEffect(() => {
    api.get("/admin/apify/presets").then(({ data }) => {
      setConfigured(data.configured);
      setPresets(data.presets || {});
    }).catch(() => {});
    loadHistory();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  const applyPreset = (key) => {
    setUseCase(key);
    const p = presets[key];
    if (p) {
      setActorId(p.actor_id);
      setInputJson(JSON.stringify(p.input, null, 2));
    }
    // Le filtre « e-mails uniquement » n'a de sens que pour la captation de leads.
    setEmailsOnly(key === "leads");
  };
  useEffect(() => { if (Object.keys(presets).length) applyPreset(useCase); /* eslint-disable-next-line */ }, [presets]);

  const poll = (jobId) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const { data } = await api.get(`/admin/apify/jobs/${jobId}`);
        setStatus(data.status);
        if (!RUNNING_STATUSES.has(data.status)) {
          clearInterval(pollRef.current);
          setBusy(false);
          if (data.status === "SUCCEEDED") {
            setItems(data.items || []);
            toast.success(`${data.count} résultat(s)${data.persisted ? " · enregistrés" : ""}`);
          } else {
            toast.error(`Run terminé : ${data.status}`);
          }
          loadHistory();
        }
      } catch (e) {
        clearInterval(pollRef.current);
        setBusy(false);
        toast.error(e?.response?.data?.detail || "Erreur de suivi du run");
      }
    }, POLL_MS);
  };

  const savePreset = async () => {
    let parsed;
    try { parsed = JSON.parse(inputJson || "{}"); }
    catch { toast.error("JSON d'entrée invalide"); return; }
    if (!actorId.trim()) { toast.error("Indiquez l'ID de l'Actor Apify"); return; }
    setBusy(true);
    try {
      const { data } = await api.put(`/admin/apify/presets/${useCase}`, { actor_id: actorId.trim(), input: parsed });
      setPresets(data.presets || {});
      toast.success("Preset enregistré — réutilisé pour les prochains runs.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Enregistrement impossible");
    } finally { setBusy(false); }
  };

  const resetPreset = async () => {
    setBusy(true);
    try {
      const { data } = await api.delete(`/admin/apify/presets/${useCase}`);
      setPresets(data.presets || {});
      const p = (data.presets || {})[useCase];
      if (p) { setActorId(p.actor_id); setInputJson(JSON.stringify(p.input, null, 2)); }
      toast.success("Preset réinitialisé.");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Réinitialisation impossible");
    } finally { setBusy(false); }
  };

  const runScraper = async () => {
    let parsed;
    try { parsed = JSON.parse(inputJson || "{}"); }
    catch { toast.error("JSON d'entrée invalide"); return; }
    if (!actorId.trim()) { toast.error("Indiquez l'ID de l'Actor Apify"); return; }
    setBusy(true); setItems([]); setStatus("RUNNING");
    try {
      const { data } = await api.post("/admin/apify/run", {
        actor_id: actorId.trim(), input: parsed, use_case: useCase,
        max_items: Number(maxItems) || 50, persist, emails_only: emailsOnly,
      });
      toast.success(`Run démarré (${data.run_id})`);
      poll(data.job_id);
    } catch (e) {
      setBusy(false); setStatus("");
      toast.error(e?.response?.data?.detail || "Démarrage impossible");
    }
  };

  const exportCsv = () => {
    if (!items.length) return;
    const cols = [...new Set(items.flatMap((x) => Object.keys(x)))];
    const esc = (v) => `"${String(v == null ? "" : (typeof v === "object" ? JSON.stringify(v) : v)).replace(/"/g, '""')}"`;
    const csv = [cols.join(","), ...items.map((r) => cols.map((c) => esc(r[c])).join(","))].join("\n");
    const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url; a.download = `apify_${useCase}_${Date.now()}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4" data-testid="admin-apify-panel">
      <div>
        <h3 className="font-display font-bold text-lg">Apify — Scraping & automatisations</h3>
        <p className="text-sm text-muted-foreground">
          Lancez des Actors Apify pour capter des leads, collecter des appels d'offres ou
          surveiller les prix. Le token reste côté serveur.
        </p>
      </div>

      {!configured && (
        <div className="surface rounded-sm p-4 flex items-start gap-2 border border-amber-500/40 bg-amber-500/10"
             data-testid="apify-not-configured">
          <AlertTriangle className="h-5 w-5 text-amber-600 mt-0.5" />
          <p className="text-sm">Le token <code>APIFY_API_TOKEN</code> n'est pas encore configuré dans le backend.
            Ajoutez-le pour activer les runs.</p>
        </div>
      )}

      <div className="surface rounded-md p-5 space-y-4">
        <div className="flex flex-wrap gap-2" data-testid="apify-presets">
          {Object.entries(presets).map(([key, p]) => (
            <Button key={key} variant={useCase === key ? "default" : "outline"} size="sm"
                    className="rounded-sm" onClick={() => applyPreset(key)}
                    data-testid={`apify-preset-${key}`}>
              {p.label}
            </Button>
          ))}
        </div>

        <div className="grid sm:grid-cols-2 gap-4">
          <div className="space-y-1.5">
            <Label className="text-xs">ID de l'Actor Apify</Label>
            <Input value={actorId} onChange={(e) => setActorId(e.target.value)}
                   placeholder="apify/google-maps-scraper" className="rounded-sm h-9 text-sm"
                   data-testid="apify-actor-id" />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Nombre max. de résultats</Label>
            <Input type="number" min={1} max={1000} value={maxItems}
                   onChange={(e) => setMaxItems(e.target.value)} className="rounded-sm h-9 text-sm"
                   data-testid="apify-max-items" />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label className="text-xs">Paramètres d'entrée (JSON — propre à l'Actor)</Label>
          <Textarea value={inputJson} onChange={(e) => setInputJson(e.target.value)} rows={6}
                    className="rounded-sm text-xs font-mono resize-y" data-testid="apify-input-json" />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Switch checked={emailsOnly} onCheckedChange={setEmailsOnly} data-testid="apify-emails-only-switch" />
              <Label className="text-sm">Apenas e-mails das empresas</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={persist} onCheckedChange={setPersist} data-testid="apify-persist-switch" />
              <Label className="text-sm flex items-center gap-1"><Database className="h-4 w-4" /> Enregistrer dans la base</Label>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {items.length > 0 && (
              <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={exportCsv}
                      data-testid="apify-export-csv"><Download className="h-4 w-4" /> CSV</Button>
            )}
            <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={savePreset}
                    disabled={busy || !useCase} data-testid="apify-save-preset-btn" title="Enregistrer hashtags / ville / catégories pour ce cas d'usage">
              <Save className="h-4 w-4" /> Enregistrer
            </Button>
            {presets[useCase]?.customized && (
              <Button variant="ghost" size="sm" className="rounded-sm gap-2" onClick={resetPreset}
                      disabled={busy} data-testid="apify-reset-preset-btn"><RotateCcw className="h-4 w-4" /> Défaut</Button>
            )}
            <Button variant="default" size="sm" className="rounded-sm gap-2" onClick={runScraper}
                    disabled={busy || !configured} data-testid="apify-run-btn">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {busy ? `Run… ${status}` : "Rodar"}
            </Button>
          </div>
        </div>
      </div>

      {items.length > 0 && (
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground" data-testid="apify-results-count">{items.length} résultat(s)</p>
          <ResultsTable items={items} />
        </div>
      )}

      <div className="flex items-center justify-between pt-2">
        <h4 className="font-semibold">Historique des runs</h4>
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={loadHistory}
                data-testid="apify-history-refresh"><RefreshCw className="h-4 w-4" /> Actualiser</Button>
      </div>
      {history.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucun run pour le moment.</p>
      ) : (
        <div className="grid gap-2" data-testid="apify-history">
          {history.map((j) => (
            <div key={j.job_id} className="surface rounded-sm p-3 flex flex-wrap items-center gap-3 text-sm"
                 data-testid={`apify-history-${j.job_id}`}>
              <span className="font-mono text-xs text-muted-foreground">{j.actor_id}</span>
              {j.use_case && <span className="text-xs px-2 py-0.5 rounded-full bg-muted">{j.use_case}</span>}
              <span className={`text-xs font-semibold ${j.status === "SUCCEEDED" ? "text-emerald-600" : j.status === "FAILED" ? "text-red-600" : "text-amber-600"}`}>{j.status}</span>
              <span className="text-xs text-muted-foreground">{j.count} item(s){j.persist ? " · enregistrés" : ""}</span>
              <span className="text-xs text-muted-foreground ml-auto">{j.created_at ? new Date(j.created_at).toLocaleString("fr-FR") : ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
