import { useRef, useState } from "react";
import { FileSpreadsheet, Upload, Download, Loader2, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { toast } from "sonner";

const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { style: "currency", currency: "EUR", maximumFractionDigits: 0 });

// Import Excel architecte (DPGF/BPU/DQE) → remplissage automatique des prix (IA).
export const DpgfImport = () => {
  const fileRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const [res, setRes] = useState(null);

  const upload = async (file) => {
    if (!file) return;
    setBusy(true); setRes(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/pro/dpgf/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setRes(data);
      toast.success(`${data.filled}/${data.line_count} lignes chiffrées — total ${eur(data.grand_total_ht)} HT`);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import impossible (fichier .xlsx attendu)");
    } finally { setBusy(false); }
  };

  const download = async () => {
    try {
      const { data } = await api.get(res.download_url, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url; a.download = "dpgf_rempli.xlsx"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Téléchargement impossible"); }
  };

  return (
    <div className="surface p-6" data-testid="dpgf-import">
      <div className="flex items-center gap-2 mb-1">
        <FileSpreadsheet className="h-5 w-5 text-primary" />
        <h3 className="font-display font-bold text-lg">Import DPGF / BPU architecte</h3>
        <span className="ml-2 text-[10px] font-bold uppercase tracking-wider bg-primary/10 text-primary px-2 py-0.5 rounded-full">Pro Business</span>
      </div>
      <p className="text-sm text-muted-foreground mb-4">
        Importa o ficheiro Excel do arquiteto (mapa de trabalhos e quantidades). O ConstruPilot deteta as colunas e
        <span className="text-foreground"> remplit automatiquement les prix unitaires</span> (estimation IA), puis calcule les totaux.
      </p>

      <input ref={fileRef} type="file" accept=".xlsx" hidden data-testid="dpgf-file-input"
             onChange={(e) => upload(e.target.files?.[0])} />
      <div className="flex flex-wrap gap-2">
        <Button onClick={() => fileRef.current?.click()} disabled={busy} className="gap-2 rounded-sm" data-testid="dpgf-upload-btn">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          {busy ? "Analyse en cours…" : "Importer un Excel"}
        </Button>
        {res && (
          <Button variant="outline" onClick={download} className="gap-2 rounded-sm" data-testid="dpgf-download-btn">
            <Download className="h-4 w-4" /> Descarregar Excel preenchido
          </Button>
        )}
      </div>

      {res && (
        <div className="mt-4" data-testid="dpgf-result">
          <div className="flex flex-wrap gap-4 text-sm mb-2">
            <span>Lignes : <b>{res.line_count}</b></span>
            <span className="text-primary inline-flex items-center gap-1"><Sparkles className="h-3.5 w-3.5" /> Chiffrées : <b>{res.filled}</b></span>
            {res.from_library > 0 && <span className="text-emerald-600">Vos prix : <b>{res.from_library}</b></span>}
            {res.from_ai > 0 && <span className="text-amber-600">IA : <b>{res.from_ai}</b></span>}
            <span>Total HT : <b>{eur(res.grand_total_ht)}</b></span>
          </div>
          <div className="max-h-64 overflow-auto rounded-sm border border-border">
            <table className="w-full text-xs">
              <thead className="bg-secondary/40 sticky top-0">
                <tr><th className="text-left p-2">Désignation</th><th className="p-2">Qté</th><th className="p-2">U.</th><th className="p-2 text-right">PU HT</th><th className="p-2">Source</th><th className="p-2 text-right">Total HT</th></tr>
              </thead>
              <tbody>
                {res.lines.map((l, i) => (
                  <tr key={i} className="border-t border-border/60">
                    <td className="p-2">{l.designation}</td>
                    <td className="p-2 text-center num">{l.qty ?? "—"}</td>
                    <td className="p-2 text-center">{l.unit || "—"}</td>
                    <td className="p-2 text-right num">{l.pu ? eur(l.pu) : "—"}</td>
                    <td className="p-2 text-center">
                      {l.price_source === "bibliotheque"
                        ? <span className="text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-600 px-1.5 py-0.5 rounded-full">Votre prix</span>
                        : l.price_source === "ia"
                          ? <span className="text-[10px] font-bold uppercase bg-amber-500/10 text-amber-600 px-1.5 py-0.5 rounded-full">IA</span>
                          : "—"}
                    </td>
                    <td className="p-2 text-right num">{l.total ? eur(l.total) : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-[11px] text-muted-foreground">Prix « Votre prix » = issus de votre bibliothèque ; « IA » = estimation à valider avant envoi au client.</p>
        </div>
      )}
    </div>
  );
};
