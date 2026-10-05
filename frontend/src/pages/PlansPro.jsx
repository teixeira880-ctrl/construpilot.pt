/**
 * Plantas Pro — Autodesk APS + Cascade IA
 *
 * Fluxo:
 *   1. Upload DWG/RVT/IFC → backend
 *   2. Polling status (translation Autodesk, 2-10 min)
 *   3. Autodesk Viewer SDK v7 (CDN oficial) com token assinado
 *   4. Botão "Analisar com IA" → relatório estruturado PT-PT
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Badge } from "../components/ui/badge";
import { Progress } from "../components/ui/progress";
import { Separator } from "../components/ui/separator";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

const API = process.env.REACT_APP_BACKEND_URL + "/api";
const VIEWER_SCRIPT = "https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/viewer3D.min.js";
const VIEWER_STYLE = "https://developer.api.autodesk.com/modelderivative/v2/viewers/7.*/style.min.css";

const STATUS_LABELS = {
  pending: { label: "A aguardar", color: "bg-amber-500" },
  inprogress: { label: "Em processamento", color: "bg-sky-500" },
  success: { label: "Pronto", color: "bg-emerald-600" },
  failed: { label: "Falhou", color: "bg-rose-600" },
  timeout: { label: "Expirado", color: "bg-rose-600" },
  unknown: { label: "Desconhecido", color: "bg-slate-500" },
};

function useAuthHeaders() {
  const { token } = useAuth();
  return useMemo(
    () => ({ Authorization: token ? `Bearer ${token}` : undefined }),
    [token]
  );
}

async function loadAutodeskViewer() {
  if (window.Autodesk?.Viewing) return;
  if (!document.querySelector(`link[href="${VIEWER_STYLE}"]`)) {
    const link = document.createElement("link");
    link.rel = "stylesheet";
    link.href = VIEWER_STYLE;
    document.head.appendChild(link);
  }
  if (!document.querySelector(`script[src="${VIEWER_SCRIPT}"]`)) {
    await new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = VIEWER_SCRIPT;
      s.async = true;
      s.onload = resolve;
      s.onerror = () => reject(new Error("Falha ao carregar Autodesk Viewer SDK"));
      document.head.appendChild(s);
    });
  }
}

