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
      toast.success(action === "reactivate" ? "Chave OpenAI reativada — teste de ligação bem-sucedido" : "Mudança para a chave Emergent efetuada");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Operação impossível");
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
      toast.success("Orçamento IA guardado");
    } catch {
      toast.error("Impossível guardar orçamento");
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
      toast.success("Modelo IA atualizado");
    } catch {
      toast.error("Falha na atualização do modelo");
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
      toast.success(backend === "native" ? "O Assistente Construção passa para o SDK Google nativo" : "O Assistente Construção passa para a chave Emergent");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Mudança impossível");
    } finally {
      setGeminiBusy("");
    }
  };

  const testGeminiKey = async () => {
    setGeminiBusy("test");
    try {
      const { data: res } = await api.post("/admin/ai-gemini-backend/test");
      if (res.ok) toast.success("Chave Google válida — ligação bem-sucedida");
      else toast.error(`Chave Google: ${res.status}`);
    } catch {
      toast.error("Teste da chave impossível");
    } finally {
      setGeminiBusy("");
    }
  };

  if (!data) return null;

  const k = data.openai_key;

  return (
    <div className="max-w-3xl space-y-8" data-testid="admin-ai-section">
      <SectionTitle over="Inteligência artificial" title="Seletor de modelo IA">
        Escolha o modelo utilizado para a geração de texto (estimativa Smart Project, coach IA, análises). A análise de imagens utiliza sempre um modelo visão dedicado.
      </SectionTitle>

      {k?.configured && (
        <div
          data-testid="admin-openai-key-status"
          className={`rounded-sm border p-4 flex flex-col sm:flex-row sm:items-center gap-3 ${k.active ? "border-border surface" : "border-amber-500/50 bg-amber-500/10"}`}
        >
          <div className="flex-1 text-sm">
            <p className="font-semibold flex items-center gap-2">
              <KeyRound className="h-4 w-4" />
              Chave OpenAI da empresa:{" "}
              <span data-testid="admin-openai-key-state" className={k.active ? "text-primary" : "text-amber-700"}>
                {k.active ? "active" : "desativada — recurso à chave Emergent"}
              </span>
            </p>
            {!k.active && (
              <p className="text-xs text-amber-800 mt-1" data-testid="admin-openai-key-reason">
                Desde {k.since ? new Date(k.since).toLocaleString("fr-FR") : "—"} · motif : {k.reason || "—"}. Recarregue o crédito em platform.openai.com e depois reative; é efetuado um teste de ligação.
              </p>
            )}
            {k.active && (
              <p className="text-xs text-muted-foreground mt-1">
                Em caso de crédito esgotado, a mudança para a chave universal Emergent é automática e é avisado por e-mail.
              </p>
            )}
          </div>
          {k.active ? (
            <Button variant="outline" size="sm" onClick={() => toggleKey("disable")} disabled={!!keyBusy} data-testid="admin-openai-key-disable-btn">
              {keyBusy === "disable" ? <Loader2 className="h-4 w-4 animate-spin" /> : "Mudar para Emergent"}
            </Button>
          ) : (
            <Button size="sm" onClick={() => toggleKey("reactivate")} disabled={!!keyBusy} data-testid="admin-openai-key-reactivate-btn">
              {keyBusy === "reactivate" ? <Loader2 className="h-4 w-4 animate-spin" /> : <><RefreshCw className="h-4 w-4 mr-1" /> Reativar a chave OpenAI</>}
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
                    <Check className="h-3.5 w-3.5" /> Ativo
                  </span>
                ) : null}
              </div>
              <p className="font-display font-extrabold tracking-tight mt-3">{o.label}</p>
              <p className="text-xs text-muted-foreground mt-1">{o.desc}</p>
              <div className="mt-4 space-y-1.5">
                <Rating icon={Sparkles} label="Qualidade" value={o.quality || 1} />
                <Rating icon={Gauge} label="Velocidade" value={o.speed || 1} />
                <Rating icon={Coins} label="Custo relativo" value={o.cost || 1} />
              </div>
              <p className="text-[11px] text-muted-foreground/70 mt-3 font-mono">{o.model}</p>
            </button>
          );
        })}
      </div>

      <p className="text-xs text-muted-foreground" data-testid="admin-ai-current">
        Modelo ativo: <strong>{data.options.find((o) => o.tier === data.current)?.label}</strong>. A alteração é imediata para todos os próximos pedidos IA.
      </p>

      {/* --- Backend Gemini : Emergent vs Google natif --- */}
      {gemini && (
        <div className="space-y-4" data-testid="admin-gemini-backend">
          <SectionTitle over="Visão e plantas" title="Motor IA Assistente Construção (plantas, medições)">
            Escolha como são executadas as chamadas do motor IA Assistente Construção: através da chave universal Emergent, ou diretamente na Google com a sua própria chave (faturação Google, alias gemini pro/flash latest).
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
                        <Check className="h-3.5 w-3.5" /> Ativo
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
                      Chave Google ausente — adicione GOOGLE_GEMINI_API_KEY ao backend.
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
              Testar a chave Google
            </Button>
            <span className="text-xs text-muted-foreground" data-testid="admin-gemini-key-state">
              Chave Google: {gemini.key_present ? "presente" : "absente"}
            </span>
          </div>
        </div>
      )}

      {/* --- Suivi des coûts / usage IA --- */}
      <div className="space-y-4" data-testid="admin-ai-usage">
        <SectionTitle over="Consumo" title="Acompanhamento das chamadas IA">
          Número de chamadas ao modelo por funcionalidade e por modelo. Total:{" "}
          <strong data-testid="admin-ai-usage-total">{num(usage?.total_calls || 0)}</strong> appels.
        </SectionTitle>

        {(!usage || usage.total_calls === 0) ? (
          <p className="text-sm text-muted-foreground" data-testid="admin-ai-usage-empty">
            Nenhuma chamada IA registada por agora. Os contadores preencherão na próxima estimativa, análise ou conversa com o coach.
          </p>
        ) : (
          <div className="grid md:grid-cols-2 gap-6">
            <div className="surface p-4 rounded-sm" data-testid="admin-ai-by-feature">
              <p className="text-[11px] font-bold uppercase tracking-widest text-primary mb-3">
                Por funcionalidade
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
                Por modelo
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
        <SectionTitle over="Tendência" title="Consumo IA — últimos 30 dias" />
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
            Ainda sem chamadas IA nos últimos 30 dias.
          </p>
        )}
      </div>

      {/* --- Alerte budget IA --- */}
      <div className="space-y-4" data-testid="admin-ai-budget">
        <SectionTitle over="Controlo de custos" title="Alerta orçamento IA">
          Receba um email quando o número de chamadas IA do mês ultrapassar um limite.
          {budget && (
            <> Este mês: <strong data-testid="admin-ai-budget-month">{num(budget.month_calls)}</strong> appels
            {budget.threshold ? <> / {num(budget.threshold)} (limiar)</> : null}.</>
          )}
        </SectionTitle>
        <div className="surface p-4 rounded-sm grid sm:grid-cols-3 gap-3 items-end">
          <div>
            <Label>Limite de chamadas / mês</Label>
            <Input type="number" min="0" value={threshold} onChange={(e) => setThreshold(e.target.value)}
                   placeholder="Ex : 500" className="rounded-sm num mt-1" data-testid="admin-ai-budget-threshold" />
          </div>
          <div>
            <Label>Email de alerta (opcional)</Label>
            <Input type="email" value={alertEmail} onChange={(e) => setAlertEmail(e.target.value)}
                   placeholder="admin@construpilot.fr" className="rounded-sm mt-1" data-testid="admin-ai-budget-email" />
          </div>
          <Button onClick={saveBudget} disabled={savingBudget} className="rounded-sm gap-2" data-testid="admin-ai-budget-save">
            {savingBudget ? <Loader2 className="h-4 w-4 animate-spin" /> : <Bell className="h-4 w-4" />} Guardar
          </Button>
        </div>
        {budget?.alert_sent_this_month && (
          <p className="text-xs text-amber-600 dark:text-amber-400" data-testid="admin-ai-budget-alerted">
            ⚠️ Um alerta já foi enviado este mês (limite ultrapassado).
          </p>
        )}
      </div>
    </div>
  );
}
