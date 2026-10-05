import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  BarChart, Bar, PieChart, Pie, Cell, XAxis, YAxis, Tooltip,
  Legend, ResponsiveContainer,
} from "recharts";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Loader2, Wrench, AlertTriangle, FileText, BookOpen, Rocket, Globe, Link2, Zap } from "lucide-react";

const WEB_MODES = [
  { value: "auto", label: "Auto", title: "Decido automaticamente" },
  { value: "always", label: "Sempre", title: "Pesquisa sempre na internet" },
  { value: "never", label: "Nunca", title: "Não pesquisa na internet" },
];

const URGENCY_LABEL = {
  informative: { label: "Informativo", color: "bg-slate-500" },
  planned: { label: "Planeável", color: "bg-emerald-500" },
  urgent: { label: "Urgente", color: "bg-amber-500" },
  immediate: { label: "Imediato", color: "bg-rose-600" },
};
const RISK_LABEL = {
  low: { label: "Baixo", color: "bg-emerald-500" },
  medium: { label: "Médio", color: "bg-amber-500" },
  high: { label: "Alto", color: "bg-rose-500" },
  critical: { label: "Crítico", color: "bg-rose-700" },
};
const CONFIDENCE_LABEL = { low: "Baixa", medium: "Média", high: "Alta" };
const CHART_COLORS = ["#10b981", "#3b82f6", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];

const toRechartsBar = (chart) => {
  const data = (chart.x_labels || []).map((lbl, i) => {
    const row = { name: lbl };
    (chart.series || []).forEach((s) => { row[s.name] = Number(s.data?.[i] ?? 0); });
    return row;
  });
  return { data, series: chart.series.map((s) => s.name) };
};

const toRechartsPie = (chart) => {
  const serie = (chart.series || [])[0];
  return (chart.x_labels || []).map((lbl, i) => ({
    name: lbl, value: Number(serie?.data?.[i] ?? 0),
  }));
};

