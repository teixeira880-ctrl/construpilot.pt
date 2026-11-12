import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Plus, Search, Pencil, Trash2, Library as LibIcon, Loader2, RotateCcw, Package, Hammer, FileUp, Copy,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import SharedLibraryPanel from "@/components/SharedLibraryPanel";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import LibraryImportDialog from "@/components/library/LibraryImportDialog";
import LibraryDuplicatesDialog from "@/components/library/LibraryDuplicatesDialog";
import LearnedPricesPanel from "@/components/library/LearnedPricesPanel";
import CostResourcesPanel from "@/components/library/CostResourcesPanel";

const UNITS = ["u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L"];
const VAT_RATES = [6, 13, 23]; // Portugal continental (CIVA)
const EMPTY = {
  type: "ouvrage", category: "", designation: "", unit: "m²",
  unit_price_ht: "", cost_price_ht: "", vat_rate: 23, notes: "", library_kind: "ambas",
};
// Duas bibliotecas: VENDA (preços ao cliente, usados nos orçamentos) e COMPRA (preços de custo: fornecedores,
// mão de obra, equipamento). Um artigo com os dois preços dá a margem no dossier económico.
const KINDS = [["venda", "Biblioteca de venda", "preços ao cliente"], ["compra", "Biblioteca de compra", "preços de custo"],
               ["recursos", "Recursos e custos da empresa", "mão de obra, veículos, máquinas, gasóleo"]];
const marginPct = (it) => (Number(it.unit_price_ht) > 0 && Number(it.cost_price_ht) > 0)
  ? Math.round((1 - Number(it.cost_price_ht) / Number(it.unit_price_ht)) * 100) : null;
const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

