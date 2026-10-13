import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { api } from "@/lib/api";

export const CHANTIER_STATUS = { prospect: "Prospect", en_cours: "En cours", termine: "Terminé" };
const EMPTY = { name: "", client_id: "", address: "", postal_code: "", city: "", status: "en_cours", notes: "" };

export function ChantierFormDialog({ open, onOpenChange, chantier, clientId, onSaved }) {
  const [form, setForm] = useState(EMPTY);
  const [clients, setClients] = useState([]);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!open) return;
    setForm(chantier ? { ...EMPTY, ...chantier, client_id: chantier.client_id || "" } : { ...EMPTY, client_id: clientId || "" });
    api.get("/clients").then(({ data }) => setClients(data.clients || [])).catch(() => {});
  }, [open, chantier, clientId]);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) return toast.error("Donnez un nom au chantier");
    setBusy(true);
    try {
      const payload = { ...form, client_id: form.client_id || null };
      const { data } = chantier ? await api.put(`/chantiers/${chantier.chantier_id}`, payload) : await api.post("/chantiers", payload);
      toast.success(chantier ? "Chantier mis à jour" : "Dossier chantier créé");
      onOpenChange(false);
      onSaved?.(data);
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Enregistrement impossible");
    } finally { setBusy(false); }
  };
  const label = (c) => c.company || [c.first_name, c.last_name].filter(Boolean).join(" ") || c.email;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="chantier-form-dialog">
        <DialogHeader><DialogTitle>{chantier ? "Modifier le chantier" : "Nouveau dossier chantier"}</DialogTitle>
          <DialogDescription>Le client et l'adresse seront repris automatiquement dans vos devis, plans et analyses.</DialogDescription></DialogHeader>
        <form onSubmit={submit} className="grid gap-3">
          <div><Label htmlFor="cht-name">Nom du chantier *</Label><Input id="cht-name" value={form.name} onChange={set("name")} placeholder="Ex. Rénovation Villa Dupont" data-testid="chantier-name-input" required /></div>
          <div><Label htmlFor="cht-client">Client</Label>
            <select id="cht-client" value={form.client_id} onChange={set("client_id")} className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" data-testid="chantier-client-select">
              <option value="">— Aucun client pour l'instant —</option>
              {clients.map((c) => <option key={c.client_id} value={c.client_id}>{label(c)}</option>)}
            </select></div>
          <div className="grid grid-cols-3 gap-2">
            <div className="col-span-3"><Label htmlFor="cht-addr">Adresse</Label><Input id="cht-addr" value={form.address} onChange={set("address")} data-testid="chantier-address-input" /></div>
            <div><Label htmlFor="cht-cp">Code postal</Label><Input id="cht-cp" value={form.postal_code} onChange={set("postal_code")} data-testid="chantier-postal-input" /></div>
            <div className="col-span-2"><Label htmlFor="cht-city">Ville</Label><Input id="cht-city" value={form.city} onChange={set("city")} data-testid="chantier-city-input" /></div>
          </div>
          <div><Label htmlFor="cht-status">Statut</Label>
            <select id="cht-status" value={form.status} onChange={set("status")} className="w-full h-10 rounded-md border border-input bg-background px-3 text-sm" data-testid="chantier-status-select">
              {Object.entries(CHANTIER_STATUS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select></div>
          <div><Label htmlFor="cht-notes">Notes</Label><textarea id="cht-notes" value={form.notes} onChange={set("notes")} rows={3} className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm" data-testid="chantier-notes-input" /></div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)} data-testid="chantier-form-cancel">Annuler</Button>
            <Button type="submit" disabled={busy} data-testid="chantier-form-submit">{busy ? "Enregistrement…" : chantier ? "Enregistrer" : "Créer le dossier"}</Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
