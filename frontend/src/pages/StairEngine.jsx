/**
 * Stair Engine — Calculador de escadas PT (RGEU, REH, RSCIE, EN 1992/1991, DL 163/2006)
 */
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Checkbox } from "../components/ui/checkbox";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL + "/api";

function useAuthHeaders() {
  const { user } = useAuth();
  return useMemo(() => {
    const token =
      (typeof window !== "undefined" &&
        localStorage.getItem("construpilot_token")) ||
      null;
    return token ? { Authorization: `Bearer ${token}` } : {};
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user]);
}

const USO_LABELS = {
  habitacao: "Habitação",
  comercio: "Comércio",
  publico: "Público",
  evacuacao: "Via de evacuação",
};
const MAT_LABELS = { betao: "Betão armado", madeira: "Madeira", metal: "Metal" };

const STATE_STYLE = {
  conforme: { bg: "bg-emerald-50", text: "text-emerald-700", border: "border-emerald-300", icon: "✓" },
  atencao: { bg: "bg-amber-50", text: "text-amber-700", border: "border-amber-300", icon: "⚠" },
  nao_conforme: { bg: "bg-rose-50", text: "text-rose-700", border: "border-rose-300", icon: "✗" },
};

function Gauge({ score }) {
  const pct = Math.max(0, Math.min(10, score)) * 10;
  const color = score >= 8 ? "#059669" : score >= 6 ? "#f59e0b" : "#ef4444";
  return (
    <div className="flex items-center gap-4" data-testid="stair-gauge">
      <svg width="110" height="60" viewBox="0 0 110 60">
        <path d="M 10 55 A 45 45 0 0 1 100 55" stroke="#e2e8f0" strokeWidth="8" fill="none" strokeLinecap="round" />
        <path
          d="M 10 55 A 45 45 0 0 1 100 55"
          stroke={color}
          strokeWidth="8"
          fill="none"
          strokeLinecap="round"
          strokeDasharray={`${(pct / 100) * 141} 141`}
        />
        <text x="55" y="50" textAnchor="middle" fontSize="20" fontWeight="700" fill={color}>
          {score.toFixed(1)}
        </text>
      </svg>
      <div className="text-sm">
        <p className="font-semibold text-slate-900 dark:text-slate-100">Conforto</p>
        <p className="text-slate-500 dark:text-slate-400">Escala 0-10</p>
      </div>
    </div>
  );
}

