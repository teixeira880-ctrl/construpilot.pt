import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { Plus, Trash2, Upload, Loader2, Tag, Search, Download, MapPin } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, eur2 } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";

const EMPTY = { name: "", price: "", unit: "u", supplier: "", category: "" };

export default function PriceCatalog() {
  const [rows, setRows] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [importing, setImporting] = useState(false);
  const [q, setQ] = useState("");
  const [depts, setDepts] = useState([]);
  const [deptCode, setDeptCode] = useState(() => localStorage.getItem("construpilot_dept_code") || "AUTRE");
  const fileRef = useRef(null);

  const load = () => api.get("/prices/catalog").then(({ data }) => setRows(data));
  useEffect(() => {
    load();
    api.get("/prices/departments").then(({ data }) => setDepts(data)).catch(() => {});
  }, []);

  const currentCoef = depts.find((d) => d.code === deptCode)?.coefficient ?? 1;
  const onDept = (code) => {
    setDeptCode(code);
    const coef = depts.find((d) => d.code === code)?.coefficient ?? 1;
    localStorage.setItem("construpilot_dept_code", code);
    localStorage.setItem("construpilot_dept_coef", String(coef));
    toast.success(`Coefficient régional appliqué : ×${coef}`);
  };

  const downloadTemplate = () => {
    window.open(`${process.env.REACT_APP_BACKEND_URL}/api/prices/catalog/template`, "_blank");
  };

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    if (!form.name.trim() || form.price === "") return toast.error("Nome e preço obrigatórios");
    setSaving(true);
    try {
      await api.post("/prices/catalog", {
        name: form.name, price: Number(form.price), unit: form.unit || "u",
        supplier: form.supplier, category: form.category,
      });
      toast.success("Preço guardado");
      setForm(EMPTY); load();
    } catch { toast.error("Erreur"); } finally { setSaving(false); }
  };

  const del = async (id) => {
    await api.delete(`/prices/catalog/${id}`); load();
  };

  const onFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setImporting(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const { data } = await api.post("/prices/catalog/import", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${data.imported} prix importés${data.skipped ? ` · ${data.skipped} ignorés` : ""}`);
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Importação impossível");
    } finally { setImporting(false); if (fileRef.current) fileRef.current.value = ""; }
  };

  const filtered = rows.filter((r) => !q || r.name.toLowerCase().includes(q.toLowerCase()) || (r.category || "").toLowerCase().includes(q.toLowerCase()));

  return (
    <div className="max-w-5xl mx-auto px-6 py-10 space-y-8" data-testid="price-catalog-page">
      <SectionTitle overline="Comparador 100% fiável" title="O meu catálogo de preços" />
      <p className="text-muted-foreground -mt-4 max-w-2xl text-sm">
        Introduz os teus preços reais de fornecedores (ou importa um ficheiro do teu distribuidor). O comparador e os orçamentos usam automaticamente estes preços quando o nome do material coincidir.
      </p>

      <div className="surface p-5 rounded-md flex flex-wrap items-center gap-4" data-testid="dept-coef">
        <div className="flex items-center gap-2 text-sm">
          <MapPin className="h-4 w-4 text-primary" />
          <span className="text-muted-foreground">Région / département :</span>
        </div>
        <select value={deptCode} onChange={(e) => onDept(e.target.value)} data-testid="dept-select"
          className="rounded-sm border border-border bg-background px-3 py-2 text-sm min-w-[280px]">
          {depts.map((d) => <option key={d.code} value={d.code}>{d.name} (×{d.coefficient})</option>)}
        </select>
        <span className="text-sm">
          Coefficient appliqué aux estimations : <b className="text-primary num">×{currentCoef}</b>
        </span>
      </div>

      <div className="surface p-5 rounded-md grid gap-3 md:grid-cols-6 items-end" data-testid="catalog-form">
        <div className="md:col-span-2"><Label>Material *</Label><Input value={form.name} onChange={set("name")} placeholder="Placa Pladur 250×120" className="rounded-sm mt-1" data-testid="catalog-name" /></div>
        <div><Label>Prix (€) *</Label><Input type="number" value={form.price} onChange={set("price")} className="rounded-sm mt-1 num" data-testid="catalog-price" /></div>
        <div><Label>Unité</Label><Input value={form.unit} onChange={set("unit")} placeholder="u / m² / ml" className="rounded-sm mt-1" data-testid="catalog-unit" /></div>
        <div><Label>Fournisseur</Label><Input value={form.supplier} onChange={set("supplier")} placeholder="Point P…" className="rounded-sm mt-1" data-testid="catalog-supplier" /></div>
        <Button onClick={save} disabled={saving} className="rounded-sm gap-2" data-testid="catalog-save">
          {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />} Ajouter
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="relative w-full max-w-xs">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher…" className="rounded-sm pl-9" data-testid="catalog-search" />
        </div>
        <div className="flex items-center gap-2">
          <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" onChange={onFile} className="hidden" data-testid="catalog-file-input" />
          <Button variant="ghost" className="rounded-sm gap-2 text-muted-foreground" onClick={downloadTemplate} data-testid="catalog-template-btn">
            <Download className="h-4 w-4" /> Modèle Excel
          </Button>
          <Button variant="outline" className="rounded-sm gap-2" disabled={importing} onClick={() => fileRef.current?.click()} data-testid="catalog-import-btn">
            {importing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Importer CSV / Excel
          </Button>
        </div>
      </div>

      {rows.length === 0 ? (
        <div className="surface p-10 text-center rounded-md" data-testid="catalog-empty">
          <Tag className="h-8 w-8 text-muted-foreground mx-auto mb-3" />
          <p className="text-muted-foreground">Sem preços de momento. Adiciona um ou importa o teu ficheiro de tarifas.</p>
          <p className="text-xs text-muted-foreground mt-2">Colunas aceites: nome, preço, unidade, fornecedor, categoria.</p>
        </div>
      ) : (
        <div className="surface rounded-md overflow-x-auto" data-testid="catalog-table">
          <Table>
            <TableHeader>
              <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                <TableHead>Matériau</TableHead>
                <TableHead>Categoria</TableHead>
                <TableHead>Fournisseur</TableHead>
                <TableHead className="text-right">Prix</TableHead>
                <TableHead className="text-right">Unité</TableHead>
                <TableHead></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {filtered.map((r) => (
                <TableRow key={r.catalog_id} className="even:bg-muted/30" data-testid={`catalog-row-${r.catalog_id}`}>
                  <TableCell className="font-medium">{r.name}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{r.category || "—"}</TableCell>
                  <TableCell className="text-muted-foreground text-sm">{r.supplier || "—"}</TableCell>
                  <TableCell className="num text-right font-semibold text-primary">{eur2(r.price)}</TableCell>
                  <TableCell className="num text-right text-muted-foreground">{r.unit}</TableCell>
                  <TableCell className="text-right">
                    <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => del(r.catalog_id)} data-testid={`catalog-del-${r.catalog_id}`}>
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
