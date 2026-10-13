import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Library, Upload, Trash2, Download, Loader2, Search, AlertTriangle, CheckCircle2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { PriceHistoryPanel } from "@/components/admin/PriceHistoryPanel";

export default function AdminSharedLibraryTab() {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [meta, setMeta] = useState({});
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const load = async (query = "") => {
    setBusy(true);
    try {
      const { data } = await api.get("/admin/shared-library", { params: { q: query } });
      setItems(data.items || []);
      setTotal(data.total || 0);
      setMeta(data.meta || {});
    } finally { setBusy(false); }
  };

  useEffect(() => { load(); }, []);

  const modeRef = useRef("replace");
  const onImport = async (e) => {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    const merge = modeRef.current === "merge" || modeRef.current === "merge_prices";
    const updPrices = modeRef.current === "merge_prices";
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/admin/shared-library/import${merge ? `?merge=true${updPrices ? "&update_prices=true" : ""}` : ""}`, fd, {
        headers: { "Content-Type": "multipart/form-data" }, timeout: 180000,
      });
      if (merge) toast.success(`Fusion FR : ${data.added} adicionado(s)${updPrices ? `, ${data.updated_prices} preços atualizados` : ""}, ${data.kept_existing} mantidos · total ${data.total}`);
      else toast.success(`${data.imported} artigos importados (colunas: ${data.columns_detected.length})`);
      await load(q);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Não foi possível importar");
    } finally { setUploading(false); }
  };

  const clearAll = async () => {
    if (!window.confirm("Eliminar TODA a biblioteca partilhada?")) return;
    await api.delete("/admin/shared-library");
    toast.success("Biblioteca partilhada esvaziada");
    await load();
  };

  const downloadTemplate = async () => {
    const { data } = await api.get("/admin/shared-library/template");
    const blob = new Blob([data], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "modele-bibliotheque-construpilot.csv"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6" data-testid="admin-shared-library">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Library className="h-5 w-5 text-primary" /> Biblioteca partilhada (Pro Business)
          </h3>
          <p className="text-sm text-muted-foreground max-w-2xl mt-1">
            Importe uma biblioteca de trabalhos (CSV ou Excel) com preços <b>baixo / médio / alto</b>. É acessível automaticamente por todas as empresas <b>Pro Business</b>, e a IA utiliza-a para orçamentar segundo a gama de preços escolhida.
            <br />A importação <b>substitui inteiramente</b> a biblioteca existente.
          </p>
        </div>
        <div className="flex flex-col items-end gap-2">
          {total > 0 ? (
            <Badge className="bg-emerald-600 hover:bg-emerald-600 gap-1" data-testid="shared-lib-count">
              <CheckCircle2 className="h-3 w-3" /> {total} ouvrages
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1 text-amber-600 border-amber-400">
              <AlertTriangle className="h-3 w-3" /> Vazio
            </Badge>
          )}
          {meta.imported_at && (
            <span className="text-[11px] text-muted-foreground">
              Atual. {new Date(meta.imported_at).toLocaleString("fr-FR")} · {meta.last_file}
            </span>
          )}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.xlsm" className="hidden"
               onChange={onImport} data-testid="shared-lib-file-input" />
        <Button onClick={() => { modeRef.current = "replace"; fileRef.current?.click(); }} disabled={uploading}
                className="rounded-sm gap-2 bg-primary" data-testid="shared-lib-import-btn">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          Importar (substituir) CSV / Excel
        </Button>
        <Button variant="outline" onClick={() => { modeRef.current = "merge"; fileRef.current?.click(); }} disabled={uploading}
                className="rounded-sm gap-2 border-primary/40 text-primary" title="Conserva o existente, adiciona apenas os artigos em falta (FR apenas, a biblioteca PT não é afetada)"
                data-testid="shared-lib-merge-btn">
          <Upload className="h-4 w-4" /> Fundir (adicionar os em falta, PT)
        </Button>
        <Button variant="outline" onClick={() => { modeRef.current = "merge_prices"; fileRef.current?.click(); }} disabled={uploading}
                className="rounded-sm gap-2 border-amber-500/50 text-amber-600" title="Adiciona os em falta E atualiza os preços dos trabalhos FR já presentes (os trabalhos ausentes do ficheiro são conservados, PT intacta)"
                data-testid="shared-lib-merge-prices-btn">
          <Upload className="h-4 w-4" /> Fundir + atualizar os preços
        </Button>
        <Button variant="outline" onClick={async () => {
                  try {
                    const res = await api.get("/admin/shared-library/export.xlsx", { responseType: "blob" });
                    const url = URL.createObjectURL(res.data); const a = document.createElement("a");
                    a.href = url; a.download = "ConstruPilot_FR_Bibliotheque_export.xlsx"; a.click(); URL.revokeObjectURL(url);
                  } catch { toast.error("Impossível exportar"); }
                }} className="rounded-sm gap-2" data-testid="shared-lib-export-btn">
          <Download className="h-4 w-4" /> Exportar a biblioteca FR (Excel)
        </Button>
        <Button variant="outline" onClick={downloadTemplate} className="rounded-sm gap-2"
                data-testid="shared-lib-template-btn">
          <Download className="h-4 w-4" /> Modelo CSV
        </Button>
        {total > 0 && (
          <Button variant="ghost" onClick={clearAll} className="rounded-sm gap-2 text-destructive"
                  data-testid="shared-lib-clear-btn">
            <Trash2 className="h-4 w-4" /> Esvaziar
          </Button>
        )}
      </div>

      <PriceHistoryPanel refreshKey={total} />

      <div className="relative max-w-sm">
        <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)}
               onKeyDown={(e) => e.key === "Enter" && load(q)}
               placeholder="Pesquisar um artigo / categoria…" className="rounded-sm pl-9"
               data-testid="shared-lib-search" />
      </div>

      <div className="border border-border rounded-sm overflow-hidden">
        <Table data-testid="shared-lib-table">
          <TableHeader>
            <TableRow className="bg-secondary/60 hover:bg-secondary/60">
              <TableHead>Categoria</TableHead>
              <TableHead>Designação</TableHead>
              <TableHead>Un.</TableHead>
              <TableHead className="text-right">Baixo €</TableHead>
              <TableHead className="text-right">Mediano €</TableHead>
              <TableHead className="text-right">Alto €</TableHead>
              <TableHead className="text-right">IVA</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {busy ? (
              <TableRow><TableCell colSpan={7} className="text-center py-8">
                <Loader2 className="h-5 w-5 animate-spin mx-auto" /></TableCell></TableRow>
            ) : items.length === 0 ? (
              <TableRow><TableCell colSpan={7} className="text-center py-8 text-muted-foreground">
                Nenhum trabalho. Importe um ficheiro para começar.</TableCell></TableRow>
            ) : items.map((it) => (
              <TableRow key={it.item_id}>
                <TableCell className="text-xs text-muted-foreground">{it.category}</TableCell>
                <TableCell className="font-medium">{it.designation}</TableCell>
                <TableCell className="text-xs">{it.unit}</TableCell>
                <TableCell className="text-right num">{it.price_low?.toFixed(0)}</TableCell>
                <TableCell className="text-right num font-semibold">{it.price_mid?.toFixed(0)}</TableCell>
                <TableCell className="text-right num">{it.price_high?.toFixed(0)}</TableCell>
                <TableCell className="text-right text-xs">{it.vat_rate != null ? `${it.vat_rate}%` : "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      {total > items.length && (
        <p className="text-xs text-muted-foreground">Visualização dos {items.length} primeiros de {total}. Utilize a pesquisa.</p>
      )}
    </div>
  );
}