export default function StairEngine() {
  const headers = useAuthHeaders();
  const [form, setForm] = useState({
    altura_total_m: 3.0,
    pe_direito_m: 2.7,
    largura_m: 1.0,
    num_degraus: "",
    uso: "habitacao",
    material: "betao",
    acessibilidade: false,
    capacidade: "",
    project_name: "",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [generatingPdf, setGeneratingPdf] = useState(false);

  const fetchHistory = useCallback(async () => {
    try {
      const r = await fetch(`${API}/stair-engine/history`, { headers });
      if (r.ok) {
        const d = await r.json();
        setHistory(d.items || []);
      }
    } catch {}
  }, [headers]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  const submit = async (e) => {
    e?.preventDefault?.();
    setLoading(true);
    try {
      const body = {
        ...form,
        altura_total_m: parseFloat(form.altura_total_m),
        pe_direito_m: parseFloat(form.pe_direito_m),
        largura_m: parseFloat(form.largura_m),
        num_degraus: form.num_degraus ? parseInt(form.num_degraus, 10) : null,
        capacidade: form.capacidade ? parseInt(form.capacidade, 10) : null,
        project_name: form.project_name || null,
      };
      const r = await fetch(`${API}/stair-engine/calculate`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Cálculo falhou");
      setResult(d);
      fetchHistory();
      toast.success("Dimensionamento concluído.");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setLoading(false);
    }
  };

  const downloadPdf = async () => {
    if (!result?.plan_id) return;
    setGeneratingPdf(true);
    try {
      const r = await fetch(`${API}/stair-engine/generate-pdf`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ plan_id: result.plan_id }),
      });
      if (!r.ok) throw new Error("PDF indisponível");
      const blob = await r.blob();
      const disp = r.headers.get("content-disposition") || "";
      const m = disp.match(/filename="([^"]+)"/);
      const fn = m ? m[1] : `dossier_escada_${result.plan_id}.pdf`;
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = fn;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      toast.success("Dossier PDF gerado.");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setGeneratingPdf(false);
    }
  };

  const pickHistory = async (planId) => {
    try {
      const r = await fetch(`${API}/stair-engine/${planId}`, { headers });
      if (r.ok) setResult(await r.json());
    } catch {}
  };

  const sumr = result?.resumo_verificacoes;

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 py-10 px-4" data-testid="stair-engine-page">
      <div className="max-w-7xl mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
            Calculador de Escadas
          </h1>
          <p className="text-base text-slate-600 dark:text-slate-400 mt-2 max-w-2xl">
            Dimensionamento ergonómico (Blondel) + verificações normativas PT
            (RGEU, REH, RSCIE, Eurocódigos, DL 163/2006). Dossier PDF profissional.
          </p>
        </header>

        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 lg:col-span-4 space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Parâmetros</CardTitle>
              </CardHeader>
              <CardContent>
                <form onSubmit={submit} className="space-y-3">
                  <div>
                    <Label htmlFor="pn">Nome do projeto (opcional)</Label>
                    <Input
                      id="pn"
                      value={form.project_name}
                      onChange={(e) => setForm({ ...form, project_name: e.target.value })}
                      placeholder="ex: Moradia T2 Lisboa"
                      data-testid="stair-project-name"
                    />
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label htmlFor="h">Altura total (m)</Label>
                      <Input
                        id="h"
                        type="number"
                        step="0.01"
                        value={form.altura_total_m}
                        onChange={(e) => setForm({ ...form, altura_total_m: e.target.value })}
                        data-testid="stair-altura"
                        required
                      />
                    </div>
                    <div>
                      <Label htmlFor="pd">Pé-direito (m)</Label>
                      <Input
                        id="pd"
                        type="number"
                        step="0.01"
                        value={form.pe_direito_m}
                        onChange={(e) => setForm({ ...form, pe_direito_m: e.target.value })}
                        data-testid="stair-pe-direito"
                        required
                      />
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    <div>
                      <Label htmlFor="l">Largura (m)</Label>
                      <Input
                        id="l"
                        type="number"
                        step="0.01"
                        value={form.largura_m}
                        onChange={(e) => setForm({ ...form, largura_m: e.target.value })}
                        data-testid="stair-largura"
                      />
                    </div>
                    <div>
                      <Label htmlFor="n">Nº degraus (opcional)</Label>
                      <Input
                        id="n"
                        type="number"
                        value={form.num_degraus}
                        onChange={(e) => setForm({ ...form, num_degraus: e.target.value })}
                        placeholder="auto"
                        data-testid="stair-num"
                      />
                    </div>
                  </div>
                  <div>
                    <Label>Uso</Label>
                    <Select value={form.uso} onValueChange={(v) => setForm({ ...form, uso: v })}>
                      <SelectTrigger data-testid="stair-uso"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(USO_LABELS).map(([k, v]) => (
                          <SelectItem key={k} value={k}>{v}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div>
                    <Label>Material</Label>
                    <Select value={form.material} onValueChange={(v) => setForm({ ...form, material: v })}>
                      <SelectTrigger data-testid="stair-material"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {Object.entries(MAT_LABELS).map(([k, v]) => (
                          <SelectItem key={k} value={k}>{v}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  {form.uso === "evacuacao" && (
                    <div>
                      <Label htmlFor="cap">Capacidade (pessoas)</Label>
                      <Input
                        id="cap"
                        type="number"
                        value={form.capacidade}
                        onChange={(e) => setForm({ ...form, capacidade: e.target.value })}
                        data-testid="stair-capacidade"
                        required
                      />
                    </div>
                  )}
                  <label className="flex items-center gap-2 cursor-pointer text-sm">
                    <Checkbox
                      checked={form.acessibilidade}
                      onCheckedChange={(v) => setForm({ ...form, acessibilidade: !!v })}
                      data-testid="stair-acessib"
                    />
                    Verificação acessibilidade (DL 163/2006)
                  </label>
                  <Button type="submit" disabled={loading} className="w-full" data-testid="stair-calc-btn">
                    {loading ? "A calcular…" : "Dimensionar"}
                  </Button>
                </form>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Histórico</CardTitle>
              </CardHeader>
              <CardContent>
                {history.length === 0 ? (
                  <p className="text-sm text-slate-500">Sem análises ainda.</p>
                ) : (
                  <div className="space-y-2" data-testid="stair-history">
                    {history.map((h) => (
                      <button
                        key={h.plan_id}
                        onClick={() => pickHistory(h.plan_id)}
                        className={`w-full text-left p-2 rounded border text-xs ${
                          result?.plan_id === h.plan_id
                            ? "border-emerald-500 bg-emerald-50 dark:bg-emerald-500/10"
                            : "border-slate-200 hover:border-slate-400 dark:border-slate-700 dark:hover:border-slate-500"
                        }`}
                        data-testid={`stair-history-item-${h.plan_id}`}
                      >
                        <div className="font-medium truncate">{h.project_name || "Escada"}</div>
                        <div className="text-slate-500 dark:text-slate-400 flex items-center justify-between">
                          <span>{h.dimensoes?.num_degraus} degraus · {USO_LABELS[h.inputs?.uso]}</span>
                          <Badge variant="outline">{h.conforto_score}/10</Badge>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </CardContent>
            </Card>
          </aside>

          <main className="col-span-12 lg:col-span-8 space-y-6">
            {!result ? (
              <Card>
                <CardContent className="py-16 text-center text-slate-600" data-testid="stair-empty">
                  Preencha os parâmetros à esquerda e clique em "Dimensionar".
                </CardContent>
              </Card>
            ) : (
              <>
                <Card>
                  <CardHeader className="flex-row items-center justify-between">
                    <div>
                      <CardTitle className="text-lg">
                        {result.project_name || "Escada"}
                      </CardTitle>
                      <p className="text-sm text-slate-500 mt-1">
                        {result.dimensoes.num_degraus} degraus · h {result.dimensoes.altura_degrau_cm} cm
                        · g {result.dimensoes.profundidade_cobertor_cm} cm · {result.dimensoes.inclinacao_graus}°
                      </p>
                    </div>
                    <Button variant="outline" onClick={downloadPdf} disabled={generatingPdf}
                            data-testid="stair-pdf-btn">
                      {generatingPdf ? "A gerar…" : "Gerar dossier PDF"}
                    </Button>
                  </CardHeader>
                  <CardContent className="grid md:grid-cols-2 gap-6">
                    <div dangerouslySetInnerHTML={{ __html: result.svgs?.plan_svg || "" }} />
                    <div dangerouslySetInnerHTML={{ __html: result.svgs?.elevation_svg || "" }} />
                  </CardContent>
                </Card>

                <div className="grid md:grid-cols-3 gap-4">
                  <Card>
                    <CardHeader><CardTitle className="text-sm">Blondel</CardTitle></CardHeader>
                    <CardContent>
                      <p className="text-2xl font-bold">{result.dimensoes.blondel} cm</p>
                      <p className="text-xs text-slate-500">
                        Intervalo ideal 60-64 cm · {result.dimensoes.blondel >= 60 && result.dimensoes.blondel <= 64 ? "✓ ergonómico" : "⚠ fora do intervalo"}
                      </p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader><CardTitle className="text-sm">Projeção horizontal</CardTitle></CardHeader>
                    <CardContent>
                      <p className="text-2xl font-bold">{result.dimensoes.projecao_horizontal_m} m</p>
                      <p className="text-xs text-slate-500">Rampante {result.dimensoes.comprimento_rampante_m} m</p>
                    </CardContent>
                  </Card>
                  <Card>
                    <CardHeader><CardTitle className="text-sm">Conforto</CardTitle></CardHeader>
                    <CardContent><Gauge score={result.conforto_score} /></CardContent>
                  </Card>
                </div>

                <Card>
                  <CardHeader>
                    <CardTitle className="text-base">Verificações normativas</CardTitle>
                    {sumr && (
                      <p className="text-sm text-slate-500">
                        {sumr.conforme} conforme · {sumr.atencao} atenção · {sumr.nao_conforme} não conforme
                      </p>
                    )}
                  </CardHeader>
                  <CardContent className="space-y-2" data-testid="stair-verifs">
                    {result.verificacoes.map((v, i) => {
                      const s = STATE_STYLE[v.estado];
                      return (
                        <div key={i} className={`flex items-start gap-3 p-3 rounded border ${s.bg} ${s.border}`}>
                          <span className={`font-bold ${s.text} text-lg leading-none`}>{s.icon}</span>
                          <div className="flex-1 text-sm">
                            <div className="flex items-center gap-2 mb-0.5">
                              <Badge variant="outline" className="text-[10px]">{v.norma}</Badge>
                              <span className="text-xs text-slate-500">{v.referencia}</span>
                            </div>
                            <p className={s.text}>{v.mensagem}</p>
                          </div>
                        </div>
                      );
                    })}
                  </CardContent>
                </Card>

                {result.alertas?.length > 0 && (
                  <Card>
                    <CardHeader><CardTitle className="text-base">Alertas</CardTitle></CardHeader>
                    <CardContent>
                      <ul className="list-disc pl-5 text-sm space-y-1">
                        {result.alertas.map((a, i) => <li key={i} className="text-rose-700">{a}</li>)}
                      </ul>
                    </CardContent>
                  </Card>
                )}

                {result.patamares?.length > 0 && (
                  <Card>
                    <CardHeader><CardTitle className="text-base">Recomendações estruturais</CardTitle></CardHeader>
                    <CardContent>
                      <ul className="list-disc pl-5 text-sm space-y-1">
                        {result.patamares.map((p, i) => <li key={i}>{p}</li>)}
                      </ul>
                    </CardContent>
                  </Card>
                )}

                {result.ia_text && (
                  <Card>
                    <CardHeader>
                      <CardTitle className="text-base">Análise IA (Opus 5.5)</CardTitle>
                    </CardHeader>
                    <CardContent>
                      <p className="text-sm whitespace-pre-wrap">{result.ia_text}</p>
                    </CardContent>
                  </Card>
                )}
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
