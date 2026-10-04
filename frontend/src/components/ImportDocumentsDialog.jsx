import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger,
} from "@/components/ui/dialog";
import {
  Select, SelectTrigger, SelectValue, SelectContent, SelectItem,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import { Upload, FileUp, Loader2, CheckCircle2, XCircle, FileText, Trash2, ArrowLeft } from "lucide-react";

const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const STATUS_LABELS = { draft: "Brouillon", sent: "Enviado", signed: "Accepté", refused: "Refusé", paid: "Payé" };
const lineTtc = (l) => (Number(l.qty) || 0) * (Number(l.unit_price_ht) || 0) * (1 + (Number(l.vat_rate) || 0) / 100);
const itemTtc = (it) => (it.lines || []).reduce((s, l) => s + lineTtc(l), 0);

/**
 * Import de devis/factures PDF d'autres logiciels, avec aperçu éditable.
 * Props : triggerLabel, triggerVariant, onImported (callback après import).
 */
export function ImportDocumentsDialog({ triggerLabel = "Importer des PDF", triggerVariant = "outline", onImported }) {
  const [open, setOpen] = useState(false);
  const [phase, setPhase] = useState("idle"); // idle | preview | results
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("sent");
  const [items, setItems] = useState([]); // aperçu éditable
  const [results, setResults] = useState(null);
  const [didImport, setDidImport] = useState(false);
  const inputRef = useRef(null);
  const nav = useNavigate();

  const reset = () => { setPhase("idle"); setItems([]); setResults(null); };

  const handleFiles = async (fileList) => {
    const files = Array.from(fileList || []).filter((f) => f && f.name.toLowerCase().endsWith(".pdf"));
    if (!files.length) { toast.error("Sélectionnez un ou plusieurs fichiers PDF"); return; }
    setBusy(true);
    const tid = toast.loading(files.length > 1 ? `Lecture de ${files.length} PDF…` : "Lecture du PDF…");
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const { data } = await api.post("/documents/import-pdf/preview", fd);
      setItems((data.items || []).map((it) => ({ ...it, client: it.client || {}, lines: it.lines || [] })));
      setPhase("preview");
      const okc = (data.items || []).filter((i) => i.ok).length;
      toast.success(`${okc} documento(s) legível(eis) — verifique antes de validar`, { id: tid });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Leitura impossível", { id: tid });
    } finally { setBusy(false); }
  };

  const setItem = (i, patch) => setItems((arr) => arr.map((it, j) => j === i ? { ...it, ...patch } : it));
  const setClient = (i, patch) => setItems((arr) => arr.map((it, j) => j === i ? { ...it, client: { ...it.client, ...patch } } : it));
  const setLine = (i, li, patch) => setItems((arr) => arr.map((it, j) =>
    j === i ? { ...it, lines: it.lines.map((l, k) => k === li ? { ...l, ...patch } : l) } : it));
  const removeLine = (i, li) => setItems((arr) => arr.map((it, j) =>
    j === i ? { ...it, lines: it.lines.filter((_, k) => k !== li) } : it));
  const removeItem = (i) => setItems((arr) => arr.filter((_, j) => j !== i));

  const confirmImport = async () => {
    const payload = items.filter((it) => it.ok && (it.lines || []).length > 0);
    if (!payload.length) { toast.error("Nenhum documento válido para importar"); return; }
    setBusy(true);
    const tid = toast.loading("Création des documents…");
    try {
      const { data } = await api.post("/documents/import-pdf/confirm", { status, items: payload });
      setResults(data);
      setPhase("results");
      if (data.imported > 0) { toast.success(`${data.imported}/${data.total} documento(s) criado(s)`, { id: tid }); setDidImport(true); }
      else toast.error("Nenhum documento criado", { id: tid });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossível importar", { id: tid });
    } finally { setBusy(false); }
  };

  const okItems = items.filter((it) => it.ok);
  const koItems = items.filter((it) => !it.ok);

  return (
    <Dialog open={open} onOpenChange={(o) => {
      setOpen(o);
      if (!o) { reset(); if (didImport) { onImported && onImported(); setDidImport(false); } }
    }}>
      <DialogTrigger asChild>
        <Button variant={triggerVariant} className="rounded-sm gap-2" data-testid="import-docs-trigger">
          <FileUp className="h-4 w-4" /> {triggerLabel}
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-3xl max-h-[90vh] flex flex-col" data-testid="import-docs-dialog"
        onPointerDownOutside={(e) => { if (busy || phase !== "idle") e.preventDefault(); }}
        onInteractOutside={(e) => { if (busy || phase !== "idle") e.preventDefault(); }}>
        <DialogHeader>
          <DialogTitle>Importer des devis / factures PDF</DialogTitle>
          <DialogDescription>
            Reprenez vos documents faits sur un autre logiciel. ConstruPilot lit chaque PDF, crée le
            client et convertit les lignes ; vous vérifiez l'aperçu avant de valider.
          </DialogDescription>
        </DialogHeader>

        <input ref={inputRef} type="file" accept="application/pdf" multiple className="hidden"
               onChange={(e) => { handleFiles(e.target.files); e.target.value = ""; }}
               data-testid="import-docs-input" />

        {/* PHASE 1 — choix statut + fichiers */}
        {phase === "idle" && (
          <div className="space-y-3">
            <div className="flex items-center gap-2">
              <label className="text-sm text-muted-foreground whitespace-nowrap">Estado a aplicar</label>
              <Select value={status} onValueChange={setStatus}>
                <SelectTrigger className="rounded-sm h-9" data-testid="import-docs-status"><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="draft">Brouillon</SelectItem>
                  <SelectItem value="sent">Envoyé</SelectItem>
                  <SelectItem value="accepted">Accepté / signé</SelectItem>
                  <SelectItem value="refused">Refusé</SelectItem>
                  <SelectItem value="paid">Payé (facture)</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <button type="button" disabled={busy} onClick={() => inputRef.current?.click()}
              className="w-full border-2 border-dashed border-primary/40 rounded-lg py-10 flex flex-col items-center gap-2 text-muted-foreground hover:bg-primary/5 transition-colors disabled:opacity-60"
              data-testid="import-docs-dropzone">
              {busy ? <Loader2 className="h-8 w-8 animate-spin text-primary" /> : <Upload className="h-8 w-8 text-primary" />}
              <span className="text-sm font-semibold text-foreground">
                {busy ? "Lecture des PDF en cours…" : "Clique para escolher os seus PDF"}
              </span>
              <span className="text-xs">Plusieurs fichiers acceptés · devis, factures, avoirs</span>
            </button>
          </div>
        )}

        {/* PHASE 2 — aperçu éditable */}
        {phase === "preview" && (
          <div className="space-y-3 overflow-auto flex-1" data-testid="import-docs-preview">
            {koItems.map((it, i) => (
              <div key={`ko-${i}`} className="flex items-center gap-2 text-sm border border-red-500/30 rounded-sm px-3 py-2 text-red-600">
                <XCircle className="h-4 w-4 shrink-0" /> {it.file} — {it.error}
              </div>
            ))}
            {okItems.map((it) => {
              const i = items.indexOf(it);
              return (
                <div key={i} className="border border-border rounded-sm p-3 space-y-2" data-testid={`import-preview-item-${i}`}>
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-sm font-semibold truncate flex items-center gap-2">
                      <FileText className="h-4 w-4 text-primary" /> {it.file}
                    </p>
                    <button onClick={() => removeItem(i)} className="text-muted-foreground hover:text-red-600"
                            data-testid={`import-preview-remove-${i}`}><Trash2 className="h-4 w-4" /></button>
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    <Select value={it.doc_type || "quote"} onValueChange={(v) => setItem(i, { doc_type: v })}>
                      <SelectTrigger className="h-8 rounded-sm text-xs" data-testid={`import-preview-type-${i}`}><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="quote">Orçamento</SelectItem>
                        <SelectItem value="invoice">Facture</SelectItem>
                        <SelectItem value="credit_note">Avoir</SelectItem>
                      </SelectContent>
                    </Select>
                    <Input value={it.number || ""} onChange={(e) => setItem(i, { number: e.target.value })}
                           placeholder="N° document" className="h-8 rounded-sm text-xs" data-testid={`import-preview-number-${i}`} />
                    <Input value={it.client?.company || ""} onChange={(e) => setClient(i, { company: e.target.value })}
                           placeholder="Société client" className="h-8 rounded-sm text-xs" data-testid={`import-preview-company-${i}`} />
                    <Input value={it.client?.email || ""} onChange={(e) => setClient(i, { email: e.target.value })}
                           placeholder="E-mail client" className="h-8 rounded-sm text-xs" data-testid={`import-preview-email-${i}`} />
                  </div>
                  <div className="space-y-1">
                    {(it.lines || []).map((l, li) => (
                      <div key={li} className="flex items-center gap-1.5" data-testid={`import-preview-line-${i}-${li}`}>
                        <Input value={l.designation || ""} onChange={(e) => setLine(i, li, { designation: e.target.value })}
                               placeholder="Désignation" className="h-7 rounded-sm text-xs flex-1" />
                        <Input type="number" value={l.qty ?? 0} onChange={(e) => setLine(i, li, { qty: e.target.value })}
                               className="h-7 rounded-sm text-xs w-16" title="Qté" />
                        <Input type="number" value={l.unit_price_ht ?? 0} onChange={(e) => setLine(i, li, { unit_price_ht: e.target.value })}
                               className="h-7 rounded-sm text-xs w-20" title="PU HT" />
                        <button onClick={() => removeLine(i, li)} className="text-muted-foreground hover:text-red-600 shrink-0"
                                data-testid={`import-preview-line-del-${i}-${li}`}><Trash2 className="h-3.5 w-3.5" /></button>
                      </div>
                    ))}
                  </div>
                  <p className="text-xs text-right text-muted-foreground">
                    {(it.lines || []).length} ligne(s) · Total TTC ≈ <b className="text-foreground">{eur(itemTtc(it))}</b>
                  </p>
                </div>
              );
            })}
            {okItems.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-6">Aucun document lisible dans ces PDF.</p>
            )}
          </div>
        )}
        {phase === "preview" && (
          <div className="flex gap-2 pt-1">
            <Button variant="outline" className="gap-2" onClick={reset} data-testid="import-preview-back">
              <ArrowLeft className="h-4 w-4" /> Retour
            </Button>
            <Button className="flex-1 gap-2" disabled={busy || okItems.length === 0} onClick={confirmImport}
                    data-testid="import-preview-confirm">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />}
              Valider et créer ({okItems.length})
            </Button>
          </div>
        )}

        {/* PHASE 3 — résultats */}
        {phase === "results" && results && (
          <div className="space-y-2 max-h-80 overflow-auto" data-testid="import-docs-results">
            <p className="text-sm font-semibold">{results.imported}/{results.total} document(s) créé(s)</p>
            {(results.results || []).map((r, i) => (
              <div key={i} className="flex items-center gap-2 text-sm border border-border rounded-sm px-3 py-2"
                   data-testid={`import-docs-result-${i}`}>
                {r.ok ? <CheckCircle2 className="h-4 w-4 text-primary shrink-0" /> : <XCircle className="h-4 w-4 text-destructive shrink-0" />}
                <div className="min-w-0 flex-1">
                  <p className="truncate font-medium">{r.file}</p>
                  {r.ok ? (
                    <p className="text-xs text-muted-foreground">
                      {r.doc_type === "invoice" ? "Fatura" : r.doc_type === "credit_note" ? "Avoir" : "Orçamento"}
                      {r.number ? ` n° ${r.number}` : ""} · {r.lines} ligne(s) · {eur(r.ttc)}
                      {r.status ? ` · ${STATUS_LABELS[r.status] || r.status}` : ""}
                    </p>
                  ) : <p className="text-xs text-destructive">{r.error}</p>}
                </div>
                {r.ok && (
                  <Button size="sm" variant="ghost" className="gap-1 shrink-0"
                          onClick={() => { setOpen(false); nav(`/devis-editeur/${r.doc_id}`); }}
                          data-testid={`import-docs-open-${i}`}>
                    <FileText className="h-3.5 w-3.5" /> Abrir
                  </Button>
                )}
              </div>
            ))}
            <div className="flex gap-2 pt-2">
              <Button variant="outline" className="flex-1" onClick={reset} data-testid="import-docs-again">Importer d'autres PDF</Button>
              <Button className="flex-1" onClick={() => setOpen(false)} data-testid="import-docs-done">Terminé</Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default ImportDocumentsDialog;
