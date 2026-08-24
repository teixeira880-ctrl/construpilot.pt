import { useEffect, useMemo, useState } from "react";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Loader2, Download, Search, Users } from "lucide-react";

function fmtCell(key, val) {
  if (val == null || val === "") return "—";
  if (key.includes("created_at") || key.includes("granted_at") || key === "created_at") {
    try { return new Date(val).toLocaleDateString("fr-FR"); } catch { return String(val); }
  }
  if (key.includes("value_eur") || key.includes("amount_eur")) {
    return (Number(val) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
  }
  return String(val);
}

function toCSV(columns, rows) {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const head = columns.map((c) => esc(c.label)).join(",");
  const body = rows.map((r) => columns.map((c) => esc(r[c.key])).join(",")).join("\n");
  return head + "\n" + body;
}

/** Drill-down d'un indicateur admin : liste détaillée + coordonnées + export CSV (cible pub). */
export default function AdminDrillDialog({ metric, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");

  useEffect(() => {
    if (!metric) { setData(null); setQ(""); return; }
    setLoading(true);
    api.get(`/admin/drill/${metric}`)
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Détails indisponibles"))
      .finally(() => setLoading(false));
  }, [metric]);

  const rows = useMemo(() => {
    if (!data) return [];
    if (!q.trim()) return data.rows;
    const needle = q.toLowerCase();
    return data.rows.filter((r) => Object.values(r).some((v) => String(v ?? "").toLowerCase().includes(needle)));
  }, [data, q]);

  const exportCSV = () => {
    if (!data || !rows.length) return;
    const csv = toCSV(data.columns, rows);
    const blob = new Blob(["\uFEFF" + csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `construpilot-${metric}-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`${rows.length} ligne(s) exportée(s)`);
  };

  return (
    <Dialog open={!!metric} onOpenChange={(o) => { if (!o) onClose(); }}>
      <DialogContent className="max-w-[95vw] w-[1100px] max-h-[88vh] flex flex-col" data-testid="admin-drill-dialog">
        <DialogHeader>
          <DialogTitle data-testid="admin-drill-title">{data?.title || "Détails"}</DialogTitle>
          <DialogDescription>{data?.description || "Chargement…"}</DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher (nom, e-mail, ville…)"
                   className="rounded-sm h-9 pl-9" data-testid="admin-drill-search" />
          </div>
          <span className="text-xs text-muted-foreground whitespace-nowrap flex items-center gap-1" data-testid="admin-drill-count">
            <Users className="h-3.5 w-3.5" /> {rows.length} résultat(s)
          </span>
          <Button size="sm" className="rounded-sm gap-2" onClick={exportCSV} disabled={!rows.length}
                  data-testid="admin-drill-export">
            <Download className="h-4 w-4" /> Exporter CSV
          </Button>
        </div>

        <div className="overflow-auto border border-border rounded-sm flex-1" data-testid="admin-drill-table-wrap">
          {loading ? (
            <div className="h-40 grid place-items-center"><Loader2 className="h-6 w-6 animate-spin text-primary" /></div>
          ) : !data ? null : rows.length === 0 ? (
            <p className="p-6 text-sm text-muted-foreground text-center">Aucune donnée.</p>
          ) : (
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-muted/95 backdrop-blur">
                <tr>
                  {data.columns.map((c) => (
                    <th key={c.key} className="text-left font-semibold px-3 py-2 whitespace-nowrap border-b border-border">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className="border-b border-border/50 hover:bg-muted/40" data-testid={`admin-drill-row-${i}`}>
                    {data.columns.map((c) => (
                      <td key={c.key} className="px-3 py-2 align-top max-w-[280px] truncate" title={fmtCell(c.key, r[c.key])}>
                        {fmtCell(c.key, r[c.key])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
