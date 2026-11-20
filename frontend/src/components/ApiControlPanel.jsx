import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, RefreshCw, ExternalLink, Lock, AlertTriangle, Plug } from "lucide-react";
import { api, num } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Progress } from "@/components/ui/progress";
import { SectionTitle } from "@/components/Bits";

function Credit({ c }) {
  if (!c) return null;
  if (c.kind === "none" || c.kind === "error") {
    return (
      <p className={`text-xs ${c.kind === "error" ? "text-amber-700" : "text-muted-foreground"}`} data-testid="api-credit-msg">
        {c.message}
      </p>
    );
  }
  const pct = c.limit ? Math.min(100, Math.round(((c.used ?? (c.limit - (c.remaining || 0))) / c.limit) * 100)) : null;
  return (
    <div className="space-y-1" data-testid="api-credit">
      {c.kind === "spend" ? (
        <p className="text-sm"><strong className="num">{num(c.used, 2)}</strong> <span className="text-muted-foreground">{c.unit}</span></p>
      ) : (
        <p className="text-sm">
          Restante: <strong className="num">{c.remaining == null ? "—" : num(c.remaining, 2)}</strong>
          {c.limit ? <span className="text-muted-foreground"> / {num(c.limit, 2)}</span> : null}{" "}
          <span className="text-muted-foreground">{c.unit}</span>
        </p>
      )}
      {pct != null && <Progress value={pct} className={`h-1.5 ${pct >= 80 ? "[&>div]:bg-amber-500" : ""}`} />}
      {c.resets_at && <p className="text-[11px] text-muted-foreground">Renova em {new Date(c.resets_at).toLocaleDateString("pt-PT")}</p>}
      {c.packs?.length > 0 && (
        <p className="text-[11px] text-muted-foreground">
          {c.packs.map((p) => `${p.name}: ${num(p.remaining)}/${num(p.total)}`).join(" · ")}
        </p>
      )}
    </div>
  );
}

