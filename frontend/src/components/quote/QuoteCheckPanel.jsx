import { useState, useEffect } from "react";
import { toast } from "sonner";
import { ShieldCheck, Loader2, AlertTriangle, AlertCircle, Info, Wrench, CheckCheck, XCircle, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";

const SEV = {
  error: { icon: AlertCircle, cls: "text-red-600 dark:text-red-400", bg: "bg-red-50 border-red-200 dark:bg-red-500/10 dark:border-red-500/30", label: "Bloqueante" },
  warning: { icon: AlertTriangle, cls: "text-amber-600 dark:text-amber-400", bg: "bg-amber-50 border-amber-200 dark:bg-amber-500/10 dark:border-amber-500/30", label: "A verificar" },
  info: { icon: Info, cls: "text-sky-600 dark:text-sky-400", bg: "bg-sky-50 border-sky-200 dark:bg-sky-500/10 dark:border-sky-500/30", label: "Information" },
};
const CAT_LABEL = {
  doublon: "Duplicado", coherence: "Coerência", marge: "Margem", tva: "IVA",
  metre: "Medição da obra", poste_manquant: "Artigo em falta", ambiguite: "Ambiguidade",
};

export function QuoteCheckPanel({ open, onOpenChange, buildPayload, onFocusLine, onApplyFix, docId }) {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [handled, setHandled] = useState({}); // key -> {status, reason}

  const run = async () => {
    setLoading(true);
    setResult(null);
    setHandled({});
    try {
      const { data } = await api.post("/documents/check", buildPayload());
      setResult(data);
      if (docId) {
        try {
          const { data: dis } = await api.get(`/documents/${docId}/check/dismissals`);
          const map = {};
          (dis.items || []).forEach((d) => { map[d.key] = { status: d.status, reason: d.reason }; });
          setHandled(map);
        } catch { /* pas de motifs persistés */ }
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Controlo indisponível");
    } finally { setLoading(false); }
  };

  // Ouverture / fermeture pilotée par le parent
  const onOpen = (v) => onOpenChange(v);

  // Lance le contrôle automatiquement à l'ouverture
  useEffect(() => {
    if (open) run();
    else { setResult(null); setHandled({}); }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const mark = (a, status, reason = "") => {
    setHandled((h) => ({ ...h, [a.key]: { status, reason } }));
    if (docId) api.post(`/documents/${docId}/check/dismissals`, { key: a.key, status, reason }).catch(() => {});
  };
  const restore = (a) => {
    setHandled((x) => { const n = { ...x }; delete n[a.key]; return n; });
    if (docId) api.delete(`/documents/${docId}/check/dismissals/${a.key}`).catch(() => {});
  };

  const applyFix = (a) => {
    if (!a.fix) return;
    if (a.fix.action === "set_vat") {
      onApplyFix?.({ type: "set_vat", indexes: a.line_indexes, rate: a.fix.rate });
      toast.success("IVA aplicado às linhas em causa");
      mark(a, "fixed");
    }
  };

  const dismissWithReason = (a) => {
    const reason = window.prompt("Motivo para afastar este alerta:", "");
    if (reason === null) return;
    mark(a, "dismissed", reason.trim());
  };

  const alerts = result?.alerts || [];
  const active = alerts.filter((a) => !handled[a.key]);
  const done = alerts.filter((a) => handled[a.key]);

  return (
    <Dialog open={open} onOpenChange={onOpen}>
      <DialogContent className="max-w-2xl" data-testid="quote-check-panel">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><ShieldCheck className="h-5 w-5 text-primary" /> Controlo do orçamento</DialogTitle>
          <DialogDescription>
            Verificações automáticas antes do envio. Cada alerta indica a sua causa e as linhas em causa. As dependências são pontos «a verificar» (um artigo pode ser global ou estar incluído noutro lado).
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            <Loader2 className="h-6 w-6 animate-spin mx-auto mb-2" /> A analisar o orçamento…
          </div>
        ) : !result ? (
          <div className="py-8 text-center">
            <Button onClick={run} className="rounded-sm gap-2" data-testid="quote-check-run"><ShieldCheck className="h-4 w-4" /> Lançar o controlo</Button>
          </div>
        ) : (
          <div className="grid gap-3 max-h-[60vh] overflow-y-auto pr-1">
            <div className="flex items-center gap-3 rounded-sm bg-secondary/30 px-3 py-2 text-sm" data-testid="quote-check-summary">
              <span className="font-medium">{result.checked_lines} linha(s) controlada(s)</span>
              <span className="text-red-600">{result.counts.error} bloqueante(s)</span>
              <span className="text-amber-600">{result.counts.warning} a verificar</span>
              <span className="text-sky-600">{result.counts.info} info</span>
              {result.ai_used && <span className="ml-auto text-[10px] uppercase tracking-wide text-primary">+ analyse IA</span>}
            </div>

            {alerts.length === 0 && (
              <div className="py-8 text-center space-y-1" data-testid="quote-check-clean">
                <CheckCheck className="h-8 w-8 mx-auto text-emerald-500" />
                <p className="font-display font-bold">Nenhuma anomalia detetada</p>
                <p className="text-sm text-muted-foreground">O orçamento parece coerente. Verifique ainda assim o conteúdo comercial.</p>
              </div>
            )}

            {active.map((a) => {
              const s = SEV[a.severity] || SEV.info;
              const Icon = s.icon;
              return (
                <div key={a.id} className={`rounded-sm border p-3 ${s.bg}`} data-testid={`quote-check-alert-${a.id}`}>
                  <div className="flex items-start gap-2">
                    <Icon className={`h-4 w-4 mt-0.5 shrink-0 ${s.cls}`} />
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold flex items-center gap-2 flex-wrap">
                        {a.title}
                        <span className="text-[10px] uppercase tracking-wide rounded-sm bg-white/70 dark:bg-white/10 border px-1.5 py-0.5 text-slate-600 dark:text-slate-300">{CAT_LABEL[a.category] || a.category}</span>
                        {a.source === "ai" && <span className="text-[10px] uppercase tracking-wide text-primary">IA</span>}
                      </p>
                      <p className="text-sm text-slate-700 dark:text-slate-200 mt-0.5">{a.message}</p>
                      {a.data_used && <p className="text-[10px] text-slate-500 dark:text-slate-400 mt-1">Dado: {a.data_used}</p>}
                      <div className="flex flex-wrap gap-1.5 mt-2">
                        {a.line_indexes.map((li) => (
                          <button key={li} type="button" onClick={() => { onFocusLine?.(li); onOpenChange(false); }}
                                  className="inline-flex items-center gap-0.5 text-xs rounded-sm border bg-white dark:bg-white/10 text-slate-700 dark:text-slate-100 px-2 py-0.5 hover:bg-primary/5"
                                  data-testid={`quote-check-goto-${a.id}-${li}`}>
                            Linha {li + 1} <ChevronRight className="h-3 w-3" />
                          </button>
                        ))}
                      </div>
                      <div className="flex flex-wrap gap-2 mt-2">
                        {a.fix && (
                          <Button size="sm" className="h-7 rounded-sm gap-1 text-xs" onClick={() => applyFix(a)} data-testid={`quote-check-fix-${a.id}`}>
                            <Wrench className="h-3.5 w-3.5" /> Corrigir
                          </Button>
                        )}
                        <Button size="sm" variant="outline" className="h-7 rounded-sm gap-1 text-xs" onClick={() => mark(a, "elsewhere")} data-testid={`quote-check-elsewhere-${a.id}`}>
                          Incluído noutro lado
                        </Button>
                        <Button size="sm" variant="ghost" className="h-7 rounded-sm gap-1 text-xs text-muted-foreground" onClick={() => dismissWithReason(a)} data-testid={`quote-check-dismiss-${a.id}`}>
                          <XCircle className="h-3.5 w-3.5" /> Afastar com motivo
                        </Button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}

            {done.length > 0 && (
              <div className="border-t pt-2 mt-1">
                <p className="text-[10px] uppercase tracking-wide text-muted-foreground mb-1">Tratadas ({done.length})</p>
                {done.map((a) => {
                  const h = handled[a.key];
                  const label = h.status === "fixed" ? "Corrigido" : h.status === "elsewhere" ? "Incluído noutro lado" : `Afastado${h.reason ? " — " + h.reason : ""}`;
                  return (
                    <div key={a.id} className="flex items-center gap-2 text-xs text-muted-foreground py-1" data-testid={`quote-check-handled-${a.id}`}>
                      <CheckCheck className="h-3.5 w-3.5 text-emerald-500 shrink-0" />
                      <span className="line-through truncate">{a.title}</span>
                      <span className="ml-auto shrink-0">{label}</span>
                      <button type="button" onClick={() => restore(a)} className="underline shrink-0">repor</button>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
