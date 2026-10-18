import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  AlertTriangle,
  BrainCircuit,
  CheckCircle2,
  Euro,
  Flag,
  Loader2,
  Play,
  RefreshCw,
  XCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

/**
 * Painel admin do BET-PT Agent.
 * Feature flag `BET_AGENT_ENABLED` controla o pipeline live. UI consegue
 * sempre consultar status/costs/runs; só o botão "Correr pipeline" fica
 * disponível quando ambos (feature_flag + anthropic_key_present) são true.
 * Rota: /admin/bet-agent  (admin role, bloqueado para demo).
 */
export default function AdminBetAgent() {
  const [status, setStatus] = useState(null);
  const [loadingStatus, setLoadingStatus] = useState(true);
  const [runs, setRuns] = useState([]);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [costs, setCosts] = useState(null);
  const [running, setRunning] = useState(false);
  const [selected, setSelected] = useState(null);
  const [projectId, setProjectId] = useState("");
  const [briefJson, setBriefJson] = useState(
    JSON.stringify(
      {
        materials: { slab_type: "aligeirada_vigotas_abobadilhas", masonry_type: "tijolo_ceramico_furado_15" },
        seismic: { zone: "1.3", soil_class: "C", municipio: "Lisboa" },
        requested_deliverables: [
          "memoria_descritiva",
          "planta_fundacoes",
          "plantas_estrutura_piso",
          "verificacao_sismica_np_en_1998_1",
        ],
      },
      null,
      2
    )
  );
  const arqRef = useRef(null);
  const geoRef = useRef(null);

  const loadStatus = async () => {
    setLoadingStatus(true);
    try {
      const { data } = await api.get("/admin/bet-agent/status");
      setStatus(data);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erro a carregar estado.");
    } finally {
      setLoadingStatus(false);
    }
  };

  const loadRuns = async () => {
    setLoadingRuns(true);
    try {
      const [{ data: r }, { data: c }] = await Promise.all([
        api.get("/admin/bet-agent/runs?limit=20"),
        api.get("/admin/bet-agent/costs"),
      ]);
      setRuns(r?.runs || []);
      setCosts(c || null);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erro a carregar dossiers.");
    } finally {
      setLoadingRuns(false);
    }
  };

  useEffect(() => {
    loadStatus();
    loadRuns();
  }, []);

  const runPipeline = async () => {
    if (!arqRef.current?.files?.[0]) {
      toast.error("Falta o PDF de arquitectura.");
      return;
    }
    setRunning(true);
    try {
      const fd = new FormData();
      fd.append("arquitectura", arqRef.current.files[0]);
      if (geoRef.current?.files?.[0]) fd.append("geotecnico", geoRef.current.files[0]);
      fd.append("brief_json", briefJson);
      if (projectId) fd.append("project_id", projectId);
      const { data } = await api.post("/admin/bet-agent/run", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`Dossier concluído — status ${data?.summary?.global_status || "?"}`);
      setSelected(data);
      await loadRuns();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      const msg = typeof detail === "string" ? detail : detail?.message || "Erro no pipeline.";
      toast.error(msg);
    } finally {
      setRunning(false);
    }
  };

  const statusBadge = (s) => {
    const map = {
      verde: { color: "bg-emerald-600", icon: CheckCircle2 },
      amarelo: { color: "bg-amber-500", icon: AlertTriangle },
      vermelho: { color: "bg-red-600", icon: XCircle },
    };
    const cfg = map[s] || { color: "bg-slate-500", icon: Flag };
    const Icon = cfg.icon;
    return (
      <Badge className={`${cfg.color} text-white`} data-testid={`global-status-${s}`}>
        <Icon className="w-3 h-3 mr-1" /> {s || "?"}
      </Badge>
    );
  };

  const canRun = !!(status?.feature_flag && status?.anthropic_key_present);

  return (
    <div className="max-w-6xl mx-auto p-6 space-y-6" data-testid="admin-bet-agent-page">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <BrainCircuit className="w-6 h-6" /> BET-PT Agent (admin)
          </h1>
          <p className="text-sm text-slate-500">
            Pipeline estrutural híbrido: Reader Claude Opus 5.5 + checks determinísticos + verificador.
          </p>
        </div>
        <Button variant="outline" onClick={() => { loadStatus(); loadRuns(); }} data-testid="refresh-btn">
          <RefreshCw className="w-4 h-4 mr-2" /> Atualizar
        </Button>
      </div>

      {/* STATUS */}
      <section className="rounded-xl border bg-white p-5 space-y-3" data-testid="bet-agent-status">
        <h2 className="font-semibold">Estado operacional</h2>
        {loadingStatus ? (
          <div className="flex items-center gap-2 text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" /> a carregar…
          </div>
        ) : status ? (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div data-testid="status-feature-flag">
              <div className="text-slate-500">Feature flag</div>
              <div className="font-medium">
                {status.feature_flag ? (
                  <span className="text-emerald-700">BET_AGENT_ENABLED=true</span>
                ) : (
                  <span className="text-red-700">OFF</span>
                )}
              </div>
            </div>
            <div data-testid="status-key">
              <div className="text-slate-500">ANTHROPIC_API_KEY</div>
              <div className="font-medium">
                {status.anthropic_key_present ? (
                  <span className="text-emerald-700">presente</span>
                ) : (
                  <span className="text-red-700">ausente</span>
                )}
              </div>
            </div>
            <div>
              <div className="text-slate-500">Modelo reader</div>
              <div className="font-medium">{status.reader_model_default}</div>
            </div>
            <div>
              <div className="text-slate-500">Limite €/dossier</div>
              <div className="font-medium flex items-center gap-1">
                <Euro className="w-3 h-3" />
                {Number(status.cost_limit_eur || 10).toFixed(2)}
              </div>
            </div>
          </div>
        ) : (
          <div className="text-sm text-slate-500">sem dados</div>
        )}
      </section>

      {/* RUN */}
      <section className="rounded-xl border bg-white p-5 space-y-4" data-testid="bet-agent-run">
        <h2 className="font-semibold">Correr pipeline</h2>
        {!canRun && (
          <div className="rounded-md bg-amber-50 border border-amber-200 p-3 text-sm text-amber-900">
            Pipeline inacessível porque {status?.feature_flag ? "" : "a feature flag está OFF"}
            {!status?.feature_flag && !status?.anthropic_key_present && " e "}
            {status?.anthropic_key_present ? "" : "ANTHROPIC_API_KEY não está presente"}.
          </div>
        )}
        <div className="grid md:grid-cols-2 gap-4">
          <div className="space-y-2">
            <Label htmlFor="arq">PDF arquitectura</Label>
            <Input id="arq" type="file" accept="application/pdf" ref={arqRef} data-testid="input-arq" />
            <Label htmlFor="geo" className="pt-2">PDF geotécnico (opcional)</Label>
            <Input id="geo" type="file" accept="application/pdf" ref={geoRef} data-testid="input-geo" />
            <Label htmlFor="pid" className="pt-2">project_id (opcional)</Label>
            <Input
              id="pid"
              placeholder="ex: moradia-martins"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
              data-testid="input-pid"
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="brief">brief.json</Label>
            <Textarea
              id="brief"
              rows={14}
              className="font-mono text-xs"
              value={briefJson}
              onChange={(e) => setBriefJson(e.target.value)}
              data-testid="input-brief"
            />
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Button
            onClick={runPipeline}
            disabled={!canRun || running}
            data-testid="run-pipeline-btn"
          >
            {running ? (
              <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> A correr…</>
            ) : (
              <><Play className="w-4 h-4 mr-2" /> Correr pipeline</>
            )}
          </Button>
          <span className="text-xs text-slate-500">
            Rodapé: “pré-dimensionamento, a verificar e assinar pelo técnico responsável”.
          </span>
        </div>
      </section>

      {/* RUNS LIST + COSTS */}
      <section className="rounded-xl border bg-white p-5 space-y-3" data-testid="bet-agent-runs">
        <div className="flex items-center justify-between">
          <h2 className="font-semibold">Dossiers recentes</h2>
          {costs && (
            <div className="text-sm text-slate-600" data-testid="costs-summary">
              {costs.runs_count} dossiers · total €{Number(costs.total_eur).toFixed(2)}
              {costs.exceeded_count > 0 && (
                <span className="ml-2 text-red-700">({costs.exceeded_count} acima do limite)</span>
              )}
            </div>
          )}
        </div>
        {loadingRuns ? (
          <div className="flex items-center gap-2 text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" /> a carregar…
          </div>
        ) : runs.length === 0 ? (
          <div className="text-sm text-slate-500">Ainda não há dossiers processados.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-left text-slate-500 border-b">
                <tr>
                  <th className="py-2">ID</th>
                  <th>Projecto</th>
                  <th>Estado</th>
                  <th>Custo</th>
                  <th>Criado</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => (
                  <tr key={r.run_id} className="border-b last:border-0" data-testid={`row-run-${r.run_id}`}>
                    <td className="py-2 font-mono text-xs">{r.run_id.slice(0, 8)}</td>
                    <td>{r.project_id}</td>
                    <td>{statusBadge(r?.summary?.global_status)}</td>
                    <td>€{Number(r?.summary?.cost?.eur_total || 0).toFixed(2)}</td>
                    <td>{r.created_at?.slice(0, 19).replace("T", " ")}</td>
                    <td>
                      <Button size="sm" variant="outline" onClick={() => setSelected(r)}>
                        detalhe
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* DETAIL DIALOG */}
      <Dialog open={!!selected} onOpenChange={(o) => !o && setSelected(null)}>
        <DialogContent className="max-w-3xl max-h-[80vh] overflow-y-auto" data-testid="run-detail-dialog">
          <DialogHeader>
            <DialogTitle>Detalhe do dossier</DialogTitle>
            <DialogDescription>
              {selected?.summary?.footer}
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-4 text-sm">
              <div className="flex items-center gap-3">
                <span className="font-medium">Estado global:</span>
                {statusBadge(selected?.summary?.global_status)}
                <span className="text-slate-500">
                  Custo: €{Number(selected?.summary?.cost?.eur_total || 0).toFixed(4)}
                  {selected?.summary?.cost?.exceeded_limit && " (acima do limite)"}
                </span>
              </div>

              <div>
                <h3 className="font-semibold mb-1">Anomalias ({selected?.summary?.anomalies?.length || 0})</h3>
                {selected?.summary?.anomalies?.length ? (
                  <ul className="space-y-2">
                    {selected.summary.anomalies.map((a, idx) => (
                      <li
                        key={idx}
                        className="rounded border p-2 text-xs bg-slate-50"
                        data-testid={`anomaly-${a.code}`}
                      >
                        <div className="flex items-center gap-2">
                          <Badge className="uppercase">{a.severity}</Badge>
                          <span className="font-mono">{a.code}</span>
                          {a.source?.page && (
                            <span className="text-slate-500">pág. {a.source.page}</span>
                          )}
                        </div>
                        <div className="mt-1">{a.message_pt}</div>
                        {a.remediation && (
                          <div className="mt-1 text-slate-600">
                            <span className="font-medium">Remediação:</span> {a.remediation}
                          </div>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-slate-500">sem anomalias.</div>
                )}
              </div>

              <div>
                <h3 className="font-semibold mb-1">Entregáveis</h3>
                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div>
                    <div className="text-slate-500">Pedidos</div>
                    <div className="font-mono break-words">
                      {(selected?.summary?.requested_deliverables || []).join(", ") || "—"}
                    </div>
                  </div>
                  <div>
                    <div className="text-slate-500">Produzidos</div>
                    <div className="font-mono break-words">
                      {(selected?.summary?.produced_deliverables || []).join(", ") || "—"}
                    </div>
                  </div>
                </div>
              </div>

              <div>
                <h3 className="font-semibold mb-1">Hipóteses usadas</h3>
                <ul className="text-xs space-y-1">
                  {(selected?.summary?.hypotheses_used || []).map((h, i) => (
                    <li key={i}>
                      <span className="font-mono">{h.key}</span>: {h.value}{" "}
                      <Badge variant={h.user_imposed ? "default" : "secondary"}>
                        {h.user_imposed ? "utilizador" : "default"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </div>

              {selected?.pending_questions?.length > 0 && (
                <div>
                  <h3 className="font-semibold mb-1">Perguntas pendentes</h3>
                  <ul className="text-xs space-y-1">
                    {selected.pending_questions.map((q, i) => (
                      <li key={i}>• {q.question_pt} (pág. {q.page})</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
