import { useRef, useState } from "react";
import { FileUp, Loader2, CheckCircle2, Upload } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

export default function LibraryImportDialog({ open, onClose, onDone }) {
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [rows, setRows] = useState(null);
  const [category, setCategory] = useState("");
  const inputRef = useRef(null);

  const reset = () => { setFiles([]); setRows(null); setCategory(""); };

  const analyse = async () => {
    if (!files.length) { toast.error("Escolha pelo menos um PDF"); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const { data } = await api.post("/library/import-pdf/preview", fd, { timeout: 180000 });
      const flat = [];
      (data.items || []).forEach((it) => {
        if (!it.ok) { toast.error(`${it.file} : ${it.error || "leitura impossível"}`); return; }
        it.lines.forEach((l) => flat.push({ ...l, file: it.file, checked: true }));
      });
      if (!flat.length) toast.error("Nenhum trabalho com preço encontrado nestes documentos");
      setRows(flat);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Análise impossível");
    } finally { setBusy(false); }
  };

  const confirm = async () => {
    const chosen = (rows || []).filter((r) => r.checked);
    if (!chosen.length) { toast.error("Selecione pelo menos uma linha"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/library/import-pdf/confirm", {
        category, lines: chosen.map(({ checked, file, existing_price, ...l }) => l),
      });
      toast.success(`${data.created} artigo(s) adicionado(s), ${data.updated} atualizado(s)`);
      onDone?.(); reset(); onClose();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível importar");
    } finally { setBusy(false); }
  };

  const setRow = (i, patch) => setRows((rs) => rs.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  const allChecked = rows?.length && rows.every((r) => r.checked);

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) { reset(); onClose(); } }}>
      <DialogContent className="max-w-3xl" data-testid="library-import-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><FileUp className="h-5 w-5 text-primary" /> Retomar os meus orçamentos antigos</DialogTitle>
        </DialogHeader>
        <p className="text-xs text-muted-foreground -mt-2">
          Carregue os seus orçamentos antigos em PDF (Tolteck, Obat, Batappli, Excel/Word exportados…). A IA extrai os seus artigos, unidades e preços para reconstruir a sua biblioteca — não começa do zero.
        </p>

        {!rows && (
          <div className="space-y-3">
            <div className="border-2 border-dashed border-border rounded-md p-6 text-center cursor-pointer hover:border-primary transition-colors"
                 onClick={() => inputRef.current?.click()} data-testid="library-import-dropzone">
              <Upload className="h-6 w-6 mx-auto text-muted-foreground mb-2" />
              <p className="text-sm">{files.length ? `${files.length} ficheiro(s) selecionado(s)` : "Clique para escolher os seus PDF (até 20)"}</p>
              {files.length > 0 && <p className="text-[11px] text-muted-foreground mt-1 truncate">{files.map((f) => f.name).join(" · ")}</p>}
              <input ref={inputRef} type="file" accept="application/pdf" multiple className="hidden"
                     onChange={(e) => setFiles(Array.from(e.target.files || []).slice(0, 20))} data-testid="library-import-input" />
            </div>
            <Button onClick={analyse} disabled={busy || !files.length} className="rounded-sm gap-2 w-full" data-testid="library-import-analyse">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <FileUp className="h-4 w-4" />} {busy ? "Leitura IA em curso…" : "Analisar os meus orçamentos"}
            </Button>
          </div>
        )}

        {rows && (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3 text-xs">
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={!!allChecked} onChange={(e) => setRows((rs) => rs.map((r) => ({ ...r, checked: e.target.checked })))}
                       data-testid="library-import-check-all" className="h-4 w-4 accent-emerald-600" />
                {rows.filter((r) => r.checked).length} / {rows.length} linhas retidas
              </label>
              <Input value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Especialidade / categoria (opcional, senão título do orçamento)"
                     className="h-8 text-xs max-w-xs" data-testid="library-import-category" />
            </div>
            <div className="max-h-[50vh] overflow-y-auto border border-border rounded-md">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-background">
                  <tr className="text-left text-muted-foreground border-b border-border">
                    <th className="p-2 w-8" /><th className="p-2">Designação</th><th className="p-2 w-16">Un.</th>
                    <th className="p-2 w-24 text-right">PU HT</th><th className="p-2 w-24 text-right">Custo produção</th><th className="p-2 w-28">Atual</th>
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
                        {r.existing_price != null ? <span className="flex items-center gap-1 text-amber-600">atual. {eur(r.existing_price)}</span> : <span className="flex items-center gap-1 text-emerald-600"><CheckCircle2 className="h-3 w-3" /> novo</span>}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={reset} className="rounded-sm" data-testid="library-import-back">Outros ficheiros</Button>
              <Button onClick={confirm} disabled={busy} className="rounded-sm gap-2" data-testid="library-import-confirm">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <CheckCircle2 className="h-4 w-4" />} Adicionar à minha biblioteca
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
