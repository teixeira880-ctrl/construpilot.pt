import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { CheckCircle2, Clock, Receipt } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, eur, num } from "@/lib/api";

export const PcSituations = ({ planId }) => {
  const [data, setData] = useState(null);
  const [pct, setPct] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    api.get(`/takeoffs/${planId}/pc-study/situations`)
      .then(({ data: d }) => setData(d))
      .catch(() => {});
  }, [planId]);
  useEffect(load, [load]);

  if (!data) return null;
  const b = data.billing || {};
  const sits = data.situations || [];
  const paidPct = b.total_ttc > 0 ? Math.min(100, Math.round((100 * b.paid) / b.total_ttc)) : 0;

  const create = async (solde) => {
    if (!solde && !(parseFloat(pct) > 0)) return toast.error("Indique o avanço acumulado (%)");
    setBusy(true);
    try {
      const { data: r } = await api.post(`/takeoffs/${planId}/pc-study/situations`,
        solde ? { solde: true } : { pct_cumul: parseFloat(pct) });
      toast.success(`Fatura ${r.situation.invoice_no} de ${eur(r.situation.amount)} emitida`
        + (r.emailed ? " e enviada ao cliente" : " (nenhum email cliente — envie primeiro o estudo)"));
      setPct("");
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Faturação impossível"); }
    finally { setBusy(false); }
  };

  return (
    <section data-testid="pc-situations-section">
      <h3 className="text-sm font-semibold mb-1 flex items-center gap-1.5">
        <Receipt className="h-4 w-4 text-primary" /> Autos de medição & saldo
      </h3>
      <div className="rounded-sm border border-border p-2.5 space-y-2">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs">
          <div><p className="text-[10px] text-muted-foreground">Valor c/ IVA</p>
            <p className="font-bold num">{eur(b.total_ttc)}</p></div>
          <div><p className="text-[10px] text-muted-foreground">Faturado (sinal incluído)</p>
            <p className="font-bold num">{eur(b.invoiced)}</p></div>
          <div><p className="text-[10px] text-muted-foreground">Recebido</p>
            <p className="font-bold num text-emerald-600" data-testid="pc-situations-paid">{eur(b.paid)}</p></div>
          <div><p className="text-[10px] text-muted-foreground">Por receber</p>
            <p className="font-bold num text-primary">{eur(b.remaining_to_pay)}</p></div>
        </div>
        <div className="h-1.5 bg-muted rounded-full overflow-hidden">
          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${paidPct}%` }} />
        </div>

        {sits.length > 0 && (
          <div className="space-y-1">
            {sits.map((s) => (
              <div key={s.sit_id}
                   className="flex items-center justify-between gap-2 text-xs border border-border rounded-sm px-2 py-1.5"
                   data-testid={`pc-situation-${s.sit_no}`}>
                <span className="truncate">
                  <b>{s.is_final ? "Saldo final" : `Auto de medição n.º ${s.sit_no}`}</b>
                  {!s.is_final && ` — ${num(s.pct_cumul)} % acumulado`}
                  <span className="text-muted-foreground"> · {s.invoice_no}</span>
                </span>
                <span className="flex items-center gap-2 shrink-0">
                  <span className="num font-semibold">{eur(s.amount)}</span>
                  {s.paid ? (
                    <Badge className="rounded-sm gap-1 text-[10px] bg-emerald-500/15 text-emerald-600 border border-emerald-500/40 hover:bg-emerald-500/15"
                           data-testid={`pc-situation-${s.sit_no}-status`}>
                      <CheckCircle2 className="h-3 w-3" />
                      Paga a {new Date(s.paid_at).toLocaleDateString("fr-FR")}
                    </Badge>
                  ) : (
                    <Badge variant="outline" className="rounded-sm gap-1 text-[10px] text-amber-600 border-amber-500/40"
                           data-testid={`pc-situation-${s.sit_no}-status`}>
                      <Clock className="h-3 w-3" /> Aguardar pagamento
                    </Badge>
                  )}
                </span>
              </div>
            ))}
          </div>
        )}

        {b.remaining_to_invoice > 0 ? (
          <div className="flex flex-wrap items-end gap-2 pt-1">
            <div className="grid gap-1">
              <label className="text-[10px] text-muted-foreground">Progresso acumulado (%)</label>
              <Input type="number" min="1" max="99" value={pct}
                     onChange={(e) => setPct(e.target.value)} placeholder="ex : 60"
                     className="h-8 w-28 rounded-sm num text-xs"
                     data-testid="pc-situation-pct-input" />
            </div>
            <Button size="sm" onClick={() => create(false)} disabled={busy}
                    className="h-8 rounded-sm text-xs" data-testid="pc-situation-create-btn">
              {busy ? "…" : "Faturar o auto de medição"}
            </Button>
            <Button size="sm" variant="outline" onClick={() => create(true)} disabled={busy}
                    className="h-8 rounded-sm text-xs" data-testid="pc-situation-solde-btn">
              Faturar o saldo ({eur(b.remaining_to_invoice)})
            </Button>
          </div>
        ) : (
          <p className="text-xs text-emerald-600 font-semibold" data-testid="pc-situations-complete">
            ✓ 100 % do contrato faturado{b.remaining_to_pay <= 0.01 ? " e recebido — obra liquidada!" : " — a aguardar recebimento."}
          </p>
        )}
        <p className="text-[10px] text-muted-foreground">
          Cada fatura é enviada ao cliente com um link de pagamento online por cartão.
        </p>
      </div>
    </section>
  );
};
