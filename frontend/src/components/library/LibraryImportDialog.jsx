import { useRef, useState } from "react";
import { FileUp, Loader2, CheckCircle2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

export default function LibraryImportDialog({ open, onClose, onDone }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [rows, setRows] = useState(null);
  const [category, setCategory] = useState("");
  const inputRef = useRef(null);

  const reset = () => { setFiles([]); setRows(null); setCategory(""); };

  const analyse = async () => {
    if (!files.length) { toast.error("Choisissez au moins un PDF"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const { data } = await api.post("/library/import-pdf/preview", fd, { timeout: 180000 });
      const flat = [];
      (data.items || []).forEach((it) => {
        if (!it.ok) { toast.error(`${it.file} : ${it.error || "lecture impossible"}`); return; }
        it.lines.forEach((l) => flat.push({ ...l, file: it.file, checked: true }));
      });
      if (!flat.length) toast.error("Aucun ouvrage avec prix trouvé dans ces documents");
      setRows(flat);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Analyse impossible");
    } finally { setBusy(false); }
  };

  const confirm = async () => {
    const chosen = (rows || []).filter((r) => r.checked);
    if (!chosen.length) { toast.error("Sélectionnez au moins une ligne"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/library/import-pdf/confirm", {
        category, lines: chosen.map(({ checked, file, existing_price, ...l }) => l),
      });
      toast.success(`${data.created} ouvrage(s) ajouté(s), ${data.updated} mis à jour`);
      onDone?.(); reset(); onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import impossible");
    } finally { setBusy(false); }
  };

  const setRow = (i, patch) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const allChecked = rows?.length && rows.every((r) => r.checked);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose(); } }}>
      <DialogContent className="max-w-3xl" data-testid="library-import-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><FileUp className="h-5 w-5 text-primary" /> Reprendre mes anciens devis</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground -mt-2">
          Déposez vos anciens devis en PDF (Tolteck, Obat, Batappli, Excel/Word exportés…). L'IA en extrait vos ouvrages, unités et prix pour reconstruire votre bibliothèque — vous ne repartez pas de zéro.
        </p>

        {!rows && (
          <div className="space-y-3">
            <div className="border-2 border-dashed border-border rounded-md p-6 text-center cursor-pointer hover:border-primary transition-colors"
                 onClick={() => inputRef.current?.click()} data-testid="library-import-dropzone">
              <Upload className="h-6 w-6 mx-auto text-muted-foreground mb-2" />
              <p className="text-sm">{files.length ? `${files.length} fichier(s) sélectionné(s)` : "Cliquez pour choisir vos PDF (jusqu'à 20)"}</p>
              {files.length > 0 && <p className="text-[11px] text-muted-foreground mt-1 truncate">{files.map((f) => f.name).join(" · ")}</p>}
              <input ref={inputRef} type="file" accept="application/pdf" multiple className="hidden"
                     onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, 20))} data-testid="library-import-input" />
            </div>
            <Button onClick={analyse} disabled={busy || !files.length} className="rounded-sm gap-2 w-full" data-testid="library-import-analyse">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />} {busy ? "Lecture IA en cours…" : "Analyser mes devis"}
            </Button>
          </div>
        )}

        {rows && (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3 text-xs">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={!!allChecked} onChange={(e) => setRows((rs) => rs.map((r) => ({ ...r, checked: e.target.checked })))}
                       data-testid="library-import-check-all" className="h-4 w-4 accent-emerald-600" />
                {rows.filter((r) => r.checked).length} / {rows.length} lignes retenues
              </label>
              <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Lot / catégorie (optionnel, sinon titre du devis)"
                     className="h-8 text-xs max-w-xs" data-testid="library-import-category" />
            </div>
            <div className="max-h-[50vh] overflow-y-auto border border-border rounded-md">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-background">
                  <tr className="text-left text-muted-foreground border-b border-border">
                    <th className="p-2 w-8" /><th className="p-2">Désignation</th><th className="p-2 w-16">Unité</th>
                    <th className="p-2 w-24 text-right">PU HT</th><th className="p-2 w-24 text-right">Coût revient</th><th className="p-2 w-28">Actuel</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r, i) => (
                    <tr key={i} className={`border-b border-border/40 ${r.checked ? "" : "opacity-50"}`} data-testid={`library-import-row-${i}`}>
                      <td className="p-2"><input type="checkbox" checked={r.checked} onChange={(e) => setRow(i, { checked: e.target.checked })} className="h-4 w-4 accent-emerald-600" data-testid={`library-import-check-${i}`} /></td>
                      <td className="p-1"><Input value={r.designation} onChange={(e) => setRow(i, { designation: e.target.value })} className="h-7 text-xs" /></td>
                      <td className="p-2 num">{r.unit}</td>
                      <td className="p-1"><Input type="number" step="0.01" value={r.unit_price_ht} onChange={(e) => setRow(i, { unit_price_ht: e.target.value })} className="h-7 text-xs num text-right" data-testid={`library-import-price-${i}`} /></td>
                      <td className="p-1"><Input type="number" step="0.01" value={r.cost_price_ht ?? ""} placeholder="—" onChange={(e) => setRow(i, { cost_price_ht: e.target.value })} className="h-7 text-xs num text-right" /></td>
                      <td className="p-2 text-muted-foreground">
                        {r.existing_price != null ? <span className="flex items-center gap-1 text-amber-600">màj {eur(r.existing_price)}</span> : <span className="flex items-center gap-1 text-emerald-600"><CheckCircle2 className="h-3 w-3" /> nouveau</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={reset} className="rounded-sm" data-testid="library-import-back">Autres fichiers</Button>
              <Button onClick={confirm} disabled={busy} className="rounded-sm gap-2" data-testid="library-import-confirm">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />} Ajouter à ma bibliothèque
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
