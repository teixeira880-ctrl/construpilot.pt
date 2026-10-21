import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useExpenseCopy } from "./copy";

export const ExpenseField = ({ id, label, children }) => <div className="min-w-0 grid content-start gap-1.5"><Label htmlFor={id}>{label}</Label>{children}</div>;
export const ExpenseInput = ({ name, label, value, onChange, ...props }) => <ExpenseField id={name} label={label}><Input id={name} data-testid={name} value={value ?? ""} onChange={e => onChange(e.target.value)} {...props} /></ExpenseField>;
export const ExpenseSelect = ({ name, label, value, onChange, options, ...props }) => {
  const unique = [...new Map(options.filter(o => o.value != null).map(o => [o.value, o])).values()];
  return <ExpenseField id={name} label={label}><select id={name} data-testid={name} value={value} onChange={e => onChange(e.target.value)} className="h-10 w-full min-w-0 rounded-md border border-input bg-background px-2 text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-ring" {...props}>{unique.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}</select></ExpenseField>;
};
export const EvidenceBadge = ({ value, id }) => {
  const { text } = useExpenseCopy();
  return <span data-testid={id} className={`inline-block rounded px-2 py-1 text-xs font-semibold ${value === "confirmed" ? "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400" : value === "estimated" ? "bg-amber-500/10 text-amber-700 dark:text-amber-400" : "bg-muted text-muted-foreground"}`}>{text(value)}</span>;
};
export const ExpenseCheck = ({ name, checked, onChange, label, required }) => <label className="flex items-start gap-2 text-sm" htmlFor={name}><input type="checkbox" id={name} data-testid={name} checked={checked} required={required} onChange={e => onChange(e.target.checked)} className="mt-1 accent-emerald-700" />{label}</label>;