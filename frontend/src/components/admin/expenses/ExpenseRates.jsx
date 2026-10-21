import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ConfirmProvider";
import { useExpenseCopy } from "./copy";

export const ExpenseRates = ({ rates, providers, onAdd, onSaved }) => {
  const { text, money } = useExpenseCopy();
  const confirm = useConfirm();
  const remove = async rate => {
    if (!await confirm({ title: text("removeConfirm"), confirmLabel: text("remove"), destructive: true })) return;
    try { await api.delete(`/admin/expenses/rates/${rate.rate_id}`); toast.success(text("removed")); onSaved(); } catch { toast.error(text("error")); }
  };
  return <section className="grid gap-5 min-w-0" data-testid="expense-rates-section">
    <div className="flex flex-wrap justify-between gap-3 items-start"><p className="text-sm text-muted-foreground max-w-xl" data-testid="expense-rates-note">{text("rateNote")}</p><Button variant="outline" onClick={onAdd} data-testid="expense-add-rate"><Plus size={16} />{text("addRate")}</Button></div>
    {!rates.length && <p className="text-sm py-5" data-testid="expense-rates-empty">{text("empty")}</p>}
    {rates.map(r => <div key={r.rate_id} className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] border-t pt-4 text-sm" data-testid={`expense-rate-row-${r.rate_id}`}><div className="break-words"><strong>{providers.find(p => p.provider === r.provider)?.name}</strong><p>{r.model || text("all")}</p><p className="num text-xs mt-1">{r.effective_from}</p><p className="text-xs text-muted-foreground break-all mt-1">{r.source_ref}</p></div><div className="num">{r.mode === "tokens" ? <><p>{text("inputPrice")}: {money(r.input_price, r.currency)}</p><p>{text("outputPrice")}: {money(r.output_price, r.currency)}</p></> : <p>{money(r.price, r.currency)} / {r.per_units} {text(r.unit)}</p>}</div><Button size="icon" variant="ghost" onClick={() => remove(r)} title={text("remove")} aria-label={text("remove")} data-testid={`expense-remove-rate-${r.rate_id}`}><Trash2 size={16} /></Button></div>)}
  </section>;
};