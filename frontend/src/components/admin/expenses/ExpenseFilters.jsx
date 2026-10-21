import { ExpenseCheck, ExpenseInput, ExpenseSelect } from "./Fields";
import { useExpenseCopy } from "./copy";

export const ExpenseFilters = ({ filters, setFilters, providers, options }) => {
  const { text } = useExpenseCopy();
  const change = (key, value) => setFilters({ ...filters, [key]: value });
  const all = [{ value: "", label: text("all") }];
  const unassigned = { value: "unattributed", label: text("unattributed") };
  return <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 border-y py-5" data-testid="expense-filters">
    <ExpenseInput name="expense-filter-month" label={text("month")} type="month" value={filters.month} required onChange={v => { if (/^\d{4}-(0[1-9]|1[0-2])$/.test(v)) change("month", v); }} />
    <ExpenseSelect name="expense-filter-provider" label={text("provider")} value={filters.provider} onChange={v => change("provider", v)} options={[...all, ...providers.map(p => ({ value: p.provider, label: p.name }))]} />
    <ExpenseSelect name="expense-filter-feature" label={text("feature")} value={filters.feature} onChange={v => change("feature", v)} options={[...all, ...options.features.map(f => ({ value: f, label: f }))]} />
    <ExpenseSelect name="expense-filter-company" label={text("company")} value={filters.company_id} onChange={v => change("company_id", v)} options={[...all, unassigned, ...options.companies.map(c => ({ value: c.org_id, label: c.name || c.org_id }))]} />
    <ExpenseSelect name="expense-filter-user" label={text("user")} value={filters.user_id} onChange={v => change("user_id", v)} options={[...all, unassigned, ...options.users.map(u => ({ value: u.user_id, label: u.name || u.email }))]} />
    <div className="flex items-center pt-5"><ExpenseCheck name="expense-filter-tests" checked={filters.include_test} onChange={v => change("include_test", v)} label={text("includeTest")} /></div>
  </div>;
};