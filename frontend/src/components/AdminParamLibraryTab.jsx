import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Boxes, Upload, Trash2, Loader2, Search, Calculator, Save, Plus, MapPin, Clock, Package,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";
const LEVELS = ["bas", "moyen", "haut"];

export default function AdminParamLibraryTab() {
  const [ouvrages, setOuvrages] = useState([]);
  const [meta, setMeta] = useState({});
  const [totalLines, setTotalLines] = useState(0);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef(null);

  const [detail, setDetail] = useState(null);
  const [level, setLevel] = useState("moyen");
  const [region, setRegion] = useState("standard");
  const [margin, setMargin] = useState(25);

  const [rates, setRates] = useState([]);
  const [coefs, setCoefs] = useState([]);
  const [materials, setMaterials] = useState([]);
  const [matQ, setMatQ] = useState("");

  const load = async (query = "") => {
    setBusy(true);
    try {
      const { data } = await api.get("/admin/param-library/ouvrages", { params: { q: query } });
      setOuvrages(data.ouvrages || []); setMeta(data.meta || {}); setTotalLines(data.total_lines || 0);
    } finally { setBusy(false); }
  };
  const loadTables = async () => {
    const [r, c, m] = await Promise.all([
      api.get("/admin/param-library/labor-rates"),
      api.get("/admin/param-library/regional-coefs"),
      api.get("/admin/param-library/materials"),
    ]);
    setRates(r.data.rates || []); setCoefs(c.data.coefs || []); setMaterials(m.data.materials || []);
  };
  useEffect(() => { load(); loadTables(); }, []);

  const onImport = async (e) => {
    const file = e.target.files?.[0]; e.target.value = "";
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData(); fd.append("file", file);
      const { data } = await api.post("/admin/param-library/import", fd,
        { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${data.ouvrages} ouvrages · ${data.lines} lignes importés`);
      await load(q); await loadTables();
    } catch (err) { toast.error(err?.response?.data?.detail || "Import impossible"); }
    finally { setUploading(false); }
  };

  const clearAll = async () => {
    if (!window.confirm("Vider toute la bibliothèque paramétrique ?")) return;
    await api.delete("/admin/param-library"); toast.success("Vidée"); await load();
  };

  const openDetail = async (base_code, lvl = level, rg = region, mg = margin) => {
    try {
      const { data } = await api.get(`/admin/param-library/ouvrages/${base_code}`,
        { params: { level: lvl, region: rg, margin_pct: mg } });
      setDetail(data);
    } catch { toast.error("Calcul impossible"); }
  };
  useEffect(() => { if (detail) openDetail(detail.base_code, level, region, margin); /* eslint-disable-next-line */ }, [level, region, margin]);

  const saveRates = async () => {
    await api.put("/admin/param-library/labor-rates", rates.map((r) => ({
      metier: r.metier, low: Number(r.low), mid: Number(r.mid), high: Number(r.high) })));
    toast.success("Taux horaires enregistrés");
  };
  const saveCoefs = async () => {
    await api.put("/admin/param-library/regional-coefs", coefs.map((c) => ({
      region: c.region, label: c.label, coef: Number(c.coef) })));
    toast.success("Coefficients enregistrés");
  };
  const saveMaterial = async (m) => {
    await api.put(`/admin/param-library/materials/${m.mat_id}`, { name: m.name, unit: m.unit, price: Number(m.price) });
    toast.success("Matériau mis à jour");
  };

  return (
    <div className="space-y-8" data-testid="admin-param-library">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-bold flex items-center gap-2">
            <Boxes className="h-5 w-5 text-primary" /> Bibliothèque paramétrique (ouvrages composés)
          </h3>
          <p className="text-sm text-muted-foreground max-w-2xl mt-1">
            Ouvrages composés avec formules de quantité, main d'œuvre et % pertes. L'IA calcule le
            <b> déboursé sec → coût de revient → prix de vente</b> selon la gamme, la région et la marge.
            L'import <b>remplace</b> la bibliothèque existante.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          {totalLines > 0
            ? <Badge className="bg-emerald-600 hover:bg-emerald-600" data-testid="param-count">{meta.count_ouvrages || "?"} ouvrages · {totalLines} lignes</Badge>
            : <Badge variant="outline" className="text-amber-600 border-amber-400">Vide</Badge>}
          {meta.imported_at && <span className="text-[11px] text-muted-foreground">{meta.last_file}</span>}
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls,.xlsm" className="hidden"
               onChange={onImport} data-testid="param-file-input" />
        <Button onClick={() => fileRef.current?.click()} disabled={uploading}
                className="rounded-sm gap-2 bg-primary" data-testid="param-import-btn">
          {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />}
          Importer (remplacer) CSV / Excel
        </Button>
        {totalLines > 0 && (
          <Button variant="ghost" onClick={clearAll} className="rounded-sm gap-2 text-destructive"
                  data-testid="param-clear-btn"><Trash2 className="h-4 w-4" /> Vider</Button>
        )}
      </div>

      {/* Ouvrages */}
      <div className="space-y-3">
        <div className="relative max-w-sm">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === "Enter" && load(q)}
                 placeholder="Rechercher un ouvrage / famille / métier…" className="rounded-sm pl-9" data-testid="param-search" />
        </div>
        <div className="border border-border rounded-sm overflow-hidden max-h-[420px] overflow-y-auto">
          <Table data-testid="param-ouvrages-table">
            <TableHeader><TableRow className="bg-secondary/60 hover:bg-secondary/60">
              <TableHead>Code</TableHead><TableHead>Famille</TableHead><TableHead>Métier</TableHead>
              <TableHead className="text-center">Lignes</TableHead><TableHead className="text-right">Calcul</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {busy ? <TableRow><TableCell colSpan={5} className="text-center py-8"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></TableCell></TableRow>
                : ouvrages.length === 0 ? <TableRow><TableCell colSpan={5} className="text-center py-8 text-muted-foreground">Aucun ouvrage. Importez le fichier.</TableCell></TableRow>
                : ouvrages.map((o) => (
                  <TableRow key={o.base_code} className="cursor-pointer" onClick={() => openDetail(o.base_code)}>
                    <TableCell className="text-xs font-mono">{o.base_code}</TableCell>
                    <TableCell className="font-medium">{o.famille}</TableCell>
                    <TableCell className="text-xs">{o.metier_mo}</TableCell>
                    <TableCell className="text-center text-xs">{o.lines}</TableCell>
                    <TableCell className="text-right"><Calculator className="h-4 w-4 inline text-primary" /></TableCell>
                  </TableRow>
                ))}
            </TableBody>
          </Table>
        </div>
      </div>

      {/* Taux horaires + coefficients régionaux */}
      <div className="grid md:grid-cols-2 gap-6">
        <div className="border border-border rounded-sm p-4 space-y-3" data-testid="param-rates">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold flex items-center gap-2"><Clock className="h-4 w-4 text-primary" /> Taux horaires 2026 (€/h HT)</h4>
            <Button size="sm" onClick={saveRates} className="rounded-sm gap-1 h-8" data-testid="param-rates-save"><Save className="h-3.5 w-3.5" /> Enregistrer</Button>
          </div>
          <div className="max-h-64 overflow-y-auto space-y-1">
            {rates.map((r, i) => (
              <div key={r.metier} className="grid grid-cols-4 gap-2 items-center text-sm">
                <span className="truncate">{r.metier}</span>
                {["low", "mid", "high"].map((k) => (
                  <input key={k} type="number" value={r[k]} onChange={(e) => { const v = [...rates]; v[i] = { ...r, [k]: e.target.value }; setRates(v); }}
                         className="rounded-sm border border-input bg-background px-2 py-1 text-right num" />
                ))}
              </div>
            ))}
            <div className="grid grid-cols-4 gap-2 text-[10px] text-muted-foreground"><span /><span className="text-right">bas</span><span className="text-right">moyen</span><span className="text-right">haut</span></div>
          </div>
        </div>

        <div className="border border-border rounded-sm p-4 space-y-3" data-testid="param-coefs">
          <div className="flex items-center justify-between">
            <h4 className="font-semibold flex items-center gap-2"><MapPin className="h-4 w-4 text-primary" /> Coefficients régionaux</h4>
            <Button size="sm" onClick={saveCoefs} className="rounded-sm gap-1 h-8" data-testid="param-coefs-save"><Save className="h-3.5 w-3.5" /> Enregistrer</Button>
          </div>
          <div className="space-y-1">
            {coefs.map((c, i) => (
              <div key={c.region} className="grid grid-cols-2 gap-2 items-center text-sm">
                <span className="truncate">{c.label || c.region}</span>
                <input type="number" step="0.01" value={c.coef} onChange={(e) => { const v = [...coefs]; v[i] = { ...c, coef: e.target.value }; setCoefs(v); }}
                       className="rounded-sm border border-input bg-background px-2 py-1 text-right num" />
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Prix matériaux */}
      <div className="border border-border rounded-sm p-4 space-y-3" data-testid="param-materials">
        <h4 className="font-semibold flex items-center gap-2"><Package className="h-4 w-4 text-primary" /> Prix matériaux (éditables)</h4>
        <div className="relative max-w-xs">
          <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
          <Input value={matQ} onChange={async (e) => { setMatQ(e.target.value); const { data } = await api.get("/admin/param-library/materials", { params: { q: e.target.value } }); setMaterials(data.materials || []); }}
                 placeholder="Rechercher un matériau…" className="rounded-sm pl-9" data-testid="param-mat-search" />
        </div>
        <div className="max-h-72 overflow-y-auto grid sm:grid-cols-2 gap-2">
          {materials.map((m, i) => (
            <div key={m.mat_id} className="flex items-center gap-2 text-sm border border-border/60 rounded-sm px-2 py-1">
              <span className="flex-1 truncate">{m.name} <span className="text-xs text-muted-foreground">/{m.unit}</span></span>
              <input type="number" step="0.1" value={m.price}
                     onChange={(e) => { const v = [...materials]; v[i] = { ...m, price: e.target.value }; setMaterials(v); }}
                     onBlur={() => saveMaterial(m)}
                     className="w-20 rounded-sm border border-input bg-background px-2 py-1 text-right num" />
              <span className="text-xs">€</span>
            </div>
          ))}
        </div>
      </div>

      {/* Détail calcul */}
      <Dialog open={!!detail} onOpenChange={(v) => !v && setDetail(null)}>
        <DialogContent className="rounded-sm max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="param-detail-dialog">
          {detail && (
            <>
              <DialogHeader><DialogTitle className="flex items-center gap-2">
                <Calculator className="h-5 w-5 text-primary" /> {detail.famille}
                <span className="text-xs font-mono text-muted-foreground">{detail.base_code}</span>
              </DialogTitle></DialogHeader>
              <div className="flex flex-wrap gap-3 items-center text-xs">
                <div className="flex gap-1">Gamme :{LEVELS.map((l) => (
                  <button key={l} onClick={() => setLevel(l)} className={`rounded-sm px-2 py-1 border capitalize ${level === l ? "border-primary bg-primary text-white" : "border-input"}`}>{l}</button>))}</div>
                <div className="flex gap-1">Région :
                  <select value={region} onChange={(e) => setRegion(e.target.value)} className="rounded-sm border border-input bg-background px-2 py-1">
                    {coefs.map((c) => <option key={c.region} value={c.region}>{c.label || c.region} (×{c.coef})</option>)}
                  </select></div>
                <div className="flex items-center gap-1">Marge :
                  <input type="number" value={margin} onChange={(e) => setMargin(Number(e.target.value) || 0)} className="w-16 rounded-sm border border-input bg-background px-2 py-1 text-right num" />%</div>
              </div>
              <div className="border border-border rounded-sm overflow-hidden">
                <table className="w-full text-sm">
                  <thead><tr className="bg-secondary/60 text-left"><th className="p-2">Composant</th><th className="p-2 text-right">Qté</th><th className="p-2 text-right">PU</th><th className="p-2 text-right">Coût</th></tr></thead>
                  <tbody>{detail.lignes.map((l, i) => (
                    <tr key={i} className="border-t border-border/60">
                      <td className="p-2">{l.composant} {!l.matched && <span className="text-[10px] text-amber-600">(prix à définir)</span>}</td>
                      <td className="p-2 text-right num">{l.quantite} {l.unite}</td>
                      <td className="p-2 text-right num">{eur(l.prix_unitaire)}</td>
                      <td className="p-2 text-right num">{eur(l.cout)}</td>
                    </tr>))}
                    <tr className="border-t border-border"><td className="p-2 text-muted-foreground" colSpan={3}>Main d'œuvre ({detail.metier}) — {detail.labor_hours} h × {eur(detail.labor_rate)}</td><td className="p-2 text-right num">{eur(detail.labor_cost)}</td></tr>
                  </tbody>
                </table>
              </div>
              <div className="grid grid-cols-3 gap-3 text-center">
                <div className="rounded-sm border border-border p-3"><p className="text-[11px] uppercase text-muted-foreground">Déboursé sec</p><p className="text-lg font-semibold num">{eur(detail.debourse_sec)}</p></div>
                <div className="rounded-sm border border-border p-3"><p className="text-[11px] uppercase text-muted-foreground">Coût revient (×{detail.coef})</p><p className="text-lg font-semibold num">{eur(detail.prix_revient)}</p></div>
                <div className="rounded-sm border border-primary bg-primary/5 p-3"><p className="text-[11px] uppercase text-primary">Prix de vente</p><p className="text-lg font-bold num text-primary">{eur(detail.prix_vente)}</p></div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
