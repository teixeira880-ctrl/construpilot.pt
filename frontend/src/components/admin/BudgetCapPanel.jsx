import { useCallback, useEffect, useState } from "react";
import { ShieldAlert, ShieldCheck, RefreshCw, Save, Lock } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

const STATE_STYLE = {
  ok: { cls: "text-primary", label: "Sob controlo" },
  warning: { cls: "text-amber-500", label: "Alerte 400 €" },
  frozen: { cls: "text-orange-500", label: "Congelado a 440 €" },
  exceeded: { cls: "text-red-600", label: "Teto ultrapassado" },
};

const eur = (v) =>
  v === null || v === undefined ? "não mensurável" : `${Number(v).toFixed(2)} €`;

export default function BudgetCapPanel() {
  const [data, setData] = useState(null);
  const [env, setEnv] = useState({});
  const [busy, setBusy] = useState(false);
  const [sim, setSim] = useState({ amount_eur: 50, envelope: "ads" });
  const [verdict, setVerdict] = useState(null);

  const load = useCallback(() => {
    setBusy(true);
    api.get("/admin/expenses/cap")
      .then(({ data: d }) => {
        setData(d);
        setEnv(Object.fromEntries(Object.entries(d.envelopes).map(([k, v]) => [k, v.budget_eur])));
      })
      .finally(() => setBusy(false));
  }, []);
  useEffect(() => { load(); }, [load]);

  const saveEnv = async () => {
    try {
      await api.put("/admin/expenses/cap/envelopes", { envelopes: env });
      toast.success("Envelopes guardados");
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível guardar");
    }
  };

  const check = async () => {
    try {
      const { data: v } = await api.post("/admin/expenses/cap/check", {
        amount_eur: Number(sim.amount_eur), envelope: sim.envelope,
      });
      setVerdict(v);
    } catch { toast.error("Verificação impossível"); }
  };

  if (!data) return <p className="text-sm text-muted-foreground" data-testid="cap-loading">A carregar o teto…</p>;

  const st = STATE_STYLE[data.state] || STATE_STYLE.ok;
  const envTotal = Object.values(env).reduce((a, b) => a + Number(b || 0), 0);

  return (
    <div className="grid gap-6" data-testid="budget-cap-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-extrabold flex items-center gap-2">
            {data.new_engagements_allowed
              ? <ShieldCheck className="h-5 w-5 text-primary" />
              : <ShieldAlert className="h-5 w-5 text-orange-500" />}
            Plafond d'exploitation — {eur(data.cap_eur)} / mois
          </h2>
          <p className="text-xs text-muted-foreground">
            Mois {data.month} · alerta a {eur(data.warning_at)} · congelamento de novos compromissos a {eur(data.freeze_at)} · reserva preservada {eur(data.reserve_eur)}
          </p>
        </div>
        <Button size="sm" variant="outline" className="rounded-sm gap-1" onClick={load} disabled={busy}
                data-testid="cap-refresh">
          <RefreshCw className={`h-3.5 w-3.5 ${busy ? "animate-spin" : ""}`} /> Actualiser
        </Button>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[
          ["Gasto (confirmado)", data.confirmed_eur, "cap-confirmed"],
          ["Estimado (não faturado)", data.estimated_eur, "cap-estimated"],
          ["Compromissos reservados", data.held_eur, "cap-held"],
          ["Reste disponible", data.remaining_eur, "cap-remaining"],
        ].map(([label, value, tid]) => (
          <div key={tid} className="surface rounded-md p-4" data-testid={tid}>
            <p className="text-[11px] uppercase tracking-widest text-muted-foreground">{label}</p>
            <p className="font-display text-2xl font-extrabold mt-1 num">{eur(value)}</p>
          </div>
        ))}
      </div>

      <div className="surface rounded-md p-4" data-testid="cap-gauge">
        <div className="flex items-center justify-between text-sm">
          <span className={`font-semibold ${st.cls}`}>{st.label}</span>
          <span className="num text-muted-foreground">{eur(data.used_eur)} / {eur(data.cap_eur)} ({data.percent} %)</span>
        </div>
        <div className="mt-2 h-2.5 rounded-full bg-muted overflow-hidden">
          <div className="h-full rounded-full transition-all"
               style={{ width: `${Math.min(100, data.percent || 0)}%`,
                        background: data.state === "ok" ? "var(--primary, #15803D)"
                          : data.state === "warning" ? "#F59E0B" : "#DC2626" }} />
        </div>
        {!data.new_engagements_allowed && (
          <p className="mt-3 text-xs flex items-start gap-2 text-orange-600" data-testid="cap-blocking-reason">
            <Lock className="h-3.5 w-3.5 shrink-0 mt-0.5" />
            Novos compromissos bloqueados — {data.blocking_reason}
          </p>
        )}
        <p className="mt-2 text-[11px] text-muted-foreground">
          Fonte de custos: {data.cost_source.last_sync
            ? `última reconciliação há${data.cost_source.days_since} jour(s)`
            : "nunca reconciliada"}{data.cost_source.stale ? "— considerada desatualizada" : ""}.
          {data.incomplete && "Algumas linhas não têm montante utilizável: o total está por isso incompleto."}
        </p>
      </div>

      <section className="grid gap-3" data-testid="cap-envelopes">
        <p className="font-semibold text-sm">Enveloppes par poste</p>
        <div className="surface rounded-md overflow-x-auto">
          <table className="w-full text-sm min-w-[640px]">
            <thead>
              <tr className="text-left text-[11px] uppercase tracking-wider text-muted-foreground border-b border-border">
                <th className="px-4 py-2.5">Poste</th>
                <th className="px-4 py-2.5 text-right">Enveloppe</th>
                <th className="px-4 py-2.5 text-right">Utilizado</th>
                <th className="px-4 py-2.5 text-right">Reste</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data.envelopes).map(([key, v]) => (
                <tr key={key} className="border-b border-border/40" data-testid={`cap-env-${key}`}>
                  <td className="px-4 py-2">{v.label}</td>
                  <td className="px-4 py-2 text-right">
                    <Input type="number" min="0" step="5" value={env[key] ?? v.budget_eur}
                           onChange={(e) => setEnv((s) => ({ ...s, [key]: Number(e.target.value) }))}
                           className="h-8 w-24 rounded-sm text-right ml-auto"
                           data-testid={`cap-env-input-${key}`} />
                  </td>
                  <td className={`px-4 py-2 text-right num ${v.over ? "text-red-600 font-semibold" : ""}`}>
                    {eur(v.used_eur)}
                  </td>
                  <td className="px-4 py-2 text-right num">{eur(v.remaining_eur)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <span className={`text-xs ${envTotal > data.cap_eur ? "text-red-600 font-semibold" : "text-muted-foreground"}`}>
            Total dos envelopes: {envTotal.toFixed(2)} € / {eur(data.cap_eur)}
          </span>
          <Button size="sm" className="rounded-sm gap-1" onClick={saveEnv}
                  disabled={envTotal > data.cap_eur} data-testid="cap-save-envelopes">
            <Save className="h-3.5 w-3.5" /> Guardar os envelopes
          </Button>
        </div>
      </section>

      <section className="surface rounded-md p-4 grid gap-3" data-testid="cap-simulator">
        <p className="font-semibold text-sm">Um compromisso passaria?</p>
        <div className="flex flex-wrap items-end gap-3">
          <label className="text-xs text-muted-foreground grid gap-1">Montante (€)
            <Input type="number" min="0" step="10" value={sim.amount_eur}
                   onChange={(e) => setSim((s) => ({ ...s, amount_eur: e.target.value }))}
                   className="h-9 w-28 rounded-sm" data-testid="cap-sim-amount" />
          </label>
          <label className="text-xs text-muted-foreground grid gap-1">Poste
            <select value={sim.envelope} onChange={(e) => setSim((s) => ({ ...s, envelope: e.target.value }))}
                    className="h-9 rounded-sm border border-border bg-background px-2 text-sm"
                    data-testid="cap-sim-envelope">
              {Object.entries(data.envelopes).map(([k, v]) => <option key={k} value={k}>{v.label}</option>)}
            </select>
          </label>
          <Button size="sm" variant="outline" className="rounded-sm" onClick={check} data-testid="cap-sim-check">
            Verificar
          </Button>
        </div>
        {verdict && (
          <p className={`text-sm ${verdict.allowed ? "text-primary" : "text-red-600"}`} data-testid="cap-sim-verdict">
            {verdict.allowed
              ? `Autorizado — total projetado${eur(verdict.projected_used_eur)} sur ${eur(verdict.cap_eur)}`
              : `Recusado —${verdict.reason}`}
          </p>
        )}
      </section>

      {data.holds?.length > 0 && (
        <section className="grid gap-2" data-testid="cap-holds">
          <p className="font-semibold text-sm">Compromissos reservados a aguardar fatura</p>
          {data.holds.map((h) => (
            <div key={h.hold_id} className="surface rounded-md p-3 flex items-center justify-between gap-3 text-sm">
              <span>{h.label} <span className="text-muted-foreground">· {h.envelope}</span></span>
              <span className="num">{eur(h.amount_eur)}</span>
            </div>
          ))}
        </section>
      )}
    </div>
  );
}
