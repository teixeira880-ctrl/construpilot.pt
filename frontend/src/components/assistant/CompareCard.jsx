import { useState } from "react";
import { ChevronDown, ChevronUp, FileDown } from "lucide-react";
import { toast } from "sonner";
import { eur2 } from "@/lib/api";

async function dlComparePdf(id) {
  const res = await fetch(`${process.env.REACT_APP_BACKEND_URL}/api/assistant/comparisons/${id}/pdf`, {  credentials: "include" });
  if (!res.ok) return toast.error("PDF indisponível");
  const url = URL.createObjectURL(await res.blob()); const el = document.createElement("a"); el.href = url; el.download = "comparacao-construpilot.pdf"; el.click(); URL.revokeObjectURL(url);
}

const STATUS = {
  identical: ["Idêntico", "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"],
  different_quantity: ["Quantidade ≠", "bg-amber-500/15 text-amber-700 dark:text-amber-400"],
  different_price: ["Preço ≠", "bg-orange-500/15 text-orange-700 dark:text-orange-400"],
  different_scope: ["Âmbito ≠", "bg-sky-500/15 text-sky-700 dark:text-sky-400"],
  only_a: ["Apenas A", "bg-muted text-muted-foreground"], only_b: ["Apenas B", "bg-muted text-muted-foreground"],
  to_confirm: ["A confirmar", "bg-violet-500/15 text-violet-700 dark:text-violet-400"],
};
const IMP = { high: "border-l-red-500", medium: "border-l-amber-500", low: "border-l-slate-300" };
const KIND = { observed: "observado", calculated: "calculado", deduced: "deduzido", to_confirm: "a confirmar" };
const n = (v) => (v === null || v === undefined ? "—" : eur2(v));
const q = (v, u) => (v === null || v === undefined ? "—" : `${v} ${u || ""}`.trim());

function DocHead({ tag, d, name }) {
  return (
    <div className="rounded-sm border bg-background p-2" data-testid={`compare-doc-${tag.toLowerCase()}`}>
      <div className="text-[10px] uppercase tracking-wide text-muted-foreground">Documento {tag}</div>
      <b className="block truncate" title={name}>{name}</b>
      <div className="text-muted-foreground">{d.issuer || "—"}{d.date ? ` · ${d.date}` : ""} · {d.lines_count} linha(s)</div>
      <div>s/ IVA {n(d.total_ht)} · IVA {d.vat_rate ?? "—"} % · <b>c/ IVA {n(d.total_ttc)}</b></div>
    </div>
  );
}

export function CompareCard({ r }) {
  const c = r.comparison;
  const [all, setAll] = useState(false);
  const rows = all ? c.line_matches : c.line_matches.slice(0, 6);
  return (
    <div className="mt-1 grid gap-2" data-testid="assistant-compare-card">
      <div className="grid sm:grid-cols-2 gap-2"><DocHead tag="A" d={c.document_a} name={r.filename_a} /><DocHead tag="B" d={c.document_b} name={r.filename_b} /></div>
      <p data-testid="compare-summary">{c.summary}</p>
      {c.line_matches.length > 0 && (
        <div className="overflow-x-auto rounded-sm border bg-background">
          <table className="w-full text-[11px]" data-testid="compare-table">
            <thead className="bg-muted/40 text-[10px] uppercase"><tr><th className="px-2 py-1 text-left">Artigo</th><th className="px-2 py-1 text-right">Qtd A / B</th><th className="px-2 py-1 text-right">PU A / B</th><th className="px-2 py-1 text-right">Total A / B</th><th className="px-2 py-1 text-right">Desvio</th><th className="px-2 py-1">Estado</th></tr></thead>
            <tbody>
              {rows.map((l, i) => {
                const [lbl, cls] = STATUS[l.status] || [l.status, ""];
                return (
                  <tr key={i} className="border-t align-top" title={l.comment} data-testid={`compare-row-${i}`}>
                    <td className="px-2 py-1"><b>{l.topic}</b><div className="text-muted-foreground">{l.designation_a || "—"} / {l.designation_b || "—"}</div></td>
                    <td className="px-2 py-1 text-right whitespace-nowrap">{q(l.qty_a, l.unit)}<br />{q(l.qty_b, l.unit)}</td>
                    <td className="px-2 py-1 text-right whitespace-nowrap">{n(l.unit_price_a)}<br />{n(l.unit_price_b)}</td>
                    <td className="px-2 py-1 text-right whitespace-nowrap">{n(l.total_a)}<br />{n(l.total_b)}</td>
                    <td className={`px-2 py-1 text-right whitespace-nowrap ${l.delta_pct > 0 ? "text-orange-600" : l.delta_pct < 0 ? "text-emerald-600" : ""}`}>{l.delta_pct === null || l.delta_pct === undefined ? "—" : `${l.delta_pct > 0 ? "+" : ""}${Math.round(l.delta_pct * 10) / 10} %`}</td>
                    <td className="px-2 py-1"><span className={`px-1.5 py-0.5 rounded-sm whitespace-nowrap ${cls}`}>{lbl}</span></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          {c.line_matches.length > 6 && <button className="w-full text-[11px] py-1 underline flex items-center justify-center gap-1" onClick={() => setAll(!all)} data-testid="compare-toggle-rows">{all ? <><ChevronUp className="h-3 w-3" /> Reduzir</> : <><ChevronDown className="h-3 w-3" /> Ver os {c.line_matches.length} postes</>}</button>}
        </div>
      )}
      <div className="grid sm:grid-cols-2 gap-2">
        {c.only_in_a.length > 0 && <div data-testid="compare-only-a"><b>Apenas em A:</b><ul className="list-disc ml-4">{c.only_in_a.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
        {c.only_in_b.length > 0 && <div data-testid="compare-only-b"><b>Apenas em B:</b><ul className="list-disc ml-4">{c.only_in_b.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
      </div>
      {c.differences.length > 0 && (
        <div className="grid gap-1" data-testid="compare-differences">
          <b>Diferenças notáveis</b>
          {c.differences.map((d, i) => <div key={i} className={`border-l-2 pl-2 ${IMP[d.importance] || ""}`}><b>{d.topic}</b> <span className="text-muted-foreground">({KIND[d.kind] || d.kind})</span> — {d.detail}</div>)}
        </div>
      )}
      {c.questions_to_ask.length > 0 && <div data-testid="compare-questions"><b>Perguntas a colocar:</b><ul className="list-disc ml-4">{c.questions_to_ask.map((x, i) => <li key={i}>{x}</li>)}</ul></div>}
      {c.caveats.length > 0 && <p className="italic text-muted-foreground border-l-2 border-slate-300 pl-2">{c.caveats.join(" ")}</p>}
      {r.comparison_id && <button className="inline-flex items-center gap-1 self-start px-2 py-1 rounded-sm border bg-background hover:bg-muted transition-colors" onClick={() => dlComparePdf(r.comparison_id)} data-testid="compare-pdf-btn"><FileDown className="h-3 w-3" /> Descarregar a comparação em PDF</button>}
    </div>
  );
}
