import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { Download, RefreshCw, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api, API, eur2 } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

const PERIODOS = [
  { v: "1", label: "Hoje" },
  { v: "7", label: "Últimos 7 dias" },
  { v: "30", label: "Últimos 30 dias" },
  { v: "90", label: "Últimos 90 dias" },
];

const MODOS = [
  { v: "", label: "Todos os modos" },
  { v: "conversa", label: "Conversa" },
  { v: "calculo", label: "Cálculo" },
  { v: "plano", label: "Plano" },
];

const PLANOS = [
  { v: "", label: "Todos os planos" },
  { v: "free", label: "Free" },
  { v: "pro", label: "Pro" },
  { v: "pro_business", label: "Pro Business" },
];


export default function BTPMetrics() {
  const { toast } = useToast();
  const [loading, setLoading] = useState(true);
  const [periodo, setPeriodo] = useState("7");
  const [modo, setModo] = useState("");
  const [plano, setPlano] = useState("");
  const [agregados, setAgregados] = useState(null);
  const [recentes, setRecentes] = useState([]);

  const fromISO = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() - Number(periodo));
    return d.toISOString();
  }, [periodo]);
  // `toISO` recalcula sempre que `periodo` muda para forçar refresh — intencional
  // eslint-disable-next-line react-hooks/exhaustive-deps
  const toISO = useMemo(() => new Date().toISOString(), [periodo]);

  const carregar = useCallback(async () => {
    setLoading(true);
    try {
      const params = { from: fromISO, to: toISO };
      if (modo) params.modo = modo;
      if (plano) params.user_plan = plano;
      const [agg, recent] = await Promise.all([
        api.get("/admin/btp-assistant/metrics", { params }),
        api.get("/admin/btp-assistant/metrics/recent", { params: { limit: 50 } }),
      ]);
      setAgregados(agg.data);
      setRecentes(recent.data.items || []);
    } catch (e) {
      toast({
        title: "Falha a carregar métricas",
        description: String(e?.response?.data?.detail || e?.message || e),
        variant: "destructive",
      });
    } finally {
      setLoading(false);
    }
  }, [fromISO, toISO, modo, plano, toast]);

  useEffect(() => { carregar(); }, [carregar]);

  const exportar = () => {
    const token = localStorage.getItem("construpilot_token");
    const a = document.createElement("a");
    a.href = `${API}/admin/btp-assistant/metrics/export.csv`;
    a.target = "_blank";
    // axios já tem o token nos headers; o browser direct precisa do token na URL
    // porém o backend aceita Bearer header — portanto usamos fetch:
    fetch(`${API}/admin/btp-assistant/metrics/export.csv`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        if (!r.ok) throw new Error("falhou");
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        a.href = url;
        a.download = "btp_assistant_metrics.csv";
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      })
      .catch(() => toast({ title: "Falha a exportar", variant: "destructive" }));
  };


  return (
    <div className="max-w-7xl mx-auto px-4 py-8" data-testid="btp-metrics-page">
      <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
        <div>
          <h1 className="text-2xl font-bold">Assistente BTP · Métricas</h1>
          <p className="text-sm opacity-70">
            Observabilidade das chamadas ao agente (Fase C).
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={periodo} onValueChange={setPeriodo}>
            <SelectTrigger className="w-[180px]" data-testid="btp-metrics-periodo">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {PERIODOS.map((p) => (
                <SelectItem key={p.v} value={p.v}>{p.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={modo || "all"} onValueChange={(v) => setModo(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[150px]"><SelectValue placeholder="Modo" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os modos</SelectItem>
              {MODOS.filter(m => m.v).map((m) => (
                <SelectItem key={m.v} value={m.v}>{m.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={plano || "all"} onValueChange={(v) => setPlano(v === "all" ? "" : v)}>
            <SelectTrigger className="w-[150px]"><SelectValue placeholder="Plano" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todos os planos</SelectItem>
              {PLANOS.filter(p => p.v).map((p) => (
                <SelectItem key={p.v} value={p.v}>{p.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={carregar} disabled={loading}>
            {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </Button>
          <Button variant="secondary" size="sm" onClick={exportar} className="gap-2">
            <Download className="h-4 w-4" /> CSV
          </Button>
        </div>
      </div>

      {/* KPI cards */}
      <div className="grid gap-3 grid-cols-2 lg:grid-cols-4 mb-6">
        <KPICard titulo="Chamadas totais" valor={agregados?.total_calls ?? "—"} />
        <KPICard
          titulo="Latência média"
          valor={agregados ? `${(agregados.avg_duration_ms / 1000).toFixed(2)} s` : "—"}
        />
        <KPICard
          titulo="Taxa de sucesso"
          valor={agregados ? `${(agregados.success_rate * 100).toFixed(1)} %` : "—"}
        />
        <KPICard
          titulo="Custo estimado"
          valor={agregados ? eur2(agregados.cost_estimate_eur) : "—"}
          sub="EUR, estimativa"
        />
      </div>

      {/* Gráfico de barras — tools mais usadas */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Ferramentas mais usadas</CardTitle>
        </CardHeader>
        <CardContent>
          <div style={{ width: "100%", height: 280 }}>
            <ResponsiveContainer>
              <BarChart
                data={agregados?.tools_usage || []}
                margin={{ top: 10, right: 20, left: 0, bottom: 60 }}
              >
                <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 11 }}
                  angle={-30}
                  textAnchor="end"
                  interval={0}
                />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  formatter={(v) => [v, "Chamadas"]}
                  labelFormatter={(l) => `Ferramenta: ${l}`}
                />
                <Bar dataKey="count" fill="#6366f1" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </CardContent>
      </Card>

      {/* Tabela de recentes */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            Últimas 50 chamadas (anonimizadas)
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left opacity-70 border-b">
                  <th className="py-2 pr-3">Momento</th>
                  <th className="py-2 pr-3">Utilizador</th>
                  <th className="py-2 pr-3">Modo</th>
                  <th className="py-2 pr-3">Modelo</th>
                  <th className="py-2 pr-3">Duração</th>
                  <th className="py-2 pr-3">Tools</th>
                  <th className="py-2 pr-3">Estado</th>
                </tr>
              </thead>
              <tbody>
                {recentes.map((r, i) => (
                  <tr key={i} className="border-b border-slate-200 dark:border-slate-800">
                    <td className="py-2 pr-3 whitespace-nowrap">
                      {r.created_at_iso?.replace("T", " ").slice(0, 19)}
                    </td>
                    <td className="py-2 pr-3 font-mono text-xs">{r.user_id_short}</td>
                    <td className="py-2 pr-3">{r.modo}</td>
                    <td className="py-2 pr-3 text-xs opacity-70">{r.modelo}</td>
                    <td className="py-2 pr-3">{(r.duracao_ms/1000).toFixed(1)}s</td>
                    <td className="py-2 pr-3 text-xs">{(r.tools_called || []).join(", ") || "—"}</td>
                    <td className="py-2 pr-3">
                      <EstadoBadge estado={r.status} />
                    </td>
                  </tr>
                ))}
                {recentes.length === 0 && (
                  <tr>
                    <td colSpan={7} className="py-8 text-center opacity-60">
                      Sem chamadas no período seleccionado.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function KPICard({ titulo, valor, sub }) {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4">
      <div className="text-xs opacity-70">{titulo}</div>
      <div className="text-2xl font-bold mt-1">{valor}</div>
      {sub && <div className="text-xs opacity-60 mt-0.5">{sub}</div>}
    </div>
  );
}

function EstadoBadge({ estado }) {
  const map = {
    success: { c: "bg-emerald-500/15 text-emerald-700 border-emerald-500/30", t: "Sucesso" },
    error: { c: "bg-red-500/15 text-red-700 border-red-500/30", t: "Erro" },
    awaiting_confirmation: { c: "bg-amber-500/15 text-amber-800 border-amber-500/30", t: "A aguardar" },
  }[estado] || { c: "bg-slate-500/15 text-slate-700 border-slate-500/30", t: estado };
  return (
    <span className={`inline-block px-2 py-0.5 rounded border text-[10px] ${map.c}`}>
      {map.t}
    </span>
  );
}
