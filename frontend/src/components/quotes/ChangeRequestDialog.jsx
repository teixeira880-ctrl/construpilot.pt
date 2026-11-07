import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api, eur2 } from "@/lib/api";
import { newRequestId } from "@/lib/workProfile";

const EMPTY_LINE = { designation: "", unit: "u", qty: "", unit_price_ht: "" };

/** Trabalho adicional pedido pelo cliente: novo rascunho ligado ao orçamento, que nunca é alterado. */
export function ChangeRequestDialog({ quote, onOpenChange }) {
  const nav = useNavigate();
  const [description, setDescription] = useState("");
  const [lines, setLines] = useState([{ ...EMPTY_LINE }]);
  const [delay, setDelay] = useState("");
  const [busy, setBusy] = useState(false);
  const [history, setHistory] = useState([]);
  const [requestId] = useState(newRequestId());

  useEffect(() => { if (quote) api.get(`/documents/${quote.doc_id}/change-requests`).then(({ data }) => setHistory(data || [])).catch(() => {}); }, [quote]);

  const extra = useMemo(() => lines.reduce((s, l) => s + (Number(l.qty) || 0) * (Number(l.unit_price_ht) || 0), 0), [lines]);
  const base = Number(quote?.totals?.ht || 0);
  const setLine = (i, patch) => setLines(ls => ls.map((l, k) => (k === i ? { ...l, ...patch } : l)));

  const submit = async () => {
    setBusy(true);
    try {
      const num = v => (v === "" ? null : Number(v));
      const { data } = await api.post(`/documents/${quote.doc_id}/change-request`, {
        request_id: requestId, description, delay_days: delay === "" ? null : Number(delay),
        lines: lines.filter(l => l.designation.trim()).map(l => ({ ...l, qty: num(l.qty), unit_price_ht: num(l.unit_price_ht) })),
      });
      toast.success("Proposta de trabalho adicional criada em rascunho. O orçamento original não foi alterado.");
      onOpenChange(false);
      nav(`/devis-editeur/${data.new_doc_id}`);
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível criar a proposta."); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={!!quote} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] overflow-y-auto sm:max-w-2xl" data-testid="change-request-dialog">
        <DialogHeader>
          <DialogTitle>Trabalho adicional</DialogTitle>
          <DialogDescription>O cliente pediu algo a mais? Cria-se uma proposta separada. O orçamento «{quote?.title || quote?.number}» fica exatamente como está.</DialogDescription>
        </DialogHeader>
        <label className="block text-sm font-medium">O que pediu o cliente?
          <textarea rows={2} className="mt-1 w-full rounded-xl border bg-background p-2" value={description} onChange={e => setDescription(e.target.value)} placeholder="Ex.: pintar também o corredor" data-testid="cr-description" /></label>
        <div className="space-y-2">
          {lines.map((l, i) => <div key={i} className="grid grid-cols-[1fr_auto] gap-2 rounded-xl border p-2 sm:grid-cols-[3fr_70px_1fr_1fr_auto]">
            <input aria-label="Trabalho" className="col-span-2 h-11 rounded-lg border bg-background px-2 sm:col-span-1" placeholder="Trabalho" value={l.designation} onChange={e => setLine(i, { designation: e.target.value })} data-testid={`cr-line-${i}-designation`} />
            <input aria-label="Unidade" className="h-11 rounded-lg border bg-background px-2" value={l.unit} onChange={e => setLine(i, { unit: e.target.value })} />
            <input aria-label="Quantidade" type="number" min="0" step="any" inputMode="decimal" className="h-11 rounded-lg border bg-background px-2" placeholder="Qtd." value={l.qty} onChange={e => setLine(i, { qty: e.target.value })} data-testid={`cr-line-${i}-qty`} />
            <input aria-label="Preço por unidade sem IVA" type="number" min="0" step="any" inputMode="decimal" className="h-11 rounded-lg border bg-background px-2" placeholder="€/u s/ IVA" value={l.unit_price_ht} onChange={e => setLine(i, { unit_price_ht: e.target.value })} data-testid={`cr-line-${i}-price`} />
            <Button variant="ghost" size="icon" aria-label="Remover" onClick={() => setLines(ls => ls.filter((_, k) => k !== i))}><Trash2 className="h-4 w-4" /></Button>
          </div>)}
          <Button variant="outline" size="sm" onClick={() => setLines(ls => [...ls, { ...EMPTY_LINE }])}><Plus className="mr-1 h-4 w-4" />Linha</Button>
        </div>
        <label className="block text-sm font-medium">Dias de trabalho a mais (opcional)
          <input type="number" min="0" className="mt-1 h-11 w-32 rounded-xl border bg-background px-2" value={delay} onChange={e => setDelay(e.target.value)} data-testid="cr-delay" />
          <span className="mt-1 block text-xs font-normal text-muted-foreground">Se não indicar, o impacto no prazo fica «por indicar» — nunca é estimado automaticamente.</span></label>
        <div className="rounded-xl bg-muted/60 p-3 text-sm" data-testid="cr-impact">
          <p>Orçamento atual: <strong>{eur2(base)}</strong> s/ IVA</p>
          <p>Trabalho adicional: <strong>+ {eur2(extra)}</strong></p>
          <p>Total com o adicional: <strong>{eur2(base + extra)}</strong> s/ IVA{delay !== "" && ` · prazo +${delay} dia(s)`}</p>
        </div>
        {history.length > 0 && <div className="text-xs text-muted-foreground"><p className="font-semibold">Pedidos anteriores neste orçamento</p>
          <ul className="list-disc pl-4">{history.map(h => <li key={h.cr_id}>{h.created_at?.slice(0, 10)} — {h.description} (+{eur2(h.impact?.extra_ht)})</li>)}</ul></div>}
        <div className="flex justify-end gap-2 border-t pt-3">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancelar</Button>
          <Button onClick={submit} disabled={busy || description.trim().length < 3 || !lines.some(l => l.designation.trim())} data-testid="cr-submit">{busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}Criar proposta</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
