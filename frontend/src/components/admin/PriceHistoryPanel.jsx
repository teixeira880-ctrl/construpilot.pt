import { useEffect, useState } from "react";
import { History, ChevronDown, ChevronUp } from "lucide-react";
import { api } from "@/lib/api";

const eur = (n) => (n == null ? "—" : `${Number(n).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} €`);

export const PriceHistoryPanel = ({ refreshKey }) => {
  const [rows, setRows] = useState([]);
  const [open, setOpen] = useState(false);
  useEffect(() => {
    api.get("/admin/shared-library/price-history?limit=200").then(({ data }) => setRows(data.items || [])).catch(() => setRows([]));
  }, [refreshKey]);
  return (
    <div className="rounded-sm border border-border/60 bg-secondary/20" data-testid="price-history-panel">
      <button onClick={() => setOpen(!open)} className="w-full flex items-center gap-2 px-3 py-2 text-sm font-medium" data-testid="price-history-toggle">
        <History className="h-4 w-4 text-primary" /> Histórico de preços — {rows.length} variation{rows.length > 1 ? "s" : ""} registada{rows.length > 1 ? "s" : ""}
        <span className="ml-auto">{open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</span>
      </button>
      {open && (rows.length === 0 ? (
        <p className="px-3 pb-3 text-xs text-muted-foreground" data-testid="price-history-empty">Nenhuma variação por agora: o histórico é preenchido em cada importação Excel com «atualizar os preços».</p>
      ) : (
        <div className="max-h-80 overflow-auto">
          <table className="w-full text-xs" data-testid="price-history-table">
            <thead className="sticky top-0 bg-background text-[10px] uppercase tracking-wide text-muted-foreground">
              <tr><th className="text-left px-3 py-1.5">Data</th><th className="text-left px-2 py-1.5">Artigo</th><th className="text-right px-2 py-1.5">Mediana antes</th><th className="text-right px-2 py-1.5">Mediana depois</th><th className="text-right px-3 py-1.5">Δ</th><th className="text-left px-2 py-1.5">Ficheiro</th></tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.hist_id} className="border-t border-border/40" data-testid={`price-history-row-${r.hist_id}`}>
                  <td className="px-3 py-1.5 text-muted-foreground whitespace-nowrap">{new Date(r.at).toLocaleDateString("pt-PT")}</td>
                  <td className="px-2 py-1.5">{r.designation} <span className="text-muted-foreground">({r.unit})</span></td>
                  <td className="px-2 py-1.5 text-right num">{eur(r.old?.price_mid)}</td>
                  <td className="px-2 py-1.5 text-right num font-medium">{eur(r.new?.price_mid)}</td>
                  <td className={`px-3 py-1.5 text-right num font-semibold ${r.delta_pct > 0 ? "text-amber-600" : r.delta_pct < 0 ? "text-emerald-600" : ""}`}>{r.delta_pct == null ? "—" : `${r.delta_pct > 0 ? "+" : ""}${r.delta_pct} %`}</td>
                  <td className="px-2 py-1.5 text-muted-foreground truncate max-w-[180px]">{r.file}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
};
