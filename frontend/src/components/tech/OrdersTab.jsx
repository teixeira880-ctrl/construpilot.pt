import { useEffect, useState } from "react";
import { Trash2, GitMerge, PackageCheck, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";

const TYPE_LBL = { acier: "Ferraillage", etancheite: "Étanchéité", toiture: "Toiture", vrd: "VRD", mixte: "Mixte" };
const STATUS = { brouillon: "bg-muted text-muted-foreground", envoyé: "bg-amber-500/15 text-amber-600", confirmé: "bg-emerald-500/15 text-emerald-600" };

export default function OrdersTab({ suppliers = [] }) {
  const [orders, setOrders] = useState([]);
  const [selected, setSelected] = useState([]);
  const [supplierId, setSupplierId] = useState("");
  const [project, setProject] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.get("/pro/appro/orders")
      .then(({ data }) => setOrders(data.items || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); }, []);

  const toggle = (id, on) => setSelected((prev) => (on ? [...prev, id] : prev.filter((x) => x !== id)));

  const merge = async () => {
    if (selected.length < 2) return toast.error("Selecione pelo menos 2 encomendas");
    setBusy(true);
    try {
      const { data } = await api.post("/pro/appro/orders/merge", {
        order_ids: selected, project: project.trim(), supplier_id: supplierId || null,
      });
      toast.success(`Encomenda agrupada — ${data.item_count} linhas (${data.merged_count} notas)`);
      setSelected([]); setProject(""); load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Não foi possível agrupar");
    } finally { setBusy(false); }
  };

  const setStatus = async (id, status) => {
    try {
      await api.patch(`/pro/appro/orders/${id}/status`, { status });
      setOrders((prev) => prev.map((o) => (o.order_id === id ? { ...o, status } : o)));
    } catch { toast.error("Impossível"); }
  };

  const del = async (id) => {
    if (!window.confirm("Eliminar esta nota de encomenda?")) return;
    try {
      await api.delete(`/pro/appro/orders/${id}`);
      setOrders((prev) => prev.filter((o) => o.order_id !== id));
      setSelected((prev) => prev.filter((x) => x !== id));
    } catch { toast.error("Impossível"); }
  };

  return (
    <div className="space-y-4" data-testid="orders-tab">
      {/* Barre de fusion */}
      <div className="surface p-4 grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
        <div>
          <label className="text-xs text-muted-foreground">Nom du projet (commande fusionnée)</label>
          <Input value={project} onChange={(e) => setProject(e.target.value)}
                 placeholder="Ex : Résidence Les Tilleuls" className="h-9 mt-1" data-testid="merge-project-name" />
        </div>
        <div>
          <label className="text-xs text-muted-foreground">Fournisseur (optionnel)</label>
          <select value={supplierId} onChange={(e) => setSupplierId(e.target.value)}
                  data-testid="merge-supplier-select"
                  className="mt-1 h-9 rounded-sm border border-border bg-background px-3 text-sm w-full sm:w-56">
            <option value="">— Auto / aucun —</option>
            {suppliers.map((s) => <option key={s.supplier_id} value={s.supplier_id}>{s.name}</option>)}
          </select>
        </div>
        <Button onClick={merge} disabled={busy || selected.length < 2}
                data-testid="merge-orders-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
          <GitMerge className="h-4 w-4" />
          {busy ? "Fusion…" : `Fusionner (${selected.length})`}
        </Button>
      </div>

      {/* Liste des commandes */}
      <div className="surface p-4">
        <h3 className="font-bold mb-3 flex items-center gap-2"><PackageCheck className="h-4 w-4 text-primary" /> Bons de commande ({orders.length})</h3>
        {loading ? (
          <p className="text-sm text-muted-foreground py-6 text-center">Chargement…</p>
        ) : orders.length === 0 ? (
          <p className="text-sm text-muted-foreground py-6 text-center">
            Aucun bon de commande. Créez-en depuis les onglets Ferraillage / Étanchéité / Toiture / VRD.
          </p>
        ) : (
          <div className="space-y-2">
            {orders.map((o) => {
              const on = selected.includes(o.order_id);
              return (
                <div key={o.order_id}
                     className={`rounded-sm border p-3 flex items-center gap-3 ${on ? "border-primary bg-primary/5" : "border-border"}`}
                     data-testid={`order-item-${o.order_id}`}>
                  <input type="checkbox" checked={on}
                         onChange={(e) => toggle(o.order_id, e.target.checked)}
                         data-testid={`order-checkbox-${o.order_id}`}
                         className="accent-primary h-4 w-4" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                      <span className="font-semibold text-sm truncate">
                        {o.project || TYPE_LBL[o.type] || "Encomenda"}
                      </span>
                      <span className="text-[10px] font-bold uppercase bg-secondary px-1.5 py-0.5 rounded">
                        {TYPE_LBL[o.type] || o.type}
                      </span>
                      {o.merged_from && (
                        <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-1.5 py-0.5 rounded">
                          Fusion ×{o.merged_from.length}
                        </span>
                      )}
                    </div>
                    <p className="text-[11px] text-muted-foreground num mt-0.5">
                      {(o.items || []).length} lignes
                      {o.supplier?.name ? ` · ${o.supplier.name}` : ""}
                      {o.order_id ? ` · ${o.order_id}` : ""}
                    </p>
                  </div>
                  <select value={o.status || "brouillon"} onChange={(e) => setStatus(o.order_id, e.target.value)}
                          data-testid={`order-status-${o.order_id}`}
                          className={`text-[11px] font-bold rounded-full px-2 py-1 border-0 cursor-pointer ${STATUS[o.status] || STATUS.brouillon}`}>
                    <option value="brouillon">Brouillon</option>
                    <option value="enviado">Envoyée</option>
                    <option value="confirmé">Confirmée</option>
                  </select>
                  <button onClick={() => del(o.order_id)} data-testid={`order-delete-${o.order_id}`}>
                    <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