function Row({ p, onChange }) {
  const [busy, setBusy] = useState("");
  const [limit, setLimit] = useState(p.limit?.monthly_limit_eur ?? "");

  const toggle = async (enabled) => {
    if (!enabled && p.critical && !window.confirm(`Desligar ${p.label}? ${p.uses} deixa de funcionar.`)) return;
    setBusy("toggle");
    try {
      const { data } = await api.put(`/admin/apis/${p.id}`, { enabled });
      onChange(data);
      toast.success(`${p.label}: ${enabled ? "ligada" : "desligada"}`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Operação impossível");
    } finally {
      setBusy("");
    }
  };

  const refresh = async () => {
    setBusy("credit");
    try {
      const { data } = await api.get(`/admin/apis/${p.id}/credit`);
      onChange({ ...p, credit: data });
    } catch {
      toast.error("Saldo indisponível");
    } finally {
      setBusy("");
    }
  };

  const saveLimit = async () => {
    setBusy("limit");
    try {
      const { data } = await api.put(`/admin/apis/${p.id}/limit`, { monthly_limit_eur: limit === "" ? null : Number(limit) });
      onChange(data);
      toast.success("Limite guardado");
    } catch {
      toast.error("Impossível guardar o limite");
    } finally {
      setBusy("");
    }
  };

  return (
    <div className={`surface rounded-sm border p-4 grid md:grid-cols-[1.3fr_1fr_auto] gap-4 items-start ${p.enabled ? "border-border" : "border-amber-500/40 bg-amber-500/5"}`}
         data-testid={`api-row-${p.id}`}>
      <div className="min-w-0">
        <p className="font-semibold flex items-center gap-2">
          {p.label}
          {p.locked && <Lock className="h-3.5 w-3.5 text-muted-foreground" title="Não pode ser desligada" />}
          {!p.configured && <span className="text-[10px] uppercase tracking-widest text-muted-foreground">sem chave</span>}
        </p>
        <p className="text-xs text-muted-foreground mt-1">{p.uses}</p>
        {p.calls_month != null && (
          <p className="text-[11px] text-muted-foreground mt-1">Chamadas IA este mês: <strong className="num">{num(p.calls_month)}</strong></p>
        )}
        {p.breaker && (
          <p className="text-[11px] text-amber-700 mt-1 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" /> Desligada automaticamente (crédito/chave): {p.breaker.reason}
          </p>
        )}
      </div>
      <div className="space-y-2">
        <Credit c={p.credit} />
        <div className="flex items-center gap-2">
          <Input type="number" min="0" value={limit} onChange={(e) => setLimit(e.target.value)} placeholder="Limite €/mês"
                 className="h-8 w-28 rounded-sm num text-xs" data-testid={`api-limit-${p.id}`} />
          <Button size="sm" variant="outline" className="h-8 rounded-sm text-xs" onClick={saveLimit} disabled={!!busy}>
            {busy === "limit" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Guardar"}
          </Button>
        </div>
      </div>
      <div className="flex md:flex-col items-center md:items-end gap-3">
        <div className="flex items-center gap-2">
          <span className={`text-xs font-semibold ${p.enabled ? "text-primary" : "text-amber-700"}`}>{p.enabled ? "Ligada" : "Desligada"}</span>
          {busy === "toggle" ? <Loader2 className="h-4 w-4 animate-spin" /> : (
            <Switch checked={p.enabled} disabled={p.locked || !!busy} onCheckedChange={toggle} data-testid={`api-toggle-${p.id}`} />
          )}
        </div>
        <div className="flex items-center gap-1">
          <Button size="icon" variant="ghost" className="h-7 w-7" onClick={refresh} disabled={!!busy || !p.configured} title="Atualizar saldo">
            {busy === "credit" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RefreshCw className="h-3.5 w-3.5" />}
          </Button>
          {p.console && (
            <a href={p.console} target="_blank" rel="noreferrer" className="inline-flex h-7 w-7 items-center justify-center rounded-sm hover:bg-muted"
               title="Abrir a consola / faturação">
              <ExternalLink className="h-3.5 w-3.5" />
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

export default function ApiControlPanel() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async (fresh = false) => {
    setLoading(true);
    try {
      const { data } = await api.get(`/admin/apis${fresh ? "?fresh=true" : ""}`);
      setData(data);
    } catch {
      toast.error("Impossível carregar as API");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);

  const update = (row) => setData((d) => ({ ...d, providers: d.providers.map((p) => (p.id === row.id ? { ...p, ...row } : p)) }));

  const cats = data ? [...new Set(data.providers.map((p) => p.category))] : [];
  const on = data ? data.providers.filter((p) => p.enabled && p.configured).length : 0;

  return (
    <div className="space-y-4" data-testid="admin-api-control">
      <SectionTitle over="Controlo central" title="Todas as IA e API do ConstruPilot">
        Ligue ou desligue cada IA / API e veja o crédito de cada uma. Desligar não apaga a chave (fica nos Secrets): a função
        passa para o fornecedor seguinte ou fica indisponível até religar. A alteração é imediata para todos os pedidos.
      </SectionTitle>
      <div className="flex items-center gap-3">
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={() => load(true)} disabled={loading} data-testid="api-refresh-all">
          {loading ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />} Atualizar todos os saldos
        </Button>
        {data && (
          <span className="text-xs text-muted-foreground flex items-center gap-1">
            <Plug className="h-3.5 w-3.5" /> {on} ativas de {data.providers.length}
          </span>
        )}
      </div>
      {!data ? (
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      ) : (
        cats.map((cat) => (
          <div key={cat} className="space-y-2">
            <p className="text-[11px] font-bold uppercase tracking-widest text-primary">{cat}</p>
            {data.providers.filter((p) => p.category === cat).map((p) => <Row key={p.id} p={p} onChange={update} />)}
          </div>
        ))
      )}
      {data?.log?.length > 0 && (
        <details className="text-xs text-muted-foreground">
          <summary className="cursor-pointer">Histórico de alterações</summary>
          <ul className="mt-2 space-y-1">
            {data.log.map((l, i) => (
              <li key={i}>{new Date(l.at).toLocaleString("pt-PT")} — {l.provider} {l.enabled ? "ligada" : "desligada"} {l.by ? `por ${l.by}` : ""}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
