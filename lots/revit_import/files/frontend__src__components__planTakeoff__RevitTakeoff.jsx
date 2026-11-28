import React, { useState } from "react";

const UNIT = { m2: "m²", m3: "m³", ml: "ml", u: "u", kg: "kg" };
const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toLocaleString("pt-PT", { maximumFractionDigits: 2 }));

/** Medição Revit por nível (lida nos parâmetros calculados pelo Revit, todos os elementos da vista 3D). */
export default function RevitTakeoff({ revit }) {
  const levels = revit?.levels || [];
  const [level, setLevel] = useState(levels[0] || null);
  if (!revit?.rows?.length) return null;
  const rows = revit.rows.filter((r) => r.level === level);
  return (
    <div className="mt-4" data-testid="plans-pro-revit-takeoff">
      <div className="flex flex-wrap items-baseline justify-between gap-2 mb-1">
        <h3 className="font-semibold">Medição Revit por nível</h3>
        <span className="text-xs text-slate-500">{revit.elements_count} elementos medidos{revit.view ? ` · vista ${revit.view}` : ""}</span>
      </div>
      <p className="text-xs text-slate-500 mb-2">{revit.method}</p>
      {(revit.warnings || []).length > 0 && (
        <ul className="text-xs text-amber-700 mb-2 list-disc ml-4" data-testid="plans-pro-revit-warnings">
          {revit.warnings.map((w, i) => <li key={i}>{w}</li>)}
        </ul>
      )}
      <div className="flex flex-wrap gap-1 mb-2" role="tablist">
        {levels.map((l) => (
          <button key={l} type="button" role="tab" aria-selected={l === level} onClick={() => setLevel(l)} data-testid={`plans-pro-revit-level-${l}`}
            className={`px-2.5 py-1 rounded-full text-xs border ${l === level ? "bg-emerald-600 text-white border-emerald-600" : "border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800"}`}>
            {l}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm border border-slate-200 dark:border-slate-800 rounded-lg overflow-hidden">
          <thead className="bg-slate-100 dark:bg-slate-900/60">
            <tr>
              <th className="text-left p-2">Trabalho</th>
              <th className="text-left p-2">Tipo Revit</th>
              <th className="text-right p-2">Quantidade</th>
              <th className="text-right p-2">Número</th>
              <th className="text-right p-2">Volume (m³)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={`${r.ouvrage}-${r.type}-${i}`} className="border-t border-slate-200 dark:border-slate-800">
                <td className="p-2 font-medium">{r.ouvrage}</td>
                <td className="p-2">{r.type}{r.quantity_note && <div className="text-[11px] text-amber-700">{r.quantity_note}</div>}</td>
                <td className="p-2 text-right whitespace-nowrap">{fmt(r.quantity)} {UNIT[r.unit] || r.unit}</td>
                <td className="p-2 text-right">{r.count}</td>
                <td className="p-2 text-right">{fmt(r.volume_m3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-[11px] text-slate-500 mt-1">A exportação Excel inclui o controlo elemento a elemento (IDs Revit), os subtotais por nível e uma coluna de preços a preencher.</p>
    </div>
  );
}
