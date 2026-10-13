import { ExpenseInput, ExpenseSelect } from "./Fields";
import { useExpenseCopy } from "./copy";

export const RateFields = ({ form, set }) => {
  const { text } = useExpenseCopy();
  return <>
    <ExpenseInput name="expense-rate-model" label={text("model")} maxLength={120} value={form.model} onChange={v => set("model", v)} />
    <ExpenseInput name="expense-rate-effective" label={text("effective")} type="date" required value={form.effective_from} onChange={v => set("effective_from", v)} />
    <ExpenseInput name="expense-rate-reference" label={text("rateRef")} required minLength={3} maxLength={180} value={form.source_ref} onChange={v => set("source_ref", v)} />
    <ExpenseInput name="expense-rate-currency" label={text("currency")} required pattern="[A-Z]{3}" minLength={3} maxLength={3} value={form.currency} onChange={v => set("currency", v.toUpperCase())} />
    <ExpenseSelect name="expense-rate-mode" label={text("mode")} value={form.mode} onChange={v => set("mode", v)} options={[{ value: "unit", label: text("unitMode") }, { value: "tokens", label: text("tokens") }]} />
    {form.mode === "tokens" ? <>{["input", "output"].map(k => <ExpenseInput key={k} name={`expense-rate-${k}-price`} label={text(`${k}Price`)} required type="number" min="0" step="0.000001" value={form[`${k}_price`]} onChange={v => set(`${k}_price`, v)} />)}</> : <>
      <ExpenseSelect name="expense-rate-unit" label={text("unit")} value={form.unit} onChange={v => set("unit", v)} options={["calls", "input_tokens", "output_tokens", "cached_input_tokens", "seconds", "images", "videos", "pages", "letters", "conversions", "characters", "bytes", "credits"].map(v => ({ value: v, label: text(v) }))} />
      <ExpenseInput name="expense-rate-price" label={text("price")} required type="number" min="0" step="0.000001" value={form.price} onChange={v => set("price", v)} />
      <ExpenseInput name="expense-rate-per-units" label={text("perUnits")} required type="number" min="0.000001" step="0.000001" value={form.per_units} onChange={v => set("per_units", v)} />
    </>}
  </>;
};