import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Gauge, Loader2, Play, RefreshCw, ExternalLink, ShieldCheck, TrendingUp, TrendingDown } from "lucide-react";

const STATUS = {
  ok: { cls: "bg-emerald-500/15 text-emerald-600 border-emerald-500/30", label: "Cohérent" },
  warning: { cls: "bg-destructive/15 text-destructive border-destructive/30", label: "Écart" },
  undetermined: { cls: "bg-muted text-muted-foreground border-border", label: "Indéterminé" },
};

const fmt = (n) => (n === null || n === undefined ? "—" : `${Number(n).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);

export default function CalcAuditorPanel() {
  const [audit, setAudit] = useState(null);
  const [threshold, setThreshold] = useState(20);
  const [configured, setConfigured] = useState(true);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);
  const pollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/calc-audit/latest");
      setAudit(data.audit || null);
      setConfigured(data.configured !== false);
      if (data.threshold_pct) setThreshold(data.threshold_pct);
      setRunning((data.audit?.status) === "running");
    } catch { /* */ }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Poll tant qu'une audit tourne
  useEffect(() => {
    if (running) {
      pollRef.current = setInterval(load, 3000);
      return () => clearInterval(pollRef.current);
    }
    if (pollRef.current) clearInterval(pollRef.current);
  }, [running, load]);

  const runNow = async () => {
    setRunning(true);
    try {
      const { data } = await api.post("/admin/calc-audit/run");
      toast.success(data.already ? "Audit déjà en cours" : "Audit lancé", { description: "Comparaison des prix de référence au marché (Perplexity)." });
      load();
    } catch (e) {
      setRunning(false);
      toast.error(e?.response?.data?.detail || "Lancement impossible");
    }
  };

  const items = audit?.items || [];
  const sum = audit?.summary || {};

  return (
    <div className="space-y-6" data-testid="calc-auditor-panel">
      <div className="flex items-start gap-3">
        <span className="h-11 w-11 rounded-lg bg-primary/10 grid place-items-center shrink-0"><Gauge className="h-6 w-6 text-primary" /></span>
        <div className="flex-1">
          <h2 className="font-display text-2xl font-bold">Auditeur de cohérence des calculs</h2>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Compare les <strong>prix de référence</strong> des moteurs déterministes au prix de <strong>marché actuel</strong> (France, via recherche web Perplexity avec sources) et signale les écarts supérieurs à ±{threshold} %.
          </p>
          <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Zéro hallucination : les prix de marché proviennent du web (citations). Les quantités des moteurs restent déterministes.</p>
        </div>
        <div className="flex gap-2 shrink-0">
          <Button variant="outline" size="icon" onClick={load} title="Rafraîchir" data-testid="calc-auditor-refresh"><RefreshCw className="h-4 w-4" /></Button>
          <Button onClick={runNow} disabled={running || !configured} className="gap-2" data-testid="calc-auditor-run">
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />} {running ? "Audit en cours…" : "Lancer l'audit"}
          </Button>
        </div>
      </div>

      {!configured && (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-sm text-amber-700" data-testid="calc-auditor-unconfigured">
          Perplexity n'est pas configuré (PERPLEXITY_API_KEY). L'audit ne peut pas récupérer les prix de marché.
        </div>
      )}

      {/* Résumé */}
      {audit && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3" data-testid="calc-auditor-summary">
          {[
            { k: "total", label: "Articles audités", val: sum.total ?? items.length },
            { k: "ok", label: "Cohérents", val: sum.ok ?? 0, cls: "text-emerald-600" },
            { k: "warning", label: "Écarts signalés", val: sum.warning ?? 0, cls: "text-destructive" },
            { k: "undetermined", label: "Indéterminés", val: sum.undetermined ?? 0, cls: "text-muted-foreground" },
          ].map((c) => (
            <div key={c.k} className="rounded-lg border border-border bg-card p-4">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">{c.label}</p>
              <p className={`text-2xl font-bold mt-1 ${c.cls || ""}`}>{c.val}</p>
            </div>
          ))}
        </div>
      )}

      {audit && (
        <p className="text-xs text-muted-foreground">
          Dernière audit : {audit.started_at ? new Date(audit.started_at).toLocaleString("fr-FR") : "—"}
          {audit.triggered_by ? ` · déclenchée par ${audit.triggered_by === "scheduler" ? "le planificateur (quotidien)" : "l'administrateur"}` : ""}
          {audit.status === "running" ? " · en cours…" : ""}
        </p>
      )}

      {/* Tableau des résultats */}
      {loading ? (
        <p className="text-sm text-muted-foreground">Chargement…</p>
      ) : !audit ? (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-sm text-muted-foreground" data-testid="calc-auditor-empty">
          Aucune audit pour l'instant. Cliquez sur « Lancer l'audit » (ou attendez l'exécution automatique quotidienne).
        </div>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border" data-testid="calc-auditor-table">
          <table className="w-full text-sm">
            <thead className="bg-secondary/60">
              <tr className="text-left">
                <th className="p-3 font-semibold">Article</th>
                <th className="p-3 font-semibold">Unité</th>
                <th className="p-3 font-semibold text-right">Prix moteur</th>
                <th className="p-3 font-semibold text-right">Prix marché</th>
                <th className="p-3 font-semibold text-right">Écart</th>
                <th className="p-3 font-semibold">État</th>
                <th className="p-3 font-semibold">Sources</th>
              </tr>
            </thead>
            <tbody>
              {items.map((it) => {
                const st = STATUS[it.status] || STATUS.undetermined;
                const dev = it.deviation_pct;
                return (
                  <tr key={it.code} className="border-t border-border align-top" data-testid={`calc-auditor-row-${it.code}`}>
                    <td className="p-3">
                      <p className="font-medium">{it.label}</p>
                      {it.note && <p className="text-xs text-muted-foreground mt-0.5">{it.note}</p>}
                    </td>
                    <td className="p-3 text-muted-foreground">{it.unit}</td>
                    <td className="p-3 text-right tabular-nums">{fmt(it.engine_price)}</td>
                    <td className="p-3 text-right tabular-nums">
                      {fmt(it.market_price)}
                      {(it.low || it.high) && <span className="block text-[11px] text-muted-foreground">{fmt(it.low)}–{fmt(it.high)}</span>}
                    </td>
                    <td className="p-3 text-right tabular-nums">
                      {dev === null || dev === undefined ? "—" : (
                        <span className={`inline-flex items-center gap-1 font-semibold ${it.status === "warning" ? "text-destructive" : "text-foreground"}`}>
                          {dev > 0 ? <TrendingUp className="h-3.5 w-3.5" /> : dev < 0 ? <TrendingDown className="h-3.5 w-3.5" /> : null}
                          {dev > 0 ? "+" : ""}{dev} %
                        </span>
                      )}
                    </td>
                    <td className="p-3">
                      <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[10px] font-semibold uppercase ${st.cls}`}>{st.label}</span>
                    </td>
                    <td className="p-3">
                      <div className="flex flex-col gap-1 max-w-[180px]">
                        {(it.sources || []).slice(0, 3).map((s, i) => (
                          <a key={i} href={s.url} target="_blank" rel="noreferrer" className="text-xs text-primary hover:underline flex items-center gap-1 truncate" title={s.title || s.url}>
                            <ExternalLink className="h-3 w-3 shrink-0" /> <span className="truncate">{s.title || s.url}</span>
                          </a>
                        ))}
                        {(!it.sources || it.sources.length === 0) && <span className="text-xs text-muted-foreground">—</span>}
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
