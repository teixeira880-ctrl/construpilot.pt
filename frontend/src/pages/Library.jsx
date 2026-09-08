import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Plus, Search, Pencil, Trash2, Library as LibIcon, Loader2, RotateCcw, Package, Hammer,
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

const UNITS = ["u", "m²", "ml", "m³", "forfait", "ens", "h", "j", "kg", "L"];
const VAT_RATES = [10, 20, 5.5];
const EMPTY = {
  type: "ouvrage", category: "", designation: "", unit: "m²",
  unit_price_ht: "", vat_rate: 10, notes: "",
};
const eur = (n) => (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

export default function Library() {
  const { user } = useAuth();
  const [items, setItems] = useState([]);
  const [categories, setCategories] = useState([]);
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = async (search = q, type = typeFilter) => {
    setLoading(true);
    try {
      const { data } = await api.get(
        `/library?q=${encodeURIComponent(search)}&type=${type}`);
      setItems(data.items || []);
      setCategories(data.categories || []);
    } catch { toast.error("Impossible de charger la bibliothèque"); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (user) load(); }, [user]);
  useEffect(() => {
    const id = setTimeout(() => { if (user) load(q, typeFilter); }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, typeFilter]);

  const openNew = () => { setEditing(null); setForm(EMPTY); setOpen(true); };
  const openEdit = (it) => {
    setEditing(it.item_id);
    setForm({ ...EMPTY, ...it, unit_price_ht: String(it.unit_price_ht ?? "") });
    setOpen(true);
  };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    if (!form.designation.trim()) return toast.error("La désignation est obligatoire");
    setSaving(true);
    try {
      const payload = {
        type: form.type, category: form.category, designation: form.designation,
        unit: form.unit, unit_price_ht: parseFloat(form.unit_price_ht) || 0,
        vat_rate: parseFloat(form.vat_rate) || 10, notes: form.notes,
      };
      if (editing) await api.put(`/library/${editing}`, payload);
      else await api.post("/library", payload);
      toast.success(editing ? "Élément mis à jour" : "Élément ajouté à la bibliothèque");
      setOpen(false);
      load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossible"); }
    finally { setSaving(false); }
  };

  const remove = async (it) => {
    if (!window.confirm(`Supprimer « ${it.designation} » ?`)) return;
    try { await api.delete(`/library/${it.item_id}`); toast.success("Élément supprimé"); load(); }
    catch { toast.error("Suppression impossible"); }
  };

  const resetCatalogue = async () => {
    if (!window.confirm("Réinsérer le catalogue de départ ? Vos éléments actuels sont conservés.")) return;
    try { const { data } = await api.post("/library/reset-catalogue"); toast.success(`Catalogue rechargé (${data.count} éléments)`); load(); }
    catch { toast.error("Action impossible"); }
  };

  if (!user) return <div className="surface p-10 text-center">Connectez-vous.</div>;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionTitle over="Espace Pro" title="Votre bibliothèque">
          Vos ouvrages et matériaux avec vos prix. Réutilisez-les dans vos devis en un clic —
          chaque nouvel élément saisi est enregistré ici automatiquement.
        </SectionTitle>
        <div className="flex gap-2">
          <Button variant="outline" onClick={resetCatalogue} className="rounded-sm gap-2"
                  data-testid="library-reset-btn">
            <RotateCcw className="h-4 w-4" /> Catalogue de départ
          </Button>
          <Button onClick={openNew} className="rounded-sm gap-2" data-testid="library-new-btn">
            <Plus className="h-4 w-4" /> Nouvel élément
          </Button>
        </div>
      </div>

      <SharedLibraryPanel />

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)}
                 placeholder="Procurar um trabalho, um material, uma categoria…"
                 className="pl-9 rounded-sm" data-testid="library-search-input" />
        </div>
        <div className="flex gap-1 border border-border rounded-sm p-0.5" data-testid="library-type-filter">
          {[["", "Tous"], ["ouvrage", "Ouvrages"], ["materiau", "Matériaux"]].map(([v, lbl]) => (
            <button key={v} onClick={() => setTypeFilter(v)}
                    data-testid={`library-filter-${v || "all"}`}
                    className={`px-3 py-1.5 text-xs rounded-sm transition ${typeFilter === v ? "bg-primary text-primary-foreground" : "text-muted-foreground hover:text-foreground"}`}>
              {lbl}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="surface p-10 text-center animate-pulse">Chargement…</div>
      ) : items.length === 0 ? (
        <div className="surface p-10 text-center space-y-3" data-testid="library-empty">
          <LibIcon className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="font-display font-bold">Aucun élément</p>
          <p className="text-sm text-muted-foreground">
            Ajoutez un ouvrage/matériau ou rechargez le catalogue de départ.
          </p>
        </div>
      ) : (
        <div className="surface divide-y divide-border" data-testid="library-list">
          <div className="hidden md:grid grid-cols-12 gap-2 px-4 py-2 text-[10px] uppercase tracking-wider text-muted-foreground font-bold">
            <span className="col-span-5">Désignation</span>
            <span className="col-span-2">Catégorie</span>
            <span className="col-span-1 text-center">Unité</span>
            <span className="col-span-2 text-right">PU HT</span>
            <span className="col-span-1 text-center">TVA</span>
            <span className="col-span-1 text-right">Actions</span>
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
              <span className="col-span-1 md:col-span-2 text-right num font-bold text-sm">{eur(it.unit_price_ht)}</span>
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

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg" data-testid="library-dialog">
          <DialogHeader>
            <DialogTitle>{editing ? "Modifier l'élément" : "Nouvel élément"}</DialogTitle>
          </DialogHeader>
          <div className="grid sm:grid-cols-2 gap-3">
            <div>
              <Label>Type</Label>
              <select value={form.type} onChange={set("type")} data-testid="library-type-select"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                <option value="ouvrage">Ouvrage (main d'œuvre + fourniture)</option>
                <option value="materiau">Matériau (fourniture seule)</option>
              </select>
            </div>
            <div>
              <Label>Catégorie</Label>
              <Input value={form.category} onChange={set("category")} list="lib-cats"
                     className="rounded-sm mt-1" data-testid="library-category" placeholder="Ex : Électricité" />
              <datalist id="lib-cats">
                {categories.map((c) => <option key={c} value={c} />)}
              </datalist>
            </div>
            <div className="sm:col-span-2">
              <Label>Désignation</Label>
              <Input value={form.designation} onChange={set("designation")}
                     className="rounded-sm mt-1" data-testid="library-designation"
                     placeholder="Ex : Peinture murs 2 couches" />
            </div>
            <div>
              <Label>Unité</Label>
              <select value={form.unit} onChange={set("unit")} data-testid="library-unit"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                {UNITS.map((u) => <option key={u} value={u}>{u}</option>)}
              </select>
            </div>
            <div>
              <Label>Prix unitaire HT (€)</Label>
              <Input type="number" step="0.01" min="0" value={form.unit_price_ht}
                     onChange={set("unit_price_ht")} className="rounded-sm mt-1 num"
                     data-testid="library-price" placeholder="0,00" />
            </div>
            <div>
              <Label>TVA</Label>
              <select value={form.vat_rate} onChange={set("vat_rate")} data-testid="library-vat"
                      className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary">
                {VAT_RATES.map((r) => <option key={r} value={r}>{r} %</option>)}
              </select>
            </div>
            <div className="sm:col-span-2">
              <Label>Notes (optionnel)</Label>
              <Textarea value={form.notes} onChange={set("notes")} rows={2}
                        className="rounded-sm mt-1 resize-none" data-testid="library-notes" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} className="rounded-sm">Annuler</Button>
            <Button onClick={save} disabled={saving} className="rounded-sm gap-2"
                    data-testid="library-save-btn">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
