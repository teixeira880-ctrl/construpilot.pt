import { ExpenseCheck, ExpenseInput, ExpenseSelect } from "./Fields";
import { useExpenseCopy } from "./copy";

export const EntryFields = ({ form, set, editing, options }) => {
  const { text } = useExpenseCopy();
  const unassigned = [{ value: "", label: text("unattributed") }];
  return <>
    {!editing && <>
      <ExpenseInput name="expense-entry-date" label={text("date")} type="date" required value={form.occurred_on} onChange={v => set("occurred_on", v)} />
      <ExpenseSelect name="expense-entry-scope" label={text("scope")} value={form.scope} onChange={v => set("scope", v)} options={["single", "monthly_total"].map(v => ({ value: v, label: text(v) }))} />
      {form.scope === "monthly_total" ? <p className="text-sm text-amber-700 dark:text-amber-400 sm:col-span-2" data-testid="expense-monthly-reconciliation-notice">{text("monthlyNote")}</p> : <>
        <ExpenseInput name="expense-entry-feature" label={text("feature")} required maxLength={80} value={form.feature} onChange={v => set("feature", v)} />
        <ExpenseSelect name="expense-entry-company" label={text("company")} value={form.company_id} onChange={v => set("company_id", v)} options={[...unassigned, ...options.companies.map(c => ({ value: c.org_id, label: c.name || c.org_id }))]} />
        <ExpenseSelect name="expense-entry-user" label={text("user")} value={form.user_id} onChange={v => set("user_id", v)} options={[...unassigned, ...options.users.map(u => ({ value: u.user_id, label: u.name || u.email }))]} />
      </>}
    </>}
    <ExpenseInput name="expense-entry-reference" label={text("reference")} required minLength={3} maxLength={180} value={form.source_ref} onChange={v => set("source_ref", v)} />
    <ExpenseInput name="expense-entry-amount" label={text("amount")} type="number" required step="0.000001" value={form.amount} onChange={v => set("amount", v)} />
    <ExpenseInput name="expense-entry-currency" label={text("currency")} required pattern="[A-Z]{3}" minLength={3} maxLength={3} value={form.currency} onChange={v => set("currency", v.toUpperCase())} />
    {form.currency !== "EUR" && <><ExpenseInput name="expense-entry-settled-eur" label={text("settled")} type="number" step="0.000001" value={form.settled_eur} onChange={v => set("settled_eur", v)} /><ExpenseInput name="expense-entry-settlement-reference" label={text("settlementRef")} required={form.settled_eur !== ""} maxLength={180} value={form.settlement_ref} onChange={v => set("settlement_ref", v)} /></>}
    <div className="sm:col-span-2 grid gap-4 border-t pt-4"><ExpenseCheck name="expense-entry-attested" checked={form.confirmed_charge} onChange={v => set("confirmed_charge", v)} label={text("attested")} required />{!editing && <ExpenseCheck name="expense-entry-is-test" checked={form.is_test} onChange={v => set("is_test", v)} label={text("isTest")} />}</div>
  </>;
};