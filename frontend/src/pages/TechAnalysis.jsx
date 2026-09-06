import { useEffect, useState } from "react";
import { Trash2, Plus, HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";
import SteelTab from "@/components/tech/SteelTab";
import WaterproofingTab from "@/components/tech/WaterproofingTab";
import RoofingTab from "@/components/tech/RoofingTab";
import VrdTab from "@/components/tech/VrdTab";
import OrdersTab from "@/components/tech/OrdersTab";

const dedupePlans = (items) => {
  const seen = new Set();
  const out = [];
  for (const p of items) {
    const key = (p.filename || p.plan_id || "").trim().toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(p);
  }
  return out;
};

export default function TechAnalysis() {
  const [tab, setTab] = useState("acier");
  const [plans, setPlans] = useState([]);
  const [suppliers, setSuppliers] = useState([]);

  useEffect(() => {
    api.get("/takeoffs").then(({ data }) => {
      const items = Array.isArray(data) ? data : (data.items || data.takeoffs || data.plans || []);
      setPlans(dedupePlans(items));
    }).catch(() => {});
    loadSuppliers();
  }, []);

  const loadSuppliers = () => api.get("/pro/suppliers").then(({ data }) => setSuppliers(data.items || [])).catch(() => {});

  const tabs = [["acier", "Ferraillage / Acier"], ["etancheite", "Étanchéité"],
  ["toiture", "Toiture"], ["vrd", "VRD / Réseaux"], ["commandes", "Commandes"], ["fournisseurs", "Mes fournisseurs"]];

  return (
    <div className="max-w-6xl mx-auto px-4 py-8 space-y-6" data-testid="tech-analysis-page">
      <div className="flex items-center gap-3 flex-wrap">
        <HardHat className="h-6 w-6 text-primary" />
        <h1 className="font-display text-2xl font-bold">Análise technique &amp; Approvisionnement IA</h1>
        <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-2 py-0.5 rounded-full">Pro · Acier · Étanchéité · Toiture · VRD</span>
      </div>

      <div className="flex gap-2 border-b border-border overflow-x-auto">
        {tabs.map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} data-testid={`tab-${k}`}
            className={`px-4 py-2 text-sm font-semibold border-b-2 -mb-px whitespace-nowrap ${tab === k ? "border-primary text-primary" : "border-transparent text-muted-foreground"}`}>{l}</button>
        ))}
      </div>

      {tab === "acier" && <SteelTab plans={plans} suppliers={suppliers} />}
      {tab === "etancheite" && <WaterproofingTab plans={plans} suppliers={suppliers} />}
      {tab === "toiture" && <RoofingTab plans={plans} suppliers={suppliers} />}
      {tab === "vrd" && <VrdTab plans={plans} suppliers={suppliers} />}
      {tab === "commandes" && <OrdersTab suppliers={suppliers} />}
      {tab === "fournisseurs" && <SupplierManager suppliers={suppliers} reload={loadSuppliers} />}
    </div>
  );
}

const SupplierManager = ({ suppliers, reload }) => {
  const empty = { name: "", agency: "", client_number: "", email: "", phone: "", delivery_address: "", categories: [], price_list: [] };
  const [form, setForm] = useState(empty);
  const [editId, setEditId] = useState(null);

  const save = async () => {
    if (!form.name) return toast.error("Nom obrigatório");
    try {
      const payload = { ...form, categories: form.categories || [], price_list: (form.price_list || []).filter((r) => r.label) };
      if (editId) await api.put(`/pro/suppliers/${editId}`, payload);
      else await api.post("/pro/suppliers", payload);
      toast.success(editId ? "Fornecedor mis à jour" : "Fornecedor ajouté");
      setForm(empty); setEditId(null); reload();
    } catch { toast.error("Impossível"); }
  };
  const edit = (s) => { setForm({ ...empty, ...s, price_list: s.price_list || [] }); setEditId(s.supplier_id); };
  const del = async (id) => { try { await api.delete(`/pro/suppliers/${id}`); reload(); if (editId === id) { setForm(empty); setEditId(null); } } catch { toast.error("Impossível"); } };

  const setPrice = (i, field, val) => {
    const pl = [...(form.price_list || [])];
    pl[i] = { ...pl[i], [field]: field === "price" ? (parseFloat(val) || 0) : val };
    setForm({ ...form, price_list: pl });
  };
  const addPrice = () => setForm({ ...form, price_list: [...(form.price_list || []), { label: "", unit: "", price: 0 }] });
  const delPrice = (i) => setForm({ ...form, price_list: (form.price_list || []).filter((_, k) => k !== i) });

  return (
    <div className="grid lg:grid-cols-2 gap-5" data-testid="suppliers-tab">
      <div className="surface p-4 space-y-2">
        <h3 className="font-bold mb-1">{editId ? "Editar le fournisseur" : "Adicionar un fournisseur"}</h3>
        {[["name", "Nom *"], ["agency", "Agence"], ["client_number", "N° client"], ["email", "Email"], ["phone", "Téléphone"], ["delivery_address", "Adresse de livraison"]].map(([k, l]) => (
          <div key={k}><label className="text-xs text-muted-foreground">{l}</label>
            <Input value={form[k] || ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} className="h-8" data-testid={`supplier-${k}`} /></div>
        ))}

        <div className="pt-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold">Catalogue de prix (mots-clés → PU HT)</label>
            <Button size="sm" variant="outline" onClick={addPrice} className="h-7 gap-1 rounded-sm" data-testid="add-price-row"><Plus className="h-3 w-3" />Ligne</Button>
          </div>
          <p className="text-[11px] text-muted-foreground mb-1">Ex : « tuiles terre cuite » · unité · 0,85 €. Utilisé pour chiffrer les bons de encomenda.</p>
          <div className="space-y-1">
            {(form.price_list || []).map((r, i) => (
              <div key={i} className="flex gap-1 items-center" data-testid={`price-row-${i}`}>
                <Input value={r.label} placeholder="désignation / mot-clé" onChange={(e) => setPrice(i, "label", e.target.value)} className="h-7 text-xs flex-1" data-testid={`price-label-${i}`} />
                <Input value={r.unit || ""} placeholder="u" onChange={(e) => setPrice(i, "unit", e.target.value)} className="h-7 text-xs w-14" />
                <Input type="number" value={r.price} placeholder="€" onChange={(e) => setPrice(i, "price", e.target.value)} className="h-7 text-xs w-20 text-right" data-testid={`price-value-${i}`} />
                <button onClick={() => delPrice(i)} data-testid={`del-price-${i}`}><Trash2 className="h-3.5 w-3.5 text-muted-foreground hover:text-destructive" /></button>
              </div>
            ))}
          </div>
        </div>

        <div className="flex gap-2 pt-2">
          <Button onClick={save} className="rounded-sm gap-2" data-testid="add-supplier-btn"><Plus className="h-4 w-4" />{editId ? "Guardar" : "Adicionar"}</Button>
          {editId && <Button variant="outline" onClick={() => { setForm(empty); setEditId(null); }} className="rounded-sm">Cancelar</Button>}
        </div>
      </div>

      <div className="surface p-4">
        <h3 className="font-bold mb-2">Mes fournisseurs ({suppliers.length})</h3>
        {suppliers.length === 0 && <p className="text-sm text-muted-foreground">Nenhum fournisseur enregistré.</p>}
        <div className="space-y-2">
          {suppliers.map((s) => (
            <div key={s.supplier_id} className="flex items-center justify-between rounded-sm border border-border p-2 text-sm" data-testid={`supplier-item-${s.supplier_id}`}>
              <div><div className="font-semibold">{s.name}{s.agency ? ` · ${s.agency}` : ""}</div>
                <div className="text-xs text-muted-foreground">{[s.client_number, s.email, s.phone].filter(Boolean).join(" · ")}{(s.price_list || []).length ? ` · ${s.price_list.length} prix` : ""}</div></div>
              <div className="flex gap-2">
                <button onClick={() => edit(s)} data-testid={`edit-supplier-${s.supplier_id}`} className="text-xs text-primary font-semibold">Editar</button>
                <button onClick={() => del(s.supplier_id)} data-testid={`del-supplier-${s.supplier_id}`}><Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" /></button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