function HistoryList({ items, onPick, selected }) {
  if (!items.length) {
    return (
      <p className="text-sm text-slate-500" data-testid="plans-pro-empty-history">
        Ainda sem planos. Faça upload do seu primeiro DWG/RVT/IFC.
      </p>
    );
  }
  return (
    <div className="space-y-2" data-testid="plans-pro-history-list">
      {items.map((it) => {
        const s = STATUS_LABELS[it.translation_status] || STATUS_LABELS.unknown;
        return (
          <button
            key={it.plan_id}
            onClick={() => onPick(it)}
            data-testid={`plan-history-item-${it.plan_id}`}
            className={`w-full text-left rounded-md border p-3 transition ${
              selected?.plan_id === it.plan_id
                ? "border-emerald-500 bg-emerald-50"
                : "border-slate-200 hover:border-slate-400"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-medium text-sm">{it.file_name}</span>
              <span className={`inline-block h-2 w-2 rounded-full ${s.color}`} />
            </div>
            <div className="mt-1 flex items-center justify-between text-xs text-slate-500">
              <span>{(it.file_type || "").toUpperCase()}</span>
              <span>{s.label}</span>
            </div>
          </button>
        );
      })}
    </div>
  );
}

function AnalysisPanel({ analysis }) {
  if (!analysis) return null;
  const synthesis = analysis.ai_analysis?.synthesis;
  const vision = analysis.ai_analysis?.vision;
  const norms = analysis.ai_analysis?.norms;
  const quantities = analysis.quantities || {};

  return (
    <div className="space-y-6" data-testid="plans-pro-analysis-panel">
      {synthesis?.resumo && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Resumo técnico</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{synthesis.resumo}</p>
          </CardContent>
        </Card>
      )}

      {Object.keys(quantities).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Quantidades Autodesk</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm" data-testid="plans-pro-quantities-table">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-2 font-medium">Ouvrage</th>
                  <th className="text-right py-2 font-medium">N.º entidades</th>
                  <th className="text-left py-2 font-medium pl-4">Fonte</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(quantities).map(([cat, data]) => (
                  <tr key={cat} className="border-b border-slate-100">
                    <td className="py-1.5">{cat}</td>
                    <td className="py-1.5 text-right tabular-nums">{data.count}</td>
                    <td className="py-1.5 pl-4 text-slate-500 text-xs">
                      {data.source === "layers" ? "layers" : "categorias"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {synthesis?.ouvrages?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Estimativa de orçamento (Biblioteca PT 2026)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm" data-testid="plans-pro-budget-table">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-2 font-medium">Ouvrage</th>
                  <th className="text-right py-2 font-medium">Qtd</th>
                  <th className="text-right py-2 font-medium">Un</th>
                  <th className="text-right py-2 font-medium">PU (€)</th>
                  <th className="text-right py-2 font-medium">Total HT (€)</th>
                </tr>
              </thead>
              <tbody>
                {synthesis.ouvrages.map((o, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    <td className="py-1.5">{o.nome}</td>
                    <td className="py-1.5 text-right tabular-nums">{o.quantidade ?? "-"}</td>
                    <td className="py-1.5 text-right">{o.unidade || "-"}</td>
                    <td className="py-1.5 text-right tabular-nums">{o.pu_eur?.toFixed?.(2) ?? "-"}</td>
                    <td className="py-1.5 text-right tabular-nums font-medium">
                      {o.total_eur?.toFixed?.(2) ?? "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {synthesis.orcamento && (
              <div className="mt-4 flex justify-end gap-6 text-sm">
                <div>
                  <span className="text-slate-500">Total HT: </span>
                  <span className="font-medium">
                    {synthesis.orcamento.total_ht_eur?.toFixed?.(2)} €
                  </span>
                </div>
                <div>
                  <span className="text-slate-500">IVA 23%: </span>
                  <span className="font-medium">
                    {synthesis.orcamento.iva_eur?.toFixed?.(2)} €
                  </span>
                </div>
                <div className="text-base font-semibold">
                  <span className="text-slate-500">Total c/ IVA: </span>
                  <span>{synthesis.orcamento.total_ttc_eur?.toFixed?.(2)} €</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {synthesis?.normas_aplicaveis?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Normas aplicáveis</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc pl-5 text-sm space-y-1">
              {synthesis.normas_aplicaveis.map((n, i) => (
                <li key={i}>{n}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {synthesis?.recomendacoes?.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Recomendações</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc pl-5 text-sm space-y-1">
              {synthesis.recomendacoes.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {norms?.text && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Normas detalhadas (pesquisa web)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-slate-700 whitespace-pre-wrap">{norms.text}</p>
            {norms.citations?.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-2">
                {norms.citations.map((c, i) => (
                  <a
                    key={i}
                    href={c}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-sky-700 underline"
                  >
                    [{i + 1}]
                  </a>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {vision?.plan_type && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Leitura visual (OpenAI)</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="text-sm space-y-1">
              <div>
                <span className="text-slate-500">Tipo: </span>
                <Badge variant="outline">{vision.plan_type}</Badge>
              </div>
              {vision.scale && (
                <div>
                  <span className="text-slate-500">Escala: </span>
                  {vision.scale}
                </div>
              )}
              {vision.elements?.length > 0 && (
                <div className="pt-2">
                  <div className="text-slate-500 mb-1">Elementos detetados:</div>
                  <div className="flex flex-wrap gap-2">
                    {vision.elements.map((el, i) => (
                      <Badge key={i} variant="secondary">
                        {el.kind} × {el.count}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

export default function PlansPro() {
  const headers = useAuthHeaders();
  const [history, setHistory] = useState([]);
  const [selected, setSelected] = useState(null);
  const [projectHint, setProjectHint] = useState("");
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [config, setConfig] = useState(null);
  const [analysis, setAnalysis] = useState(null);
  const viewerRef = useRef(null);
  const viewerInstanceRef = useRef(null);
  const pollerRef = useRef(null);
  const fileInputRef = useRef(null);

  const fetchHistory = useCallback(async () => {
    try {
      const r = await fetch(`${API}/plans-pro/history/list?limit=30`, { headers });
      if (!r.ok) return;
      const d = await r.json();
      setHistory(d.items || []);
    } catch (e) {
      // silencioso
    }
  }, [headers]);

  const fetchConfig = useCallback(async () => {
    try {
      const r = await fetch(`${API}/plans-pro/config`, { headers });
      if (r.ok) setConfig(await r.json());
    } catch (e) {}
  }, [headers]);

  useEffect(() => {
    fetchHistory();
    fetchConfig();
  }, [fetchHistory, fetchConfig]);

  // Polling do status do plano selecionado
  useEffect(() => {
    if (pollerRef.current) {
      clearInterval(pollerRef.current);
      pollerRef.current = null;
    }
    if (!selected) return;
    if (["success", "failed", "timeout"].includes(selected.translation_status)) return;
    pollerRef.current = setInterval(async () => {
      try {
        const r = await fetch(`${API}/plans-pro/${selected.plan_id}/status`, { headers });
        if (!r.ok) return;
        const d = await r.json();
        setSelected(d);
        setHistory((prev) =>
          prev.map((it) => (it.plan_id === d.plan_id ? d : it))
        );
        if (["success", "failed", "timeout"].includes(d.translation_status)) {
          clearInterval(pollerRef.current);
          pollerRef.current = null;
        }
      } catch (e) {}
    }, 7000);
    return () => {
      if (pollerRef.current) clearInterval(pollerRef.current);
    };
  }, [selected?.plan_id, selected?.translation_status, headers]);

  const handleUpload = async (file) => {
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      if (projectHint) fd.append("project_id", projectHint.slice(0, 50));
      const r = await fetch(`${API}/plans-pro/upload`, {
        method: "POST",
        body: fd,
        headers,
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Upload falhou");
      toast.success("Upload OK. Translation Autodesk a correr…");
      setSelected(d);
      fetchHistory();
    } catch (e) {
      toast.error(e.message);
    } finally {
      setUploading(false);
    }
  };

  const handleAnalyze = async () => {
    if (!selected) return;
    setAnalyzing(true);
    try {
      const r = await fetch(`${API}/plans-pro/${selected.plan_id}/analyze`, {
        method: "POST",
        body: JSON.stringify({
          project_hint: projectHint || null,
          include_web_norms: true,
        }),
        headers: { ...headers, "Content-Type": "application/json" },
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Análise falhou");
      setAnalysis(d);
      toast.success("Análise IA concluída.");
    } catch (e) {
      toast.error(e.message);
    } finally {
      setAnalyzing(false);
    }
  };

  // Autodesk Viewer: carrega quando plano translation success
  useEffect(() => {
    if (!selected || selected.translation_status !== "success") return;
    let cancelled = false;
    (async () => {
      try {
        await loadAutodeskViewer();
        if (cancelled) return;
        const tr = await fetch(
          `${API}/plans-pro/${selected.plan_id}/viewer-token`,
          { headers }
        );
        if (!tr.ok) return;
        const tok = await tr.json();
        const options = {
          env: "AutodeskProduction",
          api: "streamingV2",
          getAccessToken: (onTokenReady) =>
            onTokenReady(tok.access_token, tok.expires_in),
        };
        window.Autodesk.Viewing.Initializer(options, () => {
          if (!viewerRef.current || cancelled) return;
          if (viewerInstanceRef.current) {
            try {
              viewerInstanceRef.current.finish();
            } catch {}
          }
          const viewer = new window.Autodesk.Viewing.GuiViewer3D(viewerRef.current);
          viewer.start();
          viewerInstanceRef.current = viewer;
          const documentId = `urn:${tok.urn}`;
          window.Autodesk.Viewing.Document.load(
            documentId,
            (doc) => {
              const defaultModel = doc.getRoot().getDefaultGeometry();
              if (defaultModel) viewer.loadDocumentNode(doc, defaultModel);
            },
            () => toast.error("Autodesk Viewer: falha ao carregar documento")
          );
        });
      } catch (e) {
        toast.error(e.message || "Viewer indisponível");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selected?.plan_id, selected?.translation_status, headers]);

  // Buscar análise persistida ao mudar plano
  useEffect(() => {
    setAnalysis(null);
    if (!selected || selected.translation_status !== "success") return;
    (async () => {
      try {
        const r = await fetch(`${API}/plans-pro/${selected.plan_id}/analysis`, { headers });
        if (r.ok) setAnalysis(await r.json());
      } catch {}
    })();
  }, [selected?.plan_id, selected?.translation_status, headers]);

  const statusInfo = selected
    ? STATUS_LABELS[selected.translation_status] || STATUS_LABELS.unknown
    : null;
  const progressValue = parseInt(selected?.progress || "0", 10) || 0;

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4" data-testid="plans-pro-page">
      <div className="max-w-7xl mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-slate-900">
            Plantas Pro
          </h1>
          <p className="text-base text-slate-600 mt-2 max-w-2xl">
            Carregue DWG, RVT ou IFC. O Autodesk APS traduz, o Opus 5.5 estrutura
            o orçamento com a Biblioteca PT 2026 e as normas aplicáveis.
          </p>
          {config && !config.autodesk_configured && (
            <div className="mt-4 rounded border border-amber-400 bg-amber-50 p-3 text-sm text-amber-900">
              Autodesk APS não está configurado no servidor. Contacte o administrador.
            </div>
          )}
        </header>

        <div className="grid grid-cols-12 gap-6">
          <aside className="col-span-12 lg:col-span-3 space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Novo plano</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <Input
                  type="file"
                  ref={fileInputRef}
                  accept=".dwg,.dxf,.rvt,.ifc,.nwc,.nwd,.pdf"
                  onChange={(e) => handleUpload(e.target.files?.[0])}
                  disabled={uploading || !config?.autodesk_configured}
                  data-testid="plans-pro-file-input"
                />
                <Textarea
                  placeholder="Contexto do projeto (opcional) — tipo de obra, zona, dimensão…"
                  value={projectHint}
                  onChange={(e) => setProjectHint(e.target.value)}
                  rows={3}
                  data-testid="plans-pro-hint-input"
                />
                <p className="text-xs text-slate-500">
                  Formatos: {config?.accepted_extensions?.join(", ")} · máx{" "}
                  {config?.max_size_mb} MB
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="text-base">Histórico</CardTitle>
              </CardHeader>
              <CardContent>
                <HistoryList items={history} onPick={setSelected} selected={selected} />
              </CardContent>
            </Card>
          </aside>

          <main className="col-span-12 lg:col-span-9 space-y-6">
            {!selected && (
              <Card>
                <CardContent className="py-16 text-center">
                  <p className="text-base text-slate-600" data-testid="plans-pro-no-selection">
                    Faça upload de um plano para começar ou selecione um do histórico.
                  </p>
                </CardContent>
              </Card>
            )}

            {selected && (
              <Card>
                <CardHeader>
                  <div className="flex items-center justify-between flex-wrap gap-2">
                    <CardTitle className="text-lg truncate" data-testid="plans-pro-selected-name">
                      {selected.file_name}
                    </CardTitle>
                    <Badge className={`${statusInfo.color} text-white`} data-testid="plans-pro-status-badge">
                      {statusInfo.label}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className="space-y-4">
                  {selected.translation_status !== "success" && (
                    <>
                      <Progress value={progressValue} className="h-2" />
                      <p className="text-sm text-slate-500">
                        Progresso: {selected.progress || "0%"}. A translation Autodesk
                        demora 2-10 minutos consoante o ficheiro.
                      </p>
                    </>
                  )}

                  {selected.translation_status === "success" && (
                    <>
                      <div
                        ref={viewerRef}
                        data-testid="plans-pro-viewer"
                        className="w-full h-[500px] bg-slate-900 rounded-md relative overflow-hidden"
                      />
                      <Separator />
                      <div className="flex justify-end">
                        <Button
                          onClick={handleAnalyze}
                          disabled={analyzing}
                          data-testid="plans-pro-analyze-btn"
                        >
                          {analyzing ? "A analisar…" : "Analisar com IA"}
                        </Button>
                      </div>
                    </>
                  )}

                  {selected.translation_status === "failed" && (
                    <div className="rounded border border-rose-400 bg-rose-50 p-3 text-sm text-rose-900">
                      Translation falhou. Reenvie o ficheiro ou use outro formato.
                    </div>
                  )}
                </CardContent>
              </Card>
            )}

            <AnalysisPanel analysis={analysis} />
          </main>
        </div>
      </div>
    </div>
  );
}
