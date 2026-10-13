import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Cpu, Check, Loader2, Gauge, Coins, Sparkles, Bell, KeyRound, RefreshCw } from "lucide-react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { api, num } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionTitle } from "@/components/Bits";

function Rating({ icon: Icon, label, value }) {
  return (
    <div className="flex items-center gap-1.5" title={`${label}: ${value}/3`}>
      <Icon className="h-3.5 w-3.5 text-muted-foreground" />
      <div className="flex gap-0.5">
        {[1, 2, 3].map((i) => (
          <span
            key={i}
            className={`h-1.5 w-3 rounded-sm ${i <= value ? "bg-primary" : "bg-border"}`}
          />
        ))}
      </div>
    </div>
  );
}

export default function AiModelTab() {
  const [data, setData] = useState(null);
  const [usage, setUsage] = useState(null);
  const [daily, setDaily] = useState(null);
  const [budget, setBudget] = useState(null);
  const [threshold, setThreshold] = useState("");
  const [alertEmail, setAlertEmail] = useState("");
  const [savingBudget, setSavingBudget] = useState(false);
  const [saving, setSaving] = useState("");
  const [keyBusy, setKeyBusy] = useState("");
  const [gemini, setGemini] = useState(null);
  const [geminiBusy, setGeminiBusy] = useState("");

  const toggleKey = async (action) => {
    setKeyBusy(action);
    try {
      const { data: st } = await api.post(`/admin/ai-openai-key/${action}`);
      setData((d) => ({ ...d, openai_key: st }));
      toast.success(action === "reactivate" ? "Clé OpenAI réactivée — test de connexion réussi" : "Bascule sur la clé Emergent effectuée");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Opération impossible");
    } finally {
      setKeyBusy("");
    }
  };

  const load = () => {
    api.get("/admin/ai-model").then(({ data }) => setData(data));
    api.get("/admin/ai-gemini-backend").then(({ data }) => setGemini(data)).catch(() => {});
    api.get("/admin/ai-usage").then(({ data }) => setUsage(data)).catch(() => {});
    api.get("/admin/ai-usage-daily?days=30").then(({ data }) => setDaily(data)).catch(() => {});
    api.get("/admin/ai-budget").then(({ data }) => {
      setBudget(data);
      setThreshold(data.threshold ? String(data.threshold) : "");
      setAlertEmail(data.alert_email || "");
    }).catch(() => {});
  };

  useEffect(() => {
    load();
  }, []);

  const saveBudget = async () => {
    setSavingBudget(true);
    try {
      const { data: res } = await api.put("/admin/ai-budget", {
        threshold: Number(threshold) || 0,
        alert_email: alertEmail.trim(),
      });
      setBudget(res);
      toast.success("Budget IA enregistré");
    } catch {
      toast.error("Enregistrement du budget impossible");
    } finally {
      setSavingBudget(false);
    }
  };

  const choose = async (tier) => {
    if (!data || tier === data.current || saving) return;
    setSaving(tier);
    try {
      const { data: res } = await api.put("/admin/ai-model", { tier });
      setData((d) => ({ ...d, current: res.current }));
      toast.success("Modèle IA mis à jour");
    } catch {
      toast.error("Échec de la mise à jour du modèle");
    } finally {
      setSaving("");
    }
  };

  const chooseGemini = async (backend) => {
    if (!gemini || backend === gemini.current || geminiBusy) return;
    setGeminiBusy(backend);
    try {
      const { data: res } = await api.put("/admin/ai-gemini-backend", { backend });
      setGemini((g) => ({ ...g, current: res.current }));
      toast.success(backend === "native" ? "L'Assistant BTP bascule sur le SDK Google natif" : "L'Assistant BTP bascule sur la clé Emergent");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Bascule impossible");
    } finally {
      setGeminiBusy("");
    }
  };

  const testGeminiKey = async () => {
    setGeminiBusy("test");
    try {
      const { data: res } = await api.post("/admin/ai-gemini-backend/test");
      if (res.ok) toast.success("Clé Google valide — connexion réussie");
      else toast.error(`Clé Google : ${res.status}`);
    } catch {
      toast.error("Test de la clé impossible");
    } finally {
      setGeminiBusy("");
    }
  };

  if (!data) return null;

  const k = data.openai_key;

  return (
    <div className="max-w-3xl space-y-8" data-testid="admin-ai-section">
      <SectionTitle over="Intelligence artificielle" title="Sélecteur de modèle IA">
        Choisissez le modèle utilisé pour la génération de texte (estimation Smart Project,
        coach IA, analyses). L'analyse d'images utilise toujours un modèle vision dédié.
      </SectionTitle>

      {k?.configured && (
        <div
          data-testid="admin-openai-key-status"
          className={`rounded-sm border p-4 flex flex-col sm:flex-row sm:items-center gap-3 ${k.active ? "border-border surface" : "border-amber-500/50 bg-amber-500/10"}`}
        >
          <div className="flex-1 text-sm">
            <p className="font-semibold flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              Clé OpenAI de l'entreprise :{" "}
              <span data-testid="admin-openai-key-state" className={k.active ? "text-primary" : "text-amber-700"}>
                {k.active ? "active" : "désactivée — repli sur la clé Emergent"}
              </span>
            </p>
            {!k.active && (
              <p className="text-xs text-amber-800 mt-1" data-testid="admin-openai-key-reason">
                Depuis le {k.since ? new Date(k.since).toLocaleString("fr-FR") : "—"} · motif : {k.reason || "—"}.
                Rechargez le crédit sur platform.openai.com puis réactivez ; un test de connexion est effectué.
              </p>
            )}
            {k.active && (
              <p className="text-xs text-muted-foreground mt-1">
                En cas de crédit épuisé, la bascule sur la clé universelle Emergent est automatique et vous êtes prévenu par e-mail.
              </p>
            )}
          </div>
          {k.active ? (
            <Button variant="outline" size="sm" onClick={() => toggleKey("disable")} disabled={!!keyBusy} data-testid="admin-openai-key-disable-btn">
              {keyBusy === "disable" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Basculer sur Emergent"}
            </Button>
          ) : (
            <Button size="sm" onClick={() => toggleKey("reactivate")} disabled={!!keyBusy} data-testid="admin-openai-key-reactivate-btn">
              {keyBusy === "reactivate" ? <Loader2 className="h-4 w-4 animate-spin" /> : <><RefreshCw className="h-4 w-4 mr-1" /> Réactiver la clé OpenAI</>}
            </Button>
          )}
        </div>
      )}

      <div className="grid sm:grid-cols-3 gap-4" data-testid="admin-ai-options">
        {data.options.map((o) => {
          const active = o.tier === data.current;
          return (
            <button
              key={o.tier}
              type="button"
              onClick={() => choose(o.tier)}
              data-testid={`admin-ai-option-${o.tier}`}
              className={`surface text-left p-5 rounded-sm border transition-colors relative
                ${active ? "border-primary ring-1 ring-primary/40" : "border-border hover:border-primary/40"}`}
            >
              <div className="flex items-center justify-between">
                <Cpu className="h-5 w-5 text-primary" />
                {saving === o.tier ? (
                  <Loader2 className="h-4 w-4 animate-spin text-primary" />
                ) : active ? (
                  <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-widest text-primary">
                    <Check className="h-3.5 w-3.5" /> Actif
                  </span>
                ) : null}
              </div>
              <p className="font-display font-extrabold tracking-tight mt-3">{o.label}</p>
              <p className="text-xs text-muted-foreground mt-1">{o.desc}</p>
              <div className="mt-4 space-y-1.5">
                <Rating icon={Sparkles} label="Qualité" value={o.quality || 1} />
                <Rating icon={Gauge} label="Vitesse" value={o.speed || 1} />
                <Rating icon={Coins} label="Coût relatif" value={o.cost || 1} />
              </div>
              <p className="text-[11px] text-muted-foreground/70 mt-3 font-mono">{o.model}</p>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground" data-testid="admin-ai-current">
        Modèle actif : <strong>{data.options.find((o) => o.tier === data.current)?.label}</strong>.
        La modification est immédiate pour toutes les prochaines requêtes IA.
      </p>

      {/* --- Backend Gemini : Emergent vs Google natif --- */}
      {gemini && (
        <div className="space-y-4" data-testid="admin-gemini-backend">
          <SectionTitle over="Vision & plans" title="Moteur IA Assistant BTP (plans, métré)">
            Choisissez comment sont exécutés les appels du moteur IA Assistant BTP : via la clé universelle Emergent,
            ou directement sur Google avec votre propre clé (facturation Google, alias gemini pro/flash latest).
          </SectionTitle>
          <div className="grid sm:grid-cols-2 gap-4" data-testid="admin-gemini-options">
            {gemini.options.map((o) => {
              const active = o.backend === gemini.current;
              const disabled = o.backend === "native" && !gemini.key_present;
              return (
                <button
                  key={o.backend}
                  type="button"
                  disabled={disabled}
                  onClick={() => chooseGemini(o.backend)}
                  data-testid={`admin-gemini-option-${o.backend}`}
                  className={`surface text-left p-5 rounded-sm border transition-colors relative disabled:opacity-50 disabled:cursor-not-allowed
                    ${active ? "border-primary ring-1 ring-primary/40" : "border-border hover:border-primary/40"}`}
                >
                  <div className="flex items-center justify-between">
                    <Cpu className="h-5 w-5 text-primary" />
                    {geminiBusy === o.backend ? (
                      <Loader2 className="h-4 w-4 animate-spin text-primary" />
                    ) : active ? (
                      <span className="inline-flex items-center gap-1 text-[11px] font-bold uppercase tracking-widest text-primary">
                        <Check className="h-3.5 w-3.5" /> Actif
                      </span>
                    ) : null}
                  </div>
                  <p className="font-display font-extrabold tracking-tight mt-3">{o.label}</p>
                  <p className="text-xs text-muted-foreground mt-1">{o.desc}</p>
                  {o.backend === "native" && (
                    <p className="text-[11px] mt-3 font-mono text-muted-foreground/70">
                      {gemini.models.pro} · {gemini.models.flash}
                    </p>
                  )}
                  {disabled && (
                    <p className="text-[11px] mt-2 text-amber-700" data-testid="admin-gemini-key-missing">
                      Clé Google absente — ajoutez GOOGLE_GEMINI_API_KEY au backend.
                    </p>
                  )}
                </button>
              );
            })}
          </div>
          <div className="flex items-center gap-3">
            <Button variant="outline" size="sm" onClick={testGeminiKey} disabled={!gemini.key_present || !!geminiBusy}
                    className="rounded-sm gap-2" data-testid="admin-gemini-test-btn">
              {geminiBusy === "test" ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
              Tester la clé Google
            </Button>
            <span className="text-xs text-muted-foreground" data-testid="admin-gemini-key-state">
              Clé Google : {gemini.key_present ? "présente" : "absente"}
            </span>
          </div>
        </div>
      )}

      {/* --- Suivi des coûts / usage IA --- */}
      <div className="space-y-4" data-testid="admin-ai-usage">
        <SectionTitle over="Consommation" title="Suivi des appels IA">
          Nombre d'appels au modèle par fonctionnalité et par modèle. Total :{" "}
          <strong data-testid="admin-ai-usage-total">{num(usage?.total_calls || 0)}</strong> appels.
        </SectionTitle>

        {(!usage || usage.total_calls === 0) ? (
          <p className="text-sm text-muted-foreground" data-testid="admin-ai-usage-empty">
            Aucun appel IA enregistré pour l'instant. Les compteurs se rempliront dès la prochaine
            estimation, analyse ou conversation avec le coach.
          </p>
        ) : (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="surface p-4 rounded-sm" data-testid="admin-ai-by-feature">
              <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3">
                Par fonctionnalité
              </p>
              <div className="space-y-2">
                {usage.by_feature.map((f) => (
                  <div key={f.feature} className="flex items-center justify-between text-sm">
                    <span>{f.feature_label}</span>
                    <span className="num font-bold">{num(f.calls)}</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="surface p-4 rounded-sm" data-testid="admin-ai-by-model">
              <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3">
                Par modèle
              </p>
              <div className="space-y-2">
                {usage.by_model.map((m) => (
                  <div key={m.model} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-xs">{m.model}</span>
                    <span className="num font-bold">{num(m.calls)}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* --- Graphique de consommation (30 j) --- */}
      <div className="space-y-4" data-testid="admin-ai-daily">
        <SectionTitle over="Tendance" title="Consommation IA — 30 derniers jours" />
        {daily && daily.total > 0 ? (
          <div className="surface p-4 rounded-sm" style={{ height: 260 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={daily.series} margin={{ top: 8, right: 8, left: -18, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" vertical={false} />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(d) => d.slice(5)}
                       interval="preserveStartEnd" minTickGap={20} />
                <YAxis tick={{ fontSize: 10 }} allowDecimals={false} width={40} />
                <Tooltip
                  contentStyle={{ background: "var(--card)", border: "1px solid var(--border)", borderRadius: 4, fontSize: 12 }}
                  labelStyle={{ color: "var(--foreground)" }}
                  formatter={(v) => [`${v} appels`, "IA"]} />
                <Bar dataKey="calls" fill="var(--primary)" radius={[3, 3, 0, 0]} maxBarSize={28} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="text-sm text-muted-foreground" data-testid="admin-ai-daily-empty">
            Pas encore d'appels IA sur les 30 derniers jours.
          </p>
        )}
      </div>

      {/* --- Alerte budget IA --- */}
      <div className="space-y-4" data-testid="admin-ai-budget">
        <SectionTitle over="Maîtrise des coûts" title="Alerte budget IA">
          Recevez un email lorsque le nombre d'appels IA du mois dépasse un seuil.
          {budget && (
            <> Ce mois-ci : <strong data-testid="admin-ai-budget-month">{num(budget.month_calls)}</strong> appels
            {budget.threshold ? <> / {num(budget.threshold)} (seuil)</> : null}.</>
          )}
        </SectionTitle>
        <div className="surface p-4 rounded-sm grid sm:grid-cols-3 gap-3 items-end">
          <div>
            <Label>Seuil d'appels / mois</Label>
            <Input type="number" min="0" value={threshold} onChange={(e) => setThreshold(e.target.value)}
                   placeholder="Ex : 500" className="rounded-sm num mt-1" data-testid="admin-ai-budget-threshold" />
          </div>
          <div>
            <Label>Email d'alerte (optionnel)</Label>
            <Input type="email" value={alertEmail} onChange={(e) => setAlertEmail(e.target.value)}
                   placeholder="admin@construpilot.fr" className="rounded-sm mt-1" data-testid="admin-ai-budget-email" />
          </div>
          <Button onClick={saveBudget} disabled={savingBudget} className="rounded-sm gap-2" data-testid="admin-ai-budget-save">
            {savingBudget ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bell className="h-4 w-4" />} Enregistrer
          </Button>
        </div>
        {budget?.alert_sent_this_month && (
          <p className="text-xs text-amber-600 dark:text-amber-400" data-testid="admin-ai-budget-alerted">
            ⚠️ Une alerte a déjà été envoyée ce mois-ci (seuil dépassé).
          </p>
        )}
      </div>
    </div>
  );
}