export default function Library() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [sources, setSources] = useState([]);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [sourceFilter, setSourceFilter] = useState("");
  const [kind, setKind] = useState("venda");
  const [kinds, setKinds] = useState({});
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [dupOpen, setDupOpen] = useState(false);

  const load = async (search = q, type = typeFilter, source = sourceFilter, k = kind) => {
    setLoading(true);
    try {
      const { data } = await api.get(
        `/library?q=${encodeURIComponent(search)}&type=${type}&source=${encodeURIComponent(source)}&kind=${k}`);
      setItems(data.items || []);
      setKinds(data.kinds || {});
      setCategories(data.categories || []);
      setSources(data.sources || []);
    } catch { toast.error("Impossível carregar a biblioteca"); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (user) load(); }, [user]);
  useEffect(() => {
    const id = setTimeout(() => { if (user && kind !== "recursos") load(q, typeFilter, sourceFilter, kind); }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, typeFilter, sourceFilter, kind]);

  const openNew = () => { setEditing(null); setForm({ ...EMPTY, library_kind: kind === "compra" ? "compra" : "ambas", type: kind === "compra" ? "materiau" : "ouvrage" }); setOpen(true); };
  const openEdit = (it) => {
    setEditing(it.item_id);
    setForm({ ...EMPTY, ...it, unit_price_ht: String(it.unit_price_ht ?? ""), cost_price_ht: String(it.cost_price_ht || ""), library_kind: it.library_kind || "ambas" });
    setOpen(true);
  };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    if (!form.designation.trim()) return toast.error("A designação é obrigatória");
    setSaving(true);
    try {
      const payload = {
        type: form.type, category: form.category, designation: form.designation,
        unit: form.unit, unit_price_ht: parseFloat(form.unit_price_ht) || 0,
        cost_price_ht: parseFloat(form.cost_price_ht) || 0,
        vat_rate: (form.vat_rate === "" || form.vat_rate == null) ? 23 : parseFloat(form.vat_rate), notes: form.notes,
        library_kind: form.library_kind || "ambas",
      };
      if (editing) await api.put(`/library/${editing}`, payload);
      else await api.post("/library", payload);
      toast.success(editing ? "Elemento atualizado" : "Elemento adicionado à biblioteca");
      setOpen(false);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível guardar"); }
    finally { setSaving(false); }
  };

  const remove = async (it) => {
    if (!window.confirm(`Eliminar « ${it.designation} » ?`)) return;
    try { await api.delete(`/library/${it.item_id}`); toast.success("Elemento eliminado"); load(); }
    catch { toast.error("Não foi possível eliminar"); }
  };

  const resetCatalogue = async () => {
    if (!window.confirm("Reinserir o catálogo inicial? Os seus elementos atuais são conservados.")) return;
    try { const { data } = await api.post("/library/reset-catalogue"); toast.success(`Catálogo recarregado (${data.count} elementos)`); load(); }
    catch { toast.error("Ação impossível"); }
  };

  if (!user) return <div className="surface p-10 text-center">Ligue-se.</div>;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionTitle over="Espaço Pro" title="A sua biblioteca">
          Os seus trabalhos e materiais com os seus preços. Reutilize-os nos seus orçamentos num clique — cada novo elemento inserido é guardado aqui automaticamente.
        </SectionTitle>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" onClick={() => setImportOpen(true)} className="rounded-sm gap-2 border-primary/40 text-primary"
                  data-testid="library-import-btn">
            <FileUp className="h-4 w-4" /> Retomar os meus orçamentos antigos
          </Button>
          <Button variant="outline" onClick={() => setDupOpen(true)} className="rounded-sm gap-2"
                  data-testid="library-duplicates-btn">
            <Copy className="h-4 w-4" /> Limpar os duplicados
          </Button>
          <Button variant="outline" onClick={resetCatalogue} className="rounded-sm gap-2"
                  data-testid="library-reset-btn">
            <RotateCcw className="h-4 w-4" /> Catálogo de partida
          </Button>
          <Button onClick={openNew} className="rounded-sm gap-2" data-testid="library-new-btn">
            <Plus className="h-4 w-4" /> Novo elemento
          </Button>
        </div>
      </div>

      <div className="grid sm:grid-cols-3 gap-2" data-testid="library-kind-tabs">
        {KINDS.map(([k, label, sub]) => (
          <button key={k} onClick={() => setKind(k)} data-testid={`library-kind-${k}`}
                  className={`rounded-md border-2 px-4 py-3 text-left transition ${kind === k ? "border-primary bg-primary/5" : "border-border hover:border-primary/40"}`}>
            <span className="block font-display font-bold text-sm">{label}{k !== "recursos" && <span className="num text-muted-foreground font-normal"> ({kinds[k] ?? "…"})</span>}</span>
            <span className="block text-xs text-muted-foreground">{sub}{k === "compra" ? " — fornecedores, subempreiteiros; servem para o custo e a margem" : k === "venda" ? " — usados automaticamente nos orçamentos" : " — entram no dossier económico"}</span>
          </button>
        ))}
      </div>

      {kind === "recursos" ? <CostResourcesPanel /> : <>
      <SharedLibraryPanel />
      <LearnedPricesPanel onValidated={() => load()} />
      <LibraryImportDialog open={importOpen} onClose={() => setImportOpen(false)} onDone={() => load()} />
      <LibraryDuplicatesDialog open={dupOpen} onClose={() => setDupOpen(false)} onDone={() => load()} />

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Pesquisar um artigo, um material, uma categoria…"
                 className="pl-9 rounded-sm" data-testid="library-search-input" />
        </div>
        <div className="flex gap-1 border border-border rounded-sm p-0.5" data-testid="library-type-filter">
          {[["", "Todos"], ["ouvrage", "Trabalhos"], ["materiau", "Materiais"]].map(([v, lbl]) => (
            <button key={v} onClick={() => setTypeFilter(v)}
                    data-testid={`library-filter-${v || "all"}`}
                    className={`px-3 py-1.5 text-xs rounded-sm transition ${typeFilter === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {lbl}
            </button>
          ))}
        </div>
      </div>

      {sources.length > 1 && (
        <div className="flex flex-wrap gap-1.5 items-center" data-testid="library-source-filter">
          <span className="text-[10px] uppercase tracking-wider text-muted-foreground font-bold mr-1">Origem</span>
          <button onClick={() => setSourceFilter("")} data-testid="library-source-all"
                  className={`px-3 py-1 text-xs rounded-sm border transition ${sourceFilter === "" ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>
            Todas
          </button>
          {sources.map((s) => (
            <button key={s.key} onClick={() => setSourceFilter(s.key)} data-testid={`library-source-${s.key}`}
                    className={`px-3 py-1 text-xs rounded-sm border transition ${sourceFilter === s.key ? "bg-primary text-primary-foreground border-primary" : "border-border text-muted-foreground hover:text-foreground"}`}>
              {s.label} <span className="opacity-70 num">({s.count})</span>
            </button>
          ))}
        </div>
      )}

      {loading ? (
        <div className="surface p-10 text-center animate-pulse">A carregar…</div>
      ) : items.length === 0 ? (
        <div className="surface p-10 text-center space-y-3" data-testid="library-empty">
          <LibIcon className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="font-display font-bold">Nenhum elemento</p>
          <p className="text-sm text-muted-foreground">
            Adicione um trabalho/material ou recarregue o catálogo inicial.
          </p>
        </div>
      ) : (
        <div className="surface divide-y divide-border" data-testid="library-list">
          <div className="hidden md:grid grid-cols-12 gap-2 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground font-bold">
            <span className="col-span-5">Designação</span>
            <span className="col-span-2">Categoria</span>
            <span className="col-span-1 text-center">Un.</span>
            <span className="col-span-2 text-right">{kind === "compra" ? "Custo s/ IVA" : "PU s/ IVA"} · margem</span>
            <span className="col-span-1 text-center">IVA</span>
            <span className="col-span-1 text-right">Ações</span>
          </div>
          {items.map((it) => (
            <div key={it.item_id}
                 className="grid grid-cols-2 md:grid-cols-12 gap-2 px-4 py-3 items-center hover:bg-secondary/20"
                 data-testid={`library-item-${it.item_id}`}>
              <div className="col-span-2 md:col-span-5 flex items-center gap-2 min-w-0">
                {it.type === "materiau"
                  ? <Package className="h-4 w-4 text-muted-foreground shrink-0" />
                  : <Hammer className="h-4 w-4 text-primary shrink-0" />}
                <span className="font-medium text-sm truncate">{it.designation}</span>
              </div>
              <span className="hidden md:block col-span-2 text-xs text-muted-foreground truncate">{it.category}</span>
              <span className="hidden md:block col-span-1 text-center text-xs num">{it.unit}</span>
              <span className="col-span-1 md:col-span-2 text-right num font-bold text-sm">
                {eur(kind === "compra" ? it.cost_price_ht : it.unit_price_ht)}
                {marginPct(it) != null && <span className={`block text-[10px] font-normal ${marginPct(it) < 0 ? "text-destructive" : "text-muted-foreground"}`}>margem {marginPct(it)} %</span>}
              </span>
              <span className="hidden md:block col-span-1 text-center">
                <Badge variant="outline" className="rounded-sm text-[10px] num">{it.vat_rate}%</Badge>
              </span>
              <div className="col-span-1 flex justify-end gap-1">
                <Button size="icon" variant="ghost" className="h-7 w-7" onClick={() => openEdit(it)}
                        data-testid={`library-edit-${it.item_id}`}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button size="icon" variant="ghost" className="h-7 w-7 text-destructive"
                        onClick={() => remove(it)} data-testid={`library-delete-${it.item_id}`}>
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      </>}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg" data-testid="library-dialog">
          <DialogHeader>
            <DialogTitle>{editing ? "Modificar o elemento" : "Novo elemento"}</DialogTitle>
          </DialogHeader>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <Label>Tipo</Label>
              <select value={form.type} onChange={set("type")} data-testid="library-type-select"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                <option value="ouvrage">Trabalho (mão de obra + fornecimento)</option>
                <option value="materiau">Material (fornecimento apenas)</option>
              </select>
            </div>
            <div>
              <Label>Categoria</Label>
              <Input value={form.category} onChange={set("category")} list="lib-cats"
                     className="rounded-sm mt-1" data-testid="library-category" placeholder="Ex: Eletricidade" />
              <datalist id="lib-cats">
                {categories.map((c) => <option key={c} value={c} />)}
              </datalist>
            </div>
            <div className="sm:col-span-2">
              <Label>Biblioteca</Label>
              <select value={form.library_kind} onChange={set("library_kind")} data-testid="library-kind-select"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                <option value="ambas">Compra e venda (custo + preço ao cliente → margem)</option>
                <option value="venda">Só venda (preço ao cliente)</option>
                <option value="compra">Só compra (preço de custo: fornecedor, mão de obra, equipamento)</option>
              </select>
            </div>
            <div className="sm:col-span-2">
              <Label>Designação</Label>
              <Input value={form.designation} onChange={set("designation")}
                     className="rounded-sm mt-1" data-testid="library-designation"
                     placeholder="Ex: Pintura paredes 2 demãos" />
            </div>
            <div>
              <Label>Un.</Label>
              <select value={form.unit} onChange={set("unit")} data-testid="library-unit"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
            <div>
              <Label>Preço de venda s/ IVA (€)</Label>
              <Input type="number" step="0.01" min="0" value={form.unit_price_ht}
                     onChange={set("unit_price_ht")} className="rounded-sm mt-1 num"
                     data-testid="library-price" placeholder="0,00" />
            </div>
            <div>
              <Label>Preço de compra / custo s/ IVA (€)</Label>
              <Input type="number" step="0.01" min="0" value={form.cost_price_ht}
                     onChange={set("cost_price_ht")} className="rounded-sm mt-1 num"
                     data-testid="library-cost" placeholder="MO + materiais · dá a margem" />
            </div>
            <div>
              <Label>IVA</Label>
              <select value={form.vat_rate} onChange={set("vat_rate")} data-testid="library-vat"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                {VAT_RATES.map((r) => <option key={r} value={r}>{r} %</option>)}
              </select>
            </div>
            <div className="sm:col-span-2">
              <Label>Notas (opcional)</Label>
              <Textarea value={form.notes} onChange={set("notes")} rows={2}
                        className="rounded-sm mt-1 resize-none" data-testid="library-notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} className="rounded-sm">Cancelar</Button>
            <Button onClick={save} disabled={saving} className="rounded-sm gap-2"
                    data-testid="library-save-btn">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Guardar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
