import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
import { Loader2, Wrench, AlertTriangle, FileText, BookOpen } from "lucide-react";

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
      const r = await api.post("/btp-solver/solve", payload);
      setResult(r.data);
      toast.success("Análise concluída.");
      loadHistory();
    } catch (err) {
      const msg = err?.response?.data?.detail || err?.message || "Erro desconhecido";
      toast.error(`Análise falhou: ${msg}`);
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
          <div className="flex items-center gap-3">
            <Wrench className="h-7 w-7 text-emerald-600" />
            <h1 className="text-3xl font-bold tracking-tight sm:text-4xl" data-testid="btp-solver-title">
              Solver BTP
            </h1>
          </div>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Descreva uma patologia ou dúvida técnica — o Coach IA devolve um diagnóstico detalhado
            com causas prováveis, soluções orçamentadas e normativa portuguesa aplicável.
          </p>
        </header>

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
                      {result.web_enriched && <Badge variant="secondary" className="text-xs">Perplexity ✓</Badge>}
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
                      <CardTitle>Referências normativas</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <div className="flex flex-wrap gap-2 text-xs">
                        {result.references.map((ref, i) => (
                          <a key={i} href={ref.url || "#"} target="_blank" rel="noreferrer"
                            className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-1 text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300">
                            <BookOpen className="h-3 w-3" />
                            {ref.kind.toUpperCase()} · {ref.code}
                            {ref.title && <span className="ml-1 text-slate-500">· {ref.title}</span>}
                          </a>
                        ))}
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
