import { useState } from "react";
import { Save, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useConfirm } from "@/components/ConfirmProvider";
import { ExpenseInput, ExpenseSelect } from "./Fields";
import { EntryFields } from "./EntryFields";
import { RateFields } from "./RateFields";
import { useExpenseCopy } from "./copy";

export const ExpenseDialog = ({ config, month, providers, options, onClose, onSaved }) => {
  const { text } = useExpenseCopy();
  const confirm = useConfirm();
  const { type, row } = config;
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [form, setForm] = useState(() => ({ provider: row?.provider || (type === "budget" ? "all" : "autodesk"), amount: row?.amount ?? "", currency: row?.currency || "EUR", source_ref: row?.evidence === "confirmed" ? row.source_ref : "", occurred_on: `${month}-01`, scope: "single", feature: "invoice", company_id: "", user_id: "", confirmed_charge: false, is_test: false, settled_eur: row?.currency !== "EUR" ? row?.amount_eur ?? "" : "", settlement_ref: "", amount_eur: row?.amount_eur || "", warning_percent: row?.warning_percent || 80, model: "", mode: "unit", unit: "calls", per_units: "1", price: "", input_price: "", output_price: "", effective_from: `${month}-01` }));
  const set = (key, value) => setForm(f => ({ ...f, [key]: value }));
  const title = text(type === "budget" ? "setBudget" : type === "rate" ? "addRate" : row ? "edit" : "add");
  const save = async event => {
    event.preventDefault(); setBusy(true); setError("");
    try {
      if (type === "budget") await api.put("/admin/expenses/budgets", { provider: form.provider, month, amount_eur: form.amount_eur, warning_percent: Number(form.warning_percent) });
      else if (type === "rate") await api.put("/admin/expenses/rates", { provider: form.provider, model: form.model, currency: form.currency, mode: form.mode, unit: form.unit, per_units: form.per_units, price: form.price || "0", input_price: form.input_price || "0", output_price: form.output_price || "0", effective_from: form.effective_from, source_ref: form.source_ref });
      else {
        const body = { source_ref: form.source_ref, amount: form.amount, currency: form.currency, confirmed_charge: form.confirmed_charge, settled_eur: form.currency !== "EUR" && form.settled_eur !== "" ? form.settled_eur : null, settlement_ref: form.currency !== "EUR" ? form.settlement_ref || null : null };
        if (row) await api.put(`/admin/expenses/entries/${row.entry_id}/confirmation`, { ...body, version: row.version });
        else await api.post("/admin/expenses/entries", { ...body, provider: form.provider, occurred_on: form.occurred_on, scope: form.scope, feature: form.feature, user_id: form.scope === "single" ? form.user_id || null : null, company_id: form.scope === "single" ? form.company_id || null : null, is_test: form.is_test });
      }
      toast.success(text("saved")); onSaved();
    } catch (e) { setError(typeof e.response?.data?.detail === "string" ? e.response.data.detail : text("error")); }
    finally { setBusy(false); }
  };
  const removeBudget = async () => {
    if (!await confirm({ title: text("removeConfirm"), confirmLabel: text("remove"), destructive: true })) return;
    setBusy(true);
    try { await api.delete(`/admin/expenses/budgets/${row.budget_id}`); onSaved(); } catch { setError(text("error")); } finally { setBusy(false); }
  };
  return <Dialog open onOpenChange={open => { if (!open && !busy) onClose(); }}><DialogContent className="max-w-2xl max-h-[90dvh] overflow-y-auto" data-testid="expense-edit-dialog"><DialogHeader><DialogTitle data-testid="expense-dialog-title">{title}</DialogTitle><DialogDescription data-testid="expense-dialog-description">{text(type === "budget" ? "advisory" : type === "rate" ? "rateNote" : "totalsNote")}</DialogDescription></DialogHeader>
    <form onSubmit={save} className="grid gap-5" data-testid="expense-edit-form"><fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2 min-w-0">
      <ExpenseSelect name="expense-dialog-provider" label={text("provider")} value={form.provider} onChange={v => set("provider", v)} disabled={!!row} options={[...(type === "budget" ? [{ value: "all", label: text("all") }] : []), ...providers.map(p => ({ value: p.provider, label: p.name }))]} />
      {type === "budget" && <><ExpenseInput name="expense-budget-month" label={text("month")} value={month} readOnly onChange={() => {}} /><ExpenseInput name="expense-budget-amount" label={`${text("budget")} · EUR`} type="number" min="0.01" step="0.01" required value={form.amount_eur} onChange={v => set("amount_eur", v)} /><ExpenseInput name="expense-budget-warning" label={text("warning")} type="number" min="1" max="99" required value={form.warning_percent} onChange={v => set("warning_percent", v)} /></>}
      {type === "entry" && <EntryFields form={form} set={set} editing={!!row} options={options} />}
      {type === "rate" && <RateFields form={form} set={set} />}
    </fieldset>
    {error && <p role="alert" className="text-sm text-red-600" data-testid="expense-dialog-error">{error}</p>}
    <div className="flex flex-wrap gap-2 justify-end border-t pt-4">{type === "budget" && row && <Button type="button" variant="ghost" disabled={busy} onClick={removeBudget} data-testid="expense-remove-budget"><Trash2 size={15} />{text("remove")}</Button>}<Button type="button" variant="outline" onClick={onClose} disabled={busy} data-testid="expense-dialog-cancel">{text("cancel")}</Button><Button type="submit" disabled={busy} data-testid="expense-confirm-modal-submit"><Save size={16} />{text(busy ? "loading" : "save")}</Button></div>
    </form>
  </DialogContent></Dialog>;
};