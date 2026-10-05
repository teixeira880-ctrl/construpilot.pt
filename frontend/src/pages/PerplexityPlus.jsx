/**
 * Perplexity Plus — 4 modos: Chat SSE / Comparar / Normas / Materiais
 */
import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Textarea } from "../components/ui/textarea";
import { Badge } from "../components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
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

const PRESETS = [
  { code: "LNEC", label: "LNEC (normas construtivas)" },
  { code: "DRE", label: "Diário da República (legislação)" },
  { code: "APA", label: "APA (ambiente)" },
  { code: "ADENE", label: "ADENE (energia)" },
  { code: "IHRU", label: "IHRU (habitação / reabilitação)" },
];

// =========================================================================
// Chat SSE
// =========================================================================
function ChatPane({ headers }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [preset, setPreset] = useState("LNEC");
  const [streaming, setStreaming] = useState(false);
  const [currentCitations, setCurrentCitations] = useState([]);
  const scrollRef = useRef(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const send = async () => {
    const txt = input.trim();
    if (!txt || streaming) return;
    setStreaming(true);
    setCurrentCitations([]);
    const userMsg = { role: "user", content: txt };
    const asstIdx = messages.length + 1;
    setMessages((prev) => [...prev, userMsg, { role: "assistant", content: "" }]);
    setInput("");

    try {
      const r = await fetch(`${API}/perplexity-plus/chat`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ message: txt, preset, history: messages }),
      });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.detail || "Chat falhou");
      }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let collected = "";
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          if (!part.startsWith("data:")) continue;
          const payload = part.slice(5).trim();
          if (payload === "[DONE]") continue;
          try {
            const d = JSON.parse(payload);
            if (d.delta) {
              collected += d.delta;
              setMessages((prev) => {
                const next = [...prev];
                next[asstIdx] = { role: "assistant", content: collected };
                return next;
              });
            }
            if (d.citations) setCurrentCitations(d.citations);
            if (d.error) throw new Error(d.error);
          } catch (e) {
            // ignora parse errors parciais
          }
        }
      }
    } catch (e) {
      toast.error(e.message);
    } finally {
      setStreaming(false);
    }
  };

  return (
    <div className="space-y-4" data-testid="pplx-chat-pane">
      <div className="flex items-center gap-3">
        <label className="text-sm text-slate-600">Preset:</label>
        <Select value={preset} onValueChange={setPreset}>
          <SelectTrigger className="w-[280px]" data-testid="pplx-chat-preset">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRESETS.map((p) => (
              <SelectItem key={p.code} value={p.code}>
                {p.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div
        ref={scrollRef}
        className="h-[400px] overflow-y-auto rounded border border-slate-200 bg-white p-4 space-y-3"
        data-testid="pplx-chat-messages"
      >
        {messages.length === 0 && (
          <p className="text-sm text-slate-400">
            Faça uma pergunta técnica — ex: "Qual a espessura mínima de isolamento
            de parede exterior em zona climática I2?"
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${
              m.role === "user"
                ? "ml-auto bg-emerald-600 text-white"
                : "bg-slate-100 text-slate-900"
            }`}
          >
            {m.content || (streaming && i === messages.length - 1 ? "…" : "")}
          </div>
        ))}
      </div>

      {currentCitations.length > 0 && (
        <div className="flex flex-wrap gap-2 text-xs">
          <span className="text-slate-500">Fontes:</span>
          {currentCitations.map((c, i) => (
            <a
              key={i}
              href={c.url}
              target="_blank"
              rel="noreferrer"
              className="text-sky-700 underline"
            >
              [{i + 1}] {c.title || c.url?.slice(0, 40)}
            </a>
          ))}
        </div>
      )}

      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !streaming && send()}
          placeholder="Pergunta..."
          data-testid="pplx-chat-input"
          disabled={streaming}
        />
        <Button onClick={send} disabled={streaming} data-testid="pplx-chat-send">
          {streaming ? "..." : "Enviar"}
        </Button>
      </div>
    </div>
  );
}

// =========================================================================
// Compare
// =========================================================================
function ComparePane({ headers }) {
  const [items, setItems] = useState(["", ""]);
  const [criteria, setCriteria] = useState([""]);
  const [context, setContext] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    const its = items.map((s) => s.trim()).filter(Boolean);
    const crit = criteria.map((s) => s.trim()).filter(Boolean);
    if (its.length < 2 || crit.length < 1) {
      toast.error("Mínimo 2 items e 1 critério.");
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(`${API}/perplexity-plus/compare`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ items: its, criteria: crit, context: context || null }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Falhou");
      setResult(d);
      toast.success(`Comparação concluída (cache ${d.cache}).`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const parsed = result?.parsed;

  return (
    <div className="space-y-4" data-testid="pplx-compare-pane">
      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="text-sm font-medium">Items a comparar</label>
          {items.map((v, i) => (
            <div key={i} className="flex gap-2 mt-1">
              <Input
                value={v}
                onChange={(e) =>
                  setItems((prev) => prev.map((x, j) => (i === j ? e.target.value : x)))
                }
                placeholder={`Item ${i + 1} (ex: betão C25/30)`}
                data-testid={`pplx-compare-item-${i}`}
              />
              {items.length > 2 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setItems((prev) => prev.filter((_, j) => j !== i))}
                >
                  ✕
                </Button>
              )}
            </div>
          ))}
          {items.length < 6 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setItems((prev) => [...prev, ""])}
              className="mt-1"
              data-testid="pplx-compare-add-item"
            >
              + Adicionar item
            </Button>
          )}
        </div>
        <div>
          <label className="text-sm font-medium">Critérios</label>
          {criteria.map((v, i) => (
            <div key={i} className="flex gap-2 mt-1">
              <Input
                value={v}
                onChange={(e) =>
                  setCriteria((prev) =>
                    prev.map((x, j) => (i === j ? e.target.value : x))
                  )
                }
                placeholder={`Critério ${i + 1} (ex: durabilidade)`}
                data-testid={`pplx-compare-criterion-${i}`}
              />
              {criteria.length > 1 && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setCriteria((prev) => prev.filter((_, j) => j !== i))}
                >
                  ✕
                </Button>
              )}
            </div>
          ))}
          {criteria.length < 6 && (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setCriteria((prev) => [...prev, ""])}
              className="mt-1"
            >
              + Adicionar critério
            </Button>
          )}
        </div>
      </div>

      <Textarea
        value={context}
        onChange={(e) => setContext(e.target.value)}
        placeholder="Contexto (opcional) — tipo de obra, exigências..."
        rows={2}
      />

      <Button onClick={run} disabled={loading} data-testid="pplx-compare-run">
        {loading ? "A comparar..." : "Comparar"}
      </Button>

      {parsed && (
        <Card data-testid="pplx-compare-result">
          <CardHeader>
            <CardTitle className="text-base">Resultado</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {parsed.scores && parsed.items && parsed.criteria && (
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-slate-200">
                    <th className="text-left py-1 font-medium">Item</th>
                    {parsed.criteria.map((c, i) => (
                      <th key={i} className="text-center py-1 font-medium">
                        {c}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {parsed.items.map((it, i) => (
                    <tr key={i} className="border-b border-slate-100">
                      <td className="py-1">{it}</td>
                      {(parsed.scores[i] || []).map((s, j) => (
                        <td key={j} className="text-center py-1 tabular-nums">
                          {s}/5
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {parsed.recomendado && (
              <div className="rounded border border-emerald-300 bg-emerald-50 p-3 text-sm">
                <span className="font-semibold">Recomendado:</span>{" "}
                {parsed.recomendado.item} — {parsed.recomendado.razao}
              </div>
            )}
            {parsed.pros_cons?.map((pc, i) => (
              <div key={i} className="text-sm">
                <div className="font-medium">{pc.item}</div>
                <div className="grid grid-cols-2 gap-3 text-xs mt-1">
                  <ul className="list-disc pl-4 text-emerald-700">
                    {pc.pros?.map((p, j) => <li key={j}>{p}</li>)}
                  </ul>
                  <ul className="list-disc pl-4 text-rose-700">
                    {pc.cons?.map((p, j) => <li key={j}>{p}</li>)}
                  </ul>
                </div>
              </div>
            ))}
            {result?.citations?.length > 0 && (
              <div className="flex flex-wrap gap-2 text-xs">
                {result.citations.map((c, i) => (
                  <a key={i} href={c.url} target="_blank" rel="noreferrer" className="text-sky-700 underline">
                    [{i + 1}] {c.title || c.url?.slice(0, 40)}
                  </a>
                ))}
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// =========================================================================
// Normas
// =========================================================================
function NormsPane({ headers }) {
  const [query, setQuery] = useState("");
  const [preset, setPreset] = useState("LNEC");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    if (query.trim().length < 3) {
      toast.error("Query demasiado curta.");
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(`${API}/perplexity-plus/norms`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ query: query.trim(), preset }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Falhou");
      setResult(d);
      toast.success(`Normas obtidas (cache ${d.cache}).`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const parsed = result?.parsed;

  return (
    <div className="space-y-4" data-testid="pplx-norms-pane">
      <div className="flex gap-3">
        <Select value={preset} onValueChange={setPreset}>
          <SelectTrigger className="w-[260px]" data-testid="pplx-norms-preset">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PRESETS.filter((p) => ["LNEC", "DRE", "APA", "ADENE"].includes(p.code)).map(
              (p) => (
                <SelectItem key={p.code} value={p.code}>
                  {p.label}
                </SelectItem>
              )
            )}
          </SelectContent>
        </Select>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="ex: espessura mínima de isolamento em parede exterior zona I2"
          data-testid="pplx-norms-query"
        />
        <Button onClick={run} disabled={loading} data-testid="pplx-norms-run">
          {loading ? "..." : "Consultar"}
        </Button>
      </div>

      {parsed && (
        <div className="space-y-4" data-testid="pplx-norms-result">
          {parsed.resposta_textual && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Resposta</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm whitespace-pre-wrap">{parsed.resposta_textual}</p>
              </CardContent>
            </Card>
          )}
          {parsed.normas?.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Normas aplicáveis</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {parsed.normas.map((n, i) => (
                  <div key={i} className="rounded border border-slate-200 p-3 text-sm">
                    <div className="font-medium">{n.referencia}</div>
                    <div className="text-slate-700">{n.titulo}</div>
                    {n.artigo && (
                      <div className="text-xs text-slate-500 mt-1">
                        Artigo: {n.artigo}
                      </div>
                    )}
                    <p className="mt-2">{n.resumo}</p>
                    {n.url && (
                      <a
                        href={n.url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-sky-700 underline text-xs"
                      >
                        {n.fonte || "Fonte oficial"}
                      </a>
                    )}
                  </div>
                ))}
              </CardContent>
            </Card>
          )}
          {parsed.pontos_atencao?.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Pontos de atenção</CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="list-disc pl-5 text-sm space-y-1">
                  {parsed.pontos_atencao.map((p, i) => <li key={i}>{p}</li>)}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}

// =========================================================================
// Materials Watch
// =========================================================================
function MaterialsPane({ headers }) {
  const [materials, setMaterials] = useState([""]);
  const [region, setRegion] = useState("Portugal continental");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    const mats = materials.map((s) => s.trim()).filter(Boolean);
    if (mats.length < 1) {
      toast.error("Indique pelo menos um material.");
      return;
    }
    setLoading(true);
    try {
      const r = await fetch(`${API}/perplexity-plus/materials-watch`, {
        method: "POST",
        headers: { ...headers, "Content-Type": "application/json" },
        body: JSON.stringify({ materials: mats, region }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || "Falhou");
      setResult(d);
      toast.success(`Preços obtidos (cache ${d.cache}).`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setLoading(false);
    }
  };

  const parsed = result?.parsed;

  return (
    <div className="space-y-4" data-testid="pplx-materials-pane">
      <div className="flex gap-3">
        <Input
          value={region}
          onChange={(e) => setRegion(e.target.value)}
          placeholder="Região (ex: Lisboa, Porto, Madeira)"
          className="w-[220px]"
          data-testid="pplx-materials-region"
        />
      </div>
      <div className="space-y-2">
        {materials.map((v, i) => (
          <div key={i} className="flex gap-2">
            <Input
              value={v}
              onChange={(e) =>
                setMaterials((prev) =>
                  prev.map((x, j) => (i === j ? e.target.value : x))
                )
              }
              placeholder={`Material ${i + 1} (ex: betão C25/30)`}
              data-testid={`pplx-materials-input-${i}`}
            />
            {materials.length > 1 && (
              <Button
                variant="outline"
                size="sm"
                onClick={() =>
                  setMaterials((prev) => prev.filter((_, j) => j !== i))
                }
              >
                ✕
              </Button>
            )}
          </div>
        ))}
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setMaterials((prev) => [...prev, ""])}
          data-testid="pplx-materials-add"
        >
          + Adicionar material
        </Button>
      </div>
      <Button onClick={run} disabled={loading} data-testid="pplx-materials-run">
        {loading ? "A consultar..." : "Consultar preços"}
      </Button>

      {parsed?.materiais?.length > 0 && (
        <Card data-testid="pplx-materials-result">
          <CardHeader>
            <CardTitle className="text-base">Preços e tendências</CardTitle>
          </CardHeader>
          <CardContent>
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200">
                  <th className="text-left py-1 font-medium">Material</th>
                  <th className="text-right py-1 font-medium">Preço (€/un)</th>
                  <th className="text-center py-1 font-medium">Un</th>
                  <th className="text-center py-1 font-medium">Var. tri.</th>
                  <th className="text-center py-1 font-medium">Tendência</th>
                  <th className="text-left py-1 font-medium">Fonte</th>
                </tr>
              </thead>
              <tbody>
                {parsed.materiais.map((m, i) => (
                  <tr key={i} className="border-b border-slate-100">
                    <td className="py-1">{m.nome}</td>
                    <td className="py-1 text-right tabular-nums">
                      {m.preco_estimado_eur?.toFixed?.(2) ?? "-"}
                    </td>
                    <td className="py-1 text-center">{m.unidade}</td>
                    <td className="py-1 text-center tabular-nums">
                      {m.variacao_trimestral_pct?.toFixed?.(1) ?? "-"}%
                    </td>
                    <td className="py-1 text-center">
                      <Badge
                        variant={
                          m.tendencia === "subida"
                            ? "destructive"
                            : m.tendencia === "descida"
                            ? "default"
                            : "secondary"
                        }
                      >
                        {m.tendencia}
                      </Badge>
                    </td>
                    <td className="py-1 text-xs text-slate-600">
                      {m.fonte} {m.data_fonte ? `(${m.data_fonte})` : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {parsed.aviso && (
              <p className="mt-3 text-xs text-slate-500 italic">{parsed.aviso}</p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

// =========================================================================
// Página principal
// =========================================================================
export default function PerplexityPlus() {
  const headers = useAuthHeaders();
  const [cacheStats, setCacheStats] = useState(null);

  const fetchStats = useCallback(async () => {
    try {
      const r = await fetch(`${API}/perplexity-plus/cache-stats`, { headers });
      if (r.ok) setCacheStats(await r.json());
    } catch {}
  }, [headers]);

  useEffect(() => {
    fetchStats();
  }, [fetchStats]);

  return (
    <div className="min-h-screen bg-slate-50 py-10 px-4" data-testid="pplx-page">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <h1 className="text-4xl sm:text-5xl font-bold tracking-tight text-slate-900">
            Perplexity Plus
          </h1>
          <p className="text-base text-slate-600 mt-2 max-w-2xl">
            Pesquisa inteligente especializada em construção portuguesa — DRE,
            LNEC, APA, ADENE, IHRU. Normas, legislação, materiais e comparações
            técnicas em tempo real.
          </p>
          {cacheStats && (
            <p className="text-xs text-slate-500 mt-2" data-testid="pplx-cache-info">
              Cache ativo: {cacheStats.items} entradas · TTL {cacheStats.ttl_hours}h
            </p>
          )}
        </header>

        <Tabs defaultValue="chat" className="w-full">
          <TabsList className="grid w-full grid-cols-4" data-testid="pplx-tabs">
            <TabsTrigger value="chat" data-testid="pplx-tab-chat">
              Chat
            </TabsTrigger>
            <TabsTrigger value="compare" data-testid="pplx-tab-compare">
              Comparar
            </TabsTrigger>
            <TabsTrigger value="norms" data-testid="pplx-tab-norms">
              Normas
            </TabsTrigger>
            <TabsTrigger value="materials" data-testid="pplx-tab-materials">
              Materiais
            </TabsTrigger>
          </TabsList>
          <TabsContent value="chat" className="mt-6">
            <ChatPane headers={headers} />
          </TabsContent>
          <TabsContent value="compare" className="mt-6">
            <ComparePane headers={headers} />
          </TabsContent>
          <TabsContent value="norms" className="mt-6">
            <NormsPane headers={headers} />
          </TabsContent>
          <TabsContent value="materials" className="mt-6">
            <MaterialsPane headers={headers} />
          </TabsContent>
        </Tabs>
      </div>
    </div>
  );
}
