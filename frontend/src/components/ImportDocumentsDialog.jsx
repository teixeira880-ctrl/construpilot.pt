import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FileUp, Loader2, CheckCircle2, XCircle, FileText } from "lucide-react";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

/**
 * Import de devis/factures PDF d'autres logiciels.
 * Props :
 *  - triggerLabel : texte du bouton
 *  - triggerVariant : variante du bouton
 *  - onImported : callback après import réussi
 */
export function ImportDocumentsDialog({ triggerLabel = "Importer des PDF", triggerVariant = "outline", onImported }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [results, setResults] = useState(null);
  const [didImport, setDidImport] = useState(false);
  const inputRef = useRef(null);
  const nav = useNavigate();

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f && f.name.toLowerCase().endsWith(".pdf"));
    if (!files.length) { toast.error("Sélectionnez un ou plusieurs fichiers PDF"); return; }
    setBusy(true);
    setResults(null);
    const tid = toast.loading(files.length > 1 ? `Import de ${files.length} PDF…` : "Import du PDF…");
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const { data } = await api.post("/documents/import-pdf", fd, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      setResults(data);
      if (data.imported > 0) {
        toast.success(`${data.imported}/${data.total} document(s) importé(s)`, { id: tid });
        setDidImport(true);
      } else {
        toast.error("Aucun document n'a pu être importé", { id: tid });
      }
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import impossible", { id: tid });
    } finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => {
      setOpen(o);
      if (!o) { setResults(null); if (didImport) { onImported && onImported(); setDidImport(false); } }
    }}>
      <DialogTrigger asChild>
        <Button variant={triggerVariant} className="rounded-sm gap-2" data-testid="import-docs-trigger">
          <FileUp className="h-4 w-4" /> {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-lg" data-testid="import-docs-dialog"
        onPointerDownOutside={(e) => { if (busy || results) e.preventDefault(); }}
        onInteractOutside={(e) => { if (busy || results) e.preventDefault(); }}>
        <DialogHeader>
          <DialogTitle>Importer des devis / factures PDF</DialogTitle>
          <DialogDescription>
            Reprenez vos documents faits sur un autre logiciel. Pour chaque PDF, ConstruPilot crée
            automatiquement le client, convertit les lignes au format ConstruPilot et conserve le
            numéro d'origine.
          </DialogDescription>
        </DialogHeader>

        <input ref={inputRef} type="file" accept="application/pdf" multiple className="hidden"
               onChange={(e) => { handleFiles(e.target.files); e.target.value = ""; }}
               data-testid="import-docs-input" />

        {!results && (
          <button
            type="button"
            disabled={busy}
            onClick={() => inputRef.current?.click()}
            className="w-full border-2 border-dashed border-primary/40 rounded-lg py-10 flex flex-col items-center gap-2 text-muted-foreground hover:bg-primary/5 transition-colors disabled:opacity-60"
            data-testid="import-docs-dropzone"
          >
            {busy ? <Loader2 className="h-8 w-8 animate-spin text-primary" /> : <Upload className="h-8 w-8 text-primary" />}
            <span className="text-sm font-semibold text-foreground">
              {busy ? "Lecture des PDF en cours…" : "Cliquez pour choisir vos PDF"}
            </span>
            <span className="text-xs">Plusieurs fichiers acceptés · devis, factures, avoirs</span>
          </button>
        )}

        {results && (
          <div className="space-y-2 max-h-80 overflow-auto" data-testid="import-docs-results">
            <p className="text-sm font-semibold">
              {results.imported}/{results.total} document(s) importé(s)
            </p>
            {(results.results || []).map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-sm border border-border rounded-sm px-3 py-2"
                   data-testid={`import-docs-result-${i}`}>
                {r.ok ? <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
                      : <XCircle className="h-4 w-4 text-destructive shrink-0" />}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{r.file}</p>
                  {r.ok ? (
                    <p className="text-xs text-muted-foreground">
                      {r.doc_type === "invoice" ? "Facture" : r.doc_type === "credit_note" ? "Avoir" : "Devis"}
                      {r.number ? ` n° ${r.number}` : ""} · {r.lines} ligne(s) · {eur(r.ttc)}
                    </p>
                  ) : (
                    <p className="text-xs text-destructive">{r.error}</p>
                  )}
                </div>
                {r.ok && (
                  <Button size="sm" variant="ghost" className="gap-1 shrink-0"
                          onClick={() => { setOpen(false); nav(`/devis-editeur/${r.doc_id}`); }}
                          data-testid={`import-docs-open-${i}`}>
                    <FileText className="h-3.5 w-3.5" /> Ouvrir
                  </Button>
                )}
              </div>
            ))}
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={() => setResults(null)}
                      data-testid="import-docs-again">Importer d'autres PDF</Button>
              <Button className="flex-1" onClick={() => setOpen(false)} data-testid="import-docs-done">Terminé</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default ImportDocumentsDialog;