export default function BtpSolver() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const isFree = user?.account_type === "particulier" && user?.role !== "admin";
  const [form, setForm] = useState({
    description: "",
    tipo_edificio: "",
    region: "",
    idade_anos: "",
    orcamento_max_eur: "",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [webMode, setWebMode] = useState("auto");
  const [rateInfo, setRateInfo] = useState(null);

  const loadHistory = async () => {
    try {
      const r = await api.get("/btp-solver/history?limit=10");
      setHistory(r.data?.items || []);
    } catch (e) {
      // silencioso: histórico é bónus
    }
  };

  useEffect(() => { if (user) loadHistory(); }, [user]);

  const onSubmit = async (e) => {
    e.preventDefault();
    if ((form.description || "").trim().length < 10) {
      toast.error("Descreva o problema com pelo menos 10 caracteres.");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const payload = {
        description: form.description.trim(),
        tipo_edificio: form.tipo_edificio || undefined,
        region: form.region || undefined,
        idade_anos: form.idade_anos ? Number(form.idade_anos) : undefined,
        orcamento_max_eur: form.orcamento_max_eur ? Number(form.orcamento_max_eur) : undefined,
      };
      if (webMode === "always") payload.use_web_search = true;
      else if (webMode === "never") payload.use_web_search = false;
      const r = await api.post("/btp-solver/solve", payload);
      setResult(r.data);
      if (r.data?.rate_limit) setRateInfo(r.data.rate_limit);
      if (r.data?.web_search_fallback) {
        toast.message("Limite de pesquisas web atingido — resposta sem fontes atuais.", {
          duration: 5000,
        });
      }
      toast.success("Análise concluída.");
      loadHistory();
    } catch (err) {
      const status = err?.response?.status;
      const body = err?.response?.data;
      if (status === 429) {
        const msg = body?.message || "Atingiu o limite de pedidos.";
        const upgradeUrl = body?.upgrade_url || "/pricing";
        const isFreeUser = body?.current_plan === "free";
        toast.error(msg, {
          duration: 7000,
          action: isFreeUser ? { label: "Upgrade", onClick: () => navigate(upgradeUrl) } : undefined,
        });
      } else {
        const msg = body?.detail || err?.message || "Erro desconhecido";
        toast.error(`Análise falhou: ${msg}`);
      }
    } finally {
      setLoading(false);
    }
  };

  const loadFromHistory = async (problemId) => {
    try {
      const r = await api.get(`/btp-solver/${problemId}`);
      setResult(r.data);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch {
      toast.error("Não foi possível carregar a análise.");
    }
  };

  return (
    <div className="min-h-screen px-4 py-8 lg:px-8" data-testid="btp-solver-page">
      <div className="mx-auto max-w-7xl">
        <header className="mb-6">
          <div className="flex items-center gap-4">
            <img
              src="/assistente-obras-logo.png"
              alt="Assistente de Obras · ConstruPilot"
              className="h-24 w-24 sm:h-28 sm:w-28 shrink-0 object-contain"
              data-testid="btp-solver-logo"
              onError={(e) => { e.currentTarget.style.display = 'none'; }}
            />
            <div>
              <h1
                className="text-2xl sm:text-3xl font-bold tracking-tight sr-only"
                data-testid="btp-solver-title"
              >
                Assistente de Obras
              </h1>
              <p className="text-sm text-slate-600 dark:text-slate-400 max-w-2xl">
                Descreva uma patologia ou dúvida técnica de obra — o Assistente de Obras
                devolve um diagnóstico detalhado com causas prováveis, soluções orçamentadas
                e normativa portuguesa aplicável (RGEU, REH, RSCIE, Eurocódigos).
              </p>
            </div>
          </div>
        </header>

        {isFree && (
          <div
            data-testid="btp-solver-free-banner"
            className="mb-6 flex items-center justify-between gap-3 rounded-sm border border-primary/30 bg-primary/5 px-4 py-3 text-sm"
          >
            <div className="flex items-center gap-2.5">
              <Rocket className="h-4 w-4 text-primary shrink-0" />
              <span className="text-muted-foreground">
                Está no plano <strong className="text-foreground">Grátis</strong> · 10 análises/h.
                Faça upgrade para <strong>Pro (99 €/mês)</strong> e tenha 40 análises/h.
              </span>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => navigate("/pricing")}
              data-testid="btp-solver-upgrade-btn"
              className="rounded-sm shrink-0 border-primary/50 text-primary hover:bg-primary hover:text-primary-foreground"
            >
              Ver planos
            </Button>
          </div>
        )}

        <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
          {/* Coluna principal */}
          <div className="space-y-6">
            {/* Formulário */}
            <Card data-testid="btp-solver-form-card">
              <CardHeader>
                <CardTitle>Descrever o problema</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={onSubmit} className="space-y-4">
                  <div>
                    <Label htmlFor="description">Descrição *</Label>
                    <Textarea id="description" rows={5} placeholder="Ex.: Fissura diagonal numa parede exterior de alvenaria dupla, moradia dos anos 80, aparece há 2 meses, mais visível depois de chover."
                      value={form.description}
                      onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
                      maxLength={4000}
                      data-testid="btp-solver-description-input"
                    />
                    <p className="mt-1 text-xs text-slate-500">{form.description.length}/4000</p>
                  </div>
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <Label htmlFor="tipo_edificio">Tipo de edifício</Label>
                      <Input id="tipo_edificio" placeholder="Moradia · Prédio · Comercial"
                        value={form.tipo_edificio}
                        onChange={(e) => setForm((f) => ({ ...f, tipo_edificio: e.target.value }))}
                        data-testid="btp-solver-tipo-input"
                      />
                    </div>
                    <div>
                      <Label htmlFor="region">Região</Label>
                      <Input id="region" placeholder="Lisboa · Porto · Braga …"
                        value={form.region}
                        onChange={(e) => setForm((f) => ({ ...f, region: e.target.value }))}
                        data-testid="btp-solver-region-input"
                      />
                    </div>
                    <div>
                      <Label htmlFor="idade">Idade do edificado (anos)</Label>
                      <Input id="idade" type="number" min="0" max="500"
                        value={form.idade_anos}
                        onChange={(e) => setForm((f) => ({ ...f, idade_anos: e.target.value }))}
                        data-testid="btp-solver-idade-input"
                      />
                    </div>
                    <div>
                      <Label htmlFor="orcamento">Orçamento máx. (€)</Label>
                      <Input id="orcamento" type="number" min="0"
                        value={form.orcamento_max_eur}
                        onChange={(e) => setForm((f) => ({ ...f, orcamento_max_eur: e.target.value }))}
                        data-testid="btp-solver-orcamento-input"
                      />
                    </div>
                  </div>
                  <Button type="submit" disabled={loading} className="w-full sm:w-auto"
                    data-testid="btp-solver-submit-btn">
                    {loading
                      ? (<><Loader2 className="mr-2 h-4 w-4 animate-spin" />A analisar — pode demorar até 40 s …</>)
                      : (<><Wrench className="mr-2 h-4 w-4" />Diagnosticar</>)}
                  </Button>

                  {/* Toggle web search + indicador de uso */}
                  <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-border/60"
                       data-testid="btp-controls-bar">
                    <div className="flex items-center gap-2" data-testid="btp-web-search-toggle">
                      <Globe className="h-4 w-4 text-primary shrink-0" aria-hidden="true" />
                      <span className="text-xs text-muted-foreground">Pesquisar na Internet:</span>
                      <div className="flex items-center rounded-sm border border-border overflow-hidden">
                        {WEB_MODES.map((m) => (
                          <button
                            key={m.value}
                            type="button"
                            title={m.title}
                            data-testid={`btp-web-mode-${m.value}`}
                            onClick={() => setWebMode(m.value)}
                            className={`px-3 py-1 text-xs transition-colors ${
                              webMode === m.value
                                ? "bg-primary text-primary-foreground"
                                : "bg-background text-muted-foreground hover:bg-secondary"
                            }`}
                          >
                            {m.label}
                          </button>
                        ))}
                      </div>
                    </div>
                    {rateInfo && (
                      <div className="flex items-center gap-2 text-xs text-muted-foreground"
                           data-testid="btp-rate-indicator">
                        <Zap className="h-3.5 w-3.5 text-primary" aria-hidden="true" />
                        <span>
                          <span className="font-semibold text-foreground">{rateInfo.web_remaining}</span>
                          /{rateInfo.web_limit} pesquisas web · plano{" "}
                          <strong className="capitalize">{rateInfo.plan}</strong>
                        </span>
                        {rateInfo.plan === "free" && (
                          <button
                            type="button"
                            onClick={() => navigate("/pricing")}
                            data-testid="btp-rate-upgrade-link"
                            className="text-primary hover:underline"
                          >
                            → Pro 99 €/mês
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                </form>
              </CardContent>
            </Card>

            {/* Resultado */}
            {result && (
              <div className="space-y-4" data-testid="btp-solver-result">
                {/* Cabeçalho resumo + urgência */}
                <Card>
                  <CardHeader>
                    <div className="flex flex-wrap items-center gap-3">
                      <CardTitle>Diagnóstico</CardTitle>
                      <Badge className={`${(URGENCY_LABEL[result.urgency] || URGENCY_LABEL.planned).color} text-white`}
                        data-testid="btp-solver-urgency-badge">
                        Urgência: {(URGENCY_LABEL[result.urgency] || URGENCY_LABEL.planned).label}
                      </Badge>
                      <Badge variant="outline">{result.domain}</Badge>
                      {result.model_used && <Badge variant="secondary" className="text-xs">{result.model_used}</Badge>}
                      {result.web_enriched && (
                        <Badge
                          data-testid="btp-web-badge"
                          className="text-xs inline-flex items-center gap-1 bg-primary/10 border border-primary/30 text-primary hover:bg-primary/15"
                        >
                          <Globe className="h-3 w-3" aria-hidden="true" />
                          {(result.references || []).filter(r => r.kind === "web").length || result.references?.length || 0} fontes web
                        </Badge>
                      )}
                      {result.web_search_fallback && (
                        <Badge variant="outline" className="text-xs text-amber-600 border-amber-500/40">
                          <AlertTriangle className="h-3 w-3 mr-1" />
                          Sem fontes atuais
                        </Badge>
                      )}
                    </div>
                  </CardHeader>
                  <CardContent>
                    <p className="whitespace-pre-wrap text-sm leading-relaxed">{result.summary}</p>
                  </CardContent>
                </Card>

                {/* Causas */}
                {result.causes?.length > 0 && (
                  <Card data-testid="btp-solver-causes-card">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <AlertTriangle className="h-5 w-5 text-amber-500" />
                        Causas prováveis ({result.causes.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ul className="space-y-3">
                        {result.causes.map((c, i) => (
                          <li key={i} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                            <div className="flex items-start justify-between gap-3">
                              <div className="font-medium">{c.label}</div>
                              <Badge variant="outline">Confiança: {CONFIDENCE_LABEL[c.confidence] || c.confidence}</Badge>
                            </div>
                            <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{c.explanation}</p>
                          </li>
                        ))}
                      </ul>
                    </CardContent>
                  </Card>
                )}

                {/* Soluções */}
                {result.solutions?.length > 0 && (
                  <Card data-testid="btp-solver-solutions-card">
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <Wrench className="h-5 w-5 text-emerald-500" />
                        Soluções ({result.solutions.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-4">
                      {result.solutions.map((s) => (
                        <div key={s.id} className={`rounded-lg border p-4 ${s.recommended ? "border-emerald-500 bg-emerald-50/40 dark:bg-emerald-900/10" : "border-slate-200 dark:border-slate-700"}`}>
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="flex items-center gap-2 font-semibold">
                                {s.label}
                                {s.recommended && <Badge className="bg-emerald-600 text-white">Recomendada</Badge>}
                              </div>
                              <p className="mt-1 text-sm text-slate-600 dark:text-slate-400">{s.description}</p>
                            </div>
                            <div className="text-right text-sm">
                              {s.cost_min_eur != null && (
                                <div className="font-mono text-base font-semibold">
                                  {s.cost_min_eur}–{s.cost_max_eur ?? s.cost_min_eur} €
                                </div>
                              )}
                              <div className="text-xs text-slate-500">
                                {s.duration_days_min != null && (<>{s.duration_days_min}–{s.duration_days_max ?? s.duration_days_min} dias · </>)}
                                <Badge className={`${(RISK_LABEL[s.risk] || RISK_LABEL.medium).color} text-white`}>
                                  Risco: {(RISK_LABEL[s.risk] || RISK_LABEL.medium).label}
                                </Badge>
                                {s.warranty_years != null && <span className="ml-1">· Garantia {s.warranty_years}a</span>}
                              </div>
                            </div>
                          </div>
                          {s.steps?.length > 0 && (
                            <ol className="mt-3 space-y-1 text-sm">
                              {s.steps.map((st, i) => (
                                <li key={i} className="flex gap-2">
                                  <span className="font-mono text-slate-500">{st.order ?? i + 1}.</span>
                                  <span>{st.text}
                                    {st.materials?.length > 0 && (
                                      <span className="ml-1 text-xs text-slate-500">· {st.materials.join(", ")}</span>
                                    )}
                                    {st.biblioteca_pt_ref && (
                                      <Badge variant="outline" className="ml-2 text-xs">BPT: {st.biblioteca_pt_ref}</Badge>
                                    )}
                                  </span>
                                </li>
                              ))}
                            </ol>
                          )}
                          {s.references?.length > 0 && (
                            <div className="mt-3 flex flex-wrap gap-2 text-xs">
                              {s.references.map((ref, i) => (
                                <a key={i} href={ref.url || "#"} target="_blank" rel="noreferrer"
                                  className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-1 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                                  <BookOpen className="h-3 w-3" />
                                  {ref.kind.toUpperCase()} · {ref.code}
                                </a>
                              ))}
                            </div>
                          )}
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Gráficos */}
                {result.charts?.length > 0 && (
                  <Card data-testid="btp-solver-charts-card">
                    <CardHeader>
                      <CardTitle>Gráficos comparativos</CardTitle>
                    </CardHeader>
                    <CardContent className="grid gap-6 lg:grid-cols-2">
                      {result.charts.map((chart) => (
                        <div key={chart.id}>
                          <h4 className="mb-2 text-sm font-semibold">{chart.title}</h4>
                          <ResponsiveContainer width="100%" height={240}>
                            {chart.type === "pie" ? (
                              <PieChart>
                                <Pie data={toRechartsPie(chart)} dataKey="value" nameKey="name"
                                  outerRadius={80} label={(e) => `${e.name}`}>
                                  {toRechartsPie(chart).map((_, i) => (
                                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                                  ))}
                                </Pie>
                                <Tooltip />
                              </PieChart>
                            ) : (
                              <BarChart data={toRechartsBar(chart).data}>
                                <XAxis dataKey="name" fontSize={11} />
                                <YAxis fontSize={11} />
                                <Tooltip />
                                <Legend />
                                {toRechartsBar(chart).series.map((s, i) => (
                                  <Bar key={s} dataKey={s} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                                ))}
                              </BarChart>
                            )}
                          </ResponsiveContainer>
                          {chart.caption && (
                            <p className="mt-1 text-xs text-slate-500">{chart.caption}</p>
                          )}
                        </div>
                      ))}
                    </CardContent>
                  </Card>
                )}

                {/* Plano de ação */}
                {result.action_plan?.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <FileText className="h-5 w-5 text-blue-500" />
                        Plano de ação ({result.action_plan.length})
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <ol className="space-y-2 text-sm">
                        {result.action_plan.map((p, i) => (
                          <li key={i} className="flex gap-2">
                            <span className="font-mono text-slate-500">{p.order ?? i + 1}.</span>
                            <span>{p.text}
                              {p.duration_hours != null && (
                                <span className="ml-2 text-xs text-slate-500">({p.duration_hours} h)</span>
                              )}
                            </span>
                          </li>
                        ))}
                      </ol>
                    </CardContent>
                  </Card>
                )}

                {/* Referências globais */}
                {result.references?.length > 0 && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="flex items-center gap-2">
                        <BookOpen className="h-4 w-4" />
                        Referências e fontes
                      </CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2 text-xs" data-testid="btp-references">
                        {result.references.map((ref, i) => {
                          const isWeb = ref.kind === "web";
                          const Icon = isWeb ? Link2 : BookOpen;
                          return (
                            <a key={i} href={ref.url || "#"} target="_blank" rel="noreferrer"
                              data-testid={`btp-ref-${i}`}
                              className={`inline-flex items-center gap-1 rounded px-2 py-1 border ${
                                isWeb
                                  ? "border-primary/40 bg-primary/5 text-primary hover:bg-primary/10"
                                  : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300"
                              }`}>
                              <Icon className="h-3 w-3" />
                              <span className="font-medium">{(ref.kind || "").toUpperCase()}</span>
                              <span>· {ref.code}</span>
                              {ref.title && <span className="opacity-80">· {ref.title}</span>}
                            </a>
                          );
                        })}
                      </div>
                    </CardContent>
                  </Card>
                )}

                <p className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-800 dark:bg-amber-900/20 dark:text-amber-200">
                  {result.disclaimer}
                </p>
              </div>
            )}
          </div>

          {/* Histórico lateral */}
          <aside className="space-y-3">
            <Card data-testid="btp-solver-history-card">
              <CardHeader>
                <CardTitle className="text-base">Histórico</CardTitle>
              </CardHeader>
              <CardContent>
                {history.length === 0 ? (
                  <p className="text-sm text-slate-500">Ainda não existem análises.</p>
                ) : (
                  <ul className="space-y-2">
                    {history.map((h) => (
                      <li key={h.problem_id}>
                        <button
                          onClick={() => loadFromHistory(h.problem_id)}
                          className="w-full rounded border border-slate-200 bg-white p-2 text-left text-sm hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700"
                          data-testid={`btp-solver-history-item-${h.problem_id}`}
                        >
                          <div className="font-medium">{h.domain || "—"} · {h.urgency || "—"}</div>
                          <div className="truncate text-xs text-slate-500">{h.summary || h.description}</div>
                          <div className="mt-1 text-xs text-slate-400">
                            {(h.generated_at_iso || "").slice(0, 16).replace("T", " ")}
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
            <p className="text-xs text-slate-500">
              Precisa de orçamentar uma solução? <Link to="/quote-editor" className="underline">Vai para o Editor de orçamentos</Link>.
            </p>
          </aside>
        </div>
      </div>
    </div>
  );
}
