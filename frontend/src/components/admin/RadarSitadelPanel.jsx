import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { Loader2, Upload, Database, Trash2, FileSpreadsheet, CheckCircle2, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { toast } from "sonner";

export default function RadarSitadelPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [file, setFile] = useState(null);
  const [replace, setReplace] = useState(true);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);
  const inputRef = useRef(null);

  const loadStatus = () => {
    setLoading(true);
    api.get("/radar/admin/permits/count")
      .then(({ data }) => setStatus(data))
      .catch(() => toast.error("Statut indisponible"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { loadStatus(); }, []);

  const doImport = async () => {
    if (!file) { toast.error("Choisissez un fichier CSV"); return; }
    setImporting(true); setResult(null);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post(`/radar/admin/import-sitadel?replace=${replace}`, fd);
      setResult(data);
      toast.success(`Import terminé : ${data.inserted} permis`);
      loadStatus();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Import impossible");
    } finally { setImporting(false); }
  };

  const doClear = async () => {
    if (!window.confirm("Vider la base des permis importés et repasser sur l'échantillon de démonstration ?")) return;
    try {
      const { data } = await api.delete("/radar/admin/permits");
      toast.success(`${data.deleted} permis supprimés`);
      setResult(null); loadStatus();
    } catch { toast.error("Suppression impossible"); }
  };

  const usingReal = status && status.count > 0;

  return (
    <div className="space-y-5" data-testid="admin-radar-panel">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-display font-bold text-lg">Radar Chantiers — données SITADEL</h3>
          <p className="text-sm text-muted-foreground">Importez le fichier trimestriel des autorisations d'urbanisme. Le Radar utilise ces données réelles ; sinon il retombe sur l'échantillon de démonstration (Val-d'Oise).</p>
        </div>
        <Button variant="outline" size="sm" className="rounded-sm gap-2" onClick={loadStatus} data-testid="admin-radar-refresh">
          <RefreshCw className="h-4 w-4" /> Actualiser
        </Button>
      </div>

      <div className="surface rounded-xl p-4 flex items-center gap-3" data-testid="admin-radar-status">
        <span className={`h-10 w-10 grid place-items-center rounded-lg ${usingReal ? "bg-emerald-500/15 text-emerald-600" : "bg-amber-500/15 text-amber-600"}`}>
          <Database className="h-5 w-5" />
        </span>
        {loading ? <Loader2 className="h-5 w-5 animate-spin text-primary" /> : (
          <div className="text-sm">
            <div className="font-bold">{usingReal ? `${status.count} permis en base` : "Aucune donnée importée"}</div>
            <div className="text-xs text-muted-foreground">Source active : <b>{status?.using}</b></div>
          </div>
        )}
        {usingReal && (
          <Button variant="outline" size="sm" className="rounded-sm gap-1 ml-auto text-red-600 border-red-200 hover:bg-red-50" onClick={doClear} data-testid="admin-radar-clear">
            <Trash2 className="h-4 w-4" /> Vider (repasser en démo)
          </Button>
        )}
      </div>

      <div className="surface rounded-xl p-5 space-y-3">
        <div className="flex items-center gap-2 text-sm font-bold"><Upload className="h-4 w-4 text-primary" /> Importer un fichier SITADEL (CSV)</div>
        <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden"
          onChange={(e) => { setFile(e.target.files?.[0] || null); setResult(null); }} data-testid="admin-radar-file" />
        <div className="flex items-center gap-3 flex-wrap">
          <Button variant="outline" className="rounded-sm gap-2" onClick={() => inputRef.current?.click()} data-testid="admin-radar-choose">
            <FileSpreadsheet className="h-4 w-4" /> {file ? file.name : "Choisir un fichier .csv"}
          </Button>
          <label className="flex items-center gap-1.5 text-sm text-muted-foreground cursor-pointer">
            <input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} data-testid="admin-radar-replace" />
            Remplacer les données existantes
          </label>
          <Button className="rounded-sm gap-2 ml-auto" onClick={doImport} disabled={importing || !file} data-testid="admin-radar-import">
            {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importer
          </Button>
        </div>
        <p className="text-[11px] text-muted-foreground">
          Colonnes reconnues (insensible à la casse, séparateur ; ou ,) : <span className="font-mono">commune, cp, dep, lat, lon, adresse, num, type, nature, batiment, surf_created, logements, date_depot, date_auth, statut, mo</span>.
          Si lat/lon sont absents, l'adresse/commune est géocodée automatiquement (BAN).
        </p>
        {result && (
          <div className="rounded-lg bg-emerald-500/10 text-emerald-700 p-3 text-sm flex items-center gap-2" data-testid="admin-radar-result">
            <CheckCircle2 className="h-4 w-4" />
            {result.inserted} importés · {result.skipped} ignorés (sans géoloc) · {result.total_in_db} au total.
          </div>
        )}
      </div>
    </div>
  );
}
