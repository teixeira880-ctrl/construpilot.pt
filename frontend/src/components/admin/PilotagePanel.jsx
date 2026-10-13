import { useCallback, useEffect, useState } from "react";
import {
  Gauge, RefreshCw, TrendingUp, ShieldCheck, ShieldAlert, AlertTriangle,
  CircleAlert, Info, CheckCircle2, ArrowRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const eur = (v) => (v === null || v === undefined ? "não mensurável" : `${Number(v).toFixed(2)} €`);

const SEV = {
  critical: { cls: "border-red-500/40 bg-red-500/10 text-red-600", Icon: CircleAlert, label: "Critique" },
  high: { cls: "border-orange-500/40 bg-orange-500/10 text-orange-600", Icon: ShieldAlert, label: "Prioritaire" },
  medium: { cls: "border-amber-500/40 bg-amber-500/10 text-amber-600", Icon: AlertTriangle, label: "A vigiar" },
  low: { cls: "border-sky-500/40 bg-sky-500/10 text-sky-600", Icon: Info, label: "Info" },
  info: { cls: "border-slate-400/40 bg-slate-400/10 text-slate-500", Icon: Info, label: "Info" },
  success: { cls: "border-emerald-500/40 bg-emerald-500/10 text-emerald-600", Icon: CheckCircle2, label: "OK" },
};
const BAND = {
  good: { cls: "text-emerald-600", bar: "#059669", label: "Sain" },
  watch: { cls: "text-amber-500", bar: "#F59E0B", label: "A vigiar" },
  critical: { cls: "text-red-600", bar: "#DC2626", label: "Critique" },
};

export default function PilotagePanel({ onOpenBudget }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    setBusy(true);
    api.get("/admin/expenses/cap/pilotage")
      .then(({ data: d }) => setData(d))
      .finally(() => setBusy(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  if (!data) return <p className="text-sm text-muted-foreground" data-testid="pilotage-loading">A carregar a gestão…</p>;

  const band = BAND[data.health?.band] || BAND.good;
  const st = data.status || {};
  const proj = data.projection;

  return (
    <div className="grid gap-6" data-testid="pilotage-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-extrabold flex items-center gap-2">
            <Gauge className="h-5 w-5 text-primary" /> Gestão IA — copiloto do orçamento
          </h2>
          <p className="text-xs text-muted-foreground max-w-2xl mt-1" data-testid="pilotage-headline">
            {data.headline}
          </p>
          <p className="text-[11px] text-muted-foreground mt-0.5">
            Mois {data.month} · recommandations <b>determinísticas</b> (derivadas dos limiares conhecidos, nenhum valor inventado).
          </p>
        </div>
        <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={load} disabled={busy} data-testid="pilotage-refresh">
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Actualiser
        </Button>
      </div>

      {/* Santé + projection */}
      <div className="grid md:grid-cols-3 gap-3">
        <div className="surface rounded-md p-4" data-testid="pilotage-health">
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Índice de saúde</p>
          <p className={`font-display text-3xl font-extrabold mt-1 num ${band.cls}`}>{data.health?.score}/100</p>
          <div className="mt-2 h-2 rounded-full bg-muted overflow-hidden">
            <div className="h-full rounded-full transition-all" style={{ width: `${data.health?.score || 0}%`, background: band.bar }} />
          </div>
          <p className={`text-xs mt-1 font-semibold ${band.cls}`}>{band.label}</p>
          {data.health?.penalties?.length > 0 && (
            <p className="text-[11px] text-muted-foreground mt-1">{data.health.penalties.join(" · ")}</p>
          )}
        </div>
        <div className="surface rounded-md p-4" data-testid="pilotage-used">
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground">Consumido / teto</p>
          <p className="font-display text-3xl font-extrabold mt-1 num">{eur(st.used_eur)}</p>
          <p className="text-xs text-muted-foreground mt-1">sur {eur(st.cap_eur)} · reste {eur(st.remaining_eur)}</p>
          <p className="text-xs mt-1 flex items-center gap-1">
            {data.new_engagements_allowed
              ? <><ShieldCheck className="h-3.5 w-3.5 text-emerald-600" /> Novos compromissos autorizados</>
              : <><ShieldAlert className="h-3.5 w-3.5 text-orange-500" /> Compromissos bloqueados</>}
          </p>
        </div>
        <div className="surface rounded-md p-4" data-testid="pilotage-projection">
          <p className="text-[11px] uppercase tracking-widest text-muted-foreground flex items-center gap-1">
            <TrendingUp className="h-3.5 w-3.5" /> Projeção de fim de mês
          </p>
          {proj ? (
            <>
              <p className={`font-display text-3xl font-extrabold mt-1 num ${proj.over_cap ? "text-red-600" : ""}`}>{eur(proj.projected_eur)}</p>
              <p className="text-xs text-muted-foreground mt-1">ao ritmo de {eur(proj.pace_eur_per_day)}/jour · jour {proj.day}/{proj.days_in_month}</p>
              {proj.over_cap && <p className="text-xs text-red-600 mt-1 font-semibold">Ultrapassaria o teto</p>}
            </>
          ) : (
            <p className="text-sm text-muted-foreground mt-2">Mês passado — projeção não aplicável.</p>
          )}
        </div>
      </div>

      {/* Recommandations / actions */}
      <section className="grid gap-2" data-testid="pilotage-recos">
        <p className="font-semibold text-sm">Recommandations & actions ({data.recommendations?.length || 0})</p>
        {data.recommendations?.map((r, i) => {
          const sev = SEV[r.severity] || SEV.info;
          const Icon = sev.Icon;
          return (
            <div key={i} className={`rounded-md border p-3 ${sev.cls}`} data-testid={`pilotage-reco-${i}`}>
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 shrink-0" />
                <span className="font-semibold text-sm">{r.title}</span>
                <span className="ml-auto text-[10px] uppercase tracking-wider font-bold opacity-70">{sev.label}</span>
              </div>
              {r.detail && <p className="text-[13px] mt-1 text-foreground/80">{r.detail}</p>}
              {r.action && (
                <p className="text-[13px] mt-1 flex items-start gap-1 text-foreground/90">
                  <ArrowRight className="h-3.5 w-3.5 shrink-0 mt-0.5" /> {r.action}
                </p>
              )}
            </div>
          );
        })}
      </section>

      {onOpenBudget && (
        <Button size="sm" variant="outline" className="rounded-sm gap-1 w-fit" onClick={onOpenBudget} data-testid="pilotage-open-budget">
          Abrir o detalhe «Teto 500 €» <ArrowRight className="h-3.5 w-3.5" />
        </Button>
      )}
    </div>
  );
}
