import { ChevronLeft, ChevronRight, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useConfirm } from "@/components/ConfirmProvider";
import { ExpenseSelect, EvidenceBadge } from "./Fields";
import { useExpenseCopy } from "./copy";

export const ExpenseLedger = ({ data, providers, evidence, setEvidence, setPage, onEdit, onSaved }) => {
  const { text, money, locale } = useExpenseCopy();
  const confirm = useConfirm();
  const remove = async row => {
    if (!await confirm({ title: text("removeConfirm"), confirmLabel: text("remove"), destructive: true })) return;
    try { await api.delete(`/admin/expenses/entries/${row.entry_id}`, { params: { version: row.version } }); toast.success(text("removed")); onSaved(); } catch { toast.error(text("error")); }
  };
  return <div className="min-w-0 grid gap-4">
    <div className="max-w-xs"><ExpenseSelect name="expense-filter-status" label={text("evidence")} value={evidence} onChange={setEvidence} options={[{ value: "", label: text("all") }, ...["confirmed", "estimated", "unavailable", "reconciled"].map(v => ({ value: v, label: text(v) }))]} /></div>
    <div data-testid="expense-ledger-table" className="divide-y border-y min-w-0">
      {!data.items.length && <p className="py-8 text-sm text-muted-foreground" data-testid="expense-ledger-empty">{text("empty")}</p>}
      {data.items.map(row => <article key={row.entry_id} className="py-5 grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] text-sm" data-testid={`expense-row-${row.entry_id}`}>
        <div className="min-w-0"><p className="font-semibold">{providers.find(p => p.provider === row.provider)?.name || row.provider}</p><p className="break-words mt-1">{row.feature} {row.is_test && <strong data-testid={`expense-test-${row.entry_id}`}>· TEST</strong>}</p><p className="num text-xs text-muted-foreground mt-1">{new Date(row.occurred_at).toLocaleString(locale, { timeZone: "UTC" })} UTC</p><p className="text-xs break-all mt-2" data-testid={`expense-reference-${row.entry_id}`}>{text("reference")}: {row.source_ref}</p><p className="text-xs text-muted-foreground">{text("source")}: {text(row.source_kind === "admin_confirmation" ? "confirmedSource" : row.source_kind === "provider_report" ? "providerSource" : "meter")}</p></div>
        <div className="min-w-0"><p data-testid={`expense-company-${row.entry_id}`}>{text("company")}: {row.company_name || row.company_id || text("unattributed")}</p><p className="text-xs text-muted-foreground mt-1 break-words">{text("user")}: {row.user_name || row.user_id || text("unattributed")}</p><p className="num text-xs break-all mt-2">{row.model}</p><dl className="text-xs mt-2 grid gap-1" data-testid={`expense-units-${row.entry_id}`}>{Object.entries(row.units).map(([k, v]) => <div key={k} className="flex flex-wrap gap-1"><dt>{text(k)}:</dt><dd className="num">{v.toLocaleString(locale)}</dd></div>)}</dl></div>
        <div><EvidenceBadge id={`expense-evidence-${row.entry_id}`} value={row.evidence} /><p className="num font-semibold mt-2" data-testid={`expense-eur-${row.entry_id}`}>{money(row.amount_eur)}</p>{row.currency && row.currency !== "EUR" && <p className="num text-xs mt-1" data-testid={`expense-native-${row.entry_id}`}>{money(row.amount, row.currency)}</p>}{row.rate_ref && <p className="text-xs text-muted-foreground mt-1 break-all" data-testid={`expense-rate-${row.entry_id}`}>{text("rateRef")}: {row.rate_ref}</p>}</div>
        <div className="flex gap-1"><Button size="icon" variant="outline" title={text("edit")} aria-label={text("edit")} data-testid={`expense-confirm-modal-btn-${row.entry_id}`} disabled={row.evidence === "reconciled"} onClick={() => onEdit(row)}><Pencil size={15} /></Button><Button size="icon" variant="ghost" title={text("remove")} aria-label={text("remove")} data-testid={`expense-void-${row.entry_id}`} onClick={() => remove(row)}><Trash2 size={15} /></Button></div>
      </article>)}
    </div>
    <div className="flex flex-wrap gap-3 justify-between items-center"><p className="text-xs num" data-testid="expense-ledger-pagination">{text("page")} {data.page} / {Math.max(1, Math.ceil(data.total / data.page_size))} · {data.total} {text("operations")}</p><div className="flex gap-2"><Button variant="outline" size="sm" disabled={data.page <= 1} onClick={() => setPage(data.page - 1)} data-testid="expense-ledger-previous"><ChevronLeft size={14} />{text("previous")}</Button><Button variant="outline" size="sm" disabled={data.page * data.page_size >= data.total} onClick={() => setPage(data.page + 1)} data-testid="expense-ledger-next">{text("next")}<ChevronRight size={14} /></Button></div></div>
  </div>;
};