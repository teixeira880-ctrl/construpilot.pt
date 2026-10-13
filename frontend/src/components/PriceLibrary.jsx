import { useEffect, useRef, useState } from "react";
import { BookMarked, Upload, Loader2, Trash2, FileSpreadsheet } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { style: "currency", currency: "EUR", maximumFractionDigits: 2 });

// Bibliothèque de prix propre à l'entreprise (Excel/PDF) — utilisée en priorité pour chiffrer les DPGF.
export const PriceLibrary = () => {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    try {
      const { data } = await api.get("/pro/price-library");
      setItems(data.items || []);
    } catch { /* silencieux */ } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/pro/price-library/upload", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${data.imported} preços importados — ${data.total} no total na sua biblioteca`);
      load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Importação impossível (.xlsx ou .pdf esperado)");
    } finally { setBusy(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const removeLine = async (id) => {
    try {
      await api.delete(`/pro/price-library/${id}`);
      setItems((prev) => prev.filter((x) => x.item_id !== id));
    } catch { toast.error("Não foi possível eliminar"); }
  };

  const clearAll = async () => {
    if (!window.confirm("Limpar toda a biblioteca de preços?")) return;
    try {
      await api.delete("/pro/price-library");
      setItems([]);
      toast.success("Biblioteca esvaziada");
    } catch { toast.error("Ação impossível"); }
  };

  return (
    <div className="surface p-6" data-testid="price-library">
      <div className="flex items-center gap-2 mb-1">
        <BookMarked className="h-5 w-5 text-primary" />
        <h3 className="font-display font-bold text-lg">A minha biblioteca de preços</h3>
        <span className="ml-2 text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary px-2 py-0.5 rounded-full">Pro Business</span>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Importe <span className="text-foreground">a sua própria tabela de preços</span> (Excel ou PDF). O ConstruPilot utiliza-o
        <span className="text-foreground"> em prioridade</span> para orçamentar os seus mapas — a IA só completa as linhas não encontradas.
      </p>

      <input ref={fileRef} type="file" accept=".xlsx,.pdf" hidden data-testid="library-file-input"
             onChange={(e) => upload(e.target.files?.[0])} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => fileRef.current?.click()} disabled={busy} className="gap-2 rounded-sm" data-testid="library-upload-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {busy ? "Análise em curso…" : "Importar Excel / PDF"}
        </Button>
        {items.length > 0 && (
          <Button variant="outline" onClick={clearAll} className="gap-2 rounded-sm text-destructive" data-testid="library-clear-btn">
            <Trash2 className="h-4 w-4" /> Esvaziar tudo
          </Button>
        )}
      </div>

      {!loading && items.length === 0 && (
        <p className="mt-4 text-sm text-muted-foreground inline-flex items-center gap-2">
          <FileSpreadsheet className="h-4 w-4" /> Nenhum preço por enquanto. Importe o seu primeiro mapa de trabalhos.
        </p>
      )}

      {items.length > 0 && (
        <div className="mt-4" data-testid="library-list">
          <div className="text-sm mb-2">Preços registados: <b>{items.length}</b></div>
          <div className="max-h-72 overflow-auto rounded-sm border border-border">
            <table className="w-full text-xs">
              <thead className="bg-secondary/40 sticky top-0">
                <tr>
                  <th className="text-left p-2">Designação</th>
                  <th className="p-2">Un.</th>
                  <th className="p-2 text-right">PU HT</th>
                  <th className="p-2"></th>
                </tr>
              </thead>
              <tbody>
                {items.map((l) => (
                  <tr key={l.item_id} className="border-t border-border/60" data-testid={`library-row-${l.item_id}`}>
                    <td className="p-2">{l.designation}</td>
                    <td className="p-2 text-center">{l.unit || "—"}</td>
                    <td className="p-2 text-right num">{eur(l.unit_price)}</td>
                    <td className="p-2 text-center">
                      <button onClick={() => removeLine(l.item_id)} className="text-muted-foreground hover:text-destructive" data-testid={`library-delete-${l.item_id}`}>
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
