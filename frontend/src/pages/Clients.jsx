import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Plus, Search, Pencil, Trash2, Mail, Phone, MapPin, Building2, User, Loader2,
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
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useNavigate } from "react-router-dom";

const EMPTY = {
  first_name: "", last_name: "", company: "", email: "", phone: "",
  address: "", postal_code: "", city: "", siret: "", notes: "",
};

export default function Clients() {
  const { user } = useAuth();
  const nav = useNavigate();
  const [clients, setClients] = useState([]);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);

  const load = async (search = "") => {
    setLoading(true);
    try {
      const { data } = await api.get(`/clients?q=${encodeURIComponent(search)}`);
      setClients(data.clients || []);
    } catch { toast.error("Impossible de charger les clients"); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (user) load(); }, [user]);
  useEffect(() => {
    const id = setTimeout(() => { if (user) load(q); }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const openNew = () => { setEditing(null); setForm(EMPTY); setOpen(true); };
  const openEdit = (c) => { setEditing(c.client_id); setForm({ ...EMPTY, ...c }); setOpen(true); };
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    if (!(form.first_name || form.last_name || form.company || form.email)) {
      return toast.error("Renseignez au moins un nom, une société ou un email");
    }
    setSaving(true);
    try {
      const payload = {
        first_name: form.first_name, last_name: form.last_name, company: form.company,
        email: form.email, phone: form.phone, address: form.address,
        postal_code: form.postal_code, city: form.city, siret: form.siret, notes: form.notes,
      };
      if (editing) await api.put(`/clients/${editing}`, payload);
      else await api.post("/clients", payload);
      toast.success(editing ? "Client mis à jour" : "Client créé");
      setOpen(false);
      load(q);
    } catch (e) { toast.error(e?.response?.data?.detail || "Enregistrement impossible"); }
    finally { setSaving(false); }
  };

  const remove = async (c) => {
    if (!window.confirm(`Supprimer la fiche de ${name(c)} ?`)) return;
    try { await api.delete(`/clients/${c.client_id}`); toast.success("Client supprimé"); load(q); }
    catch { toast.error("Suppression impossible"); }
  };

  const name = (c) =>
    [c.first_name, c.last_name].filter(Boolean).join(" ") || c.company || c.email || "Client";

  if (!user) return <div className="surface p-10 text-center">Connectez-vous.</div>;

  return (
    <div className="grid gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionTitle over="Espace Pro" title="Vos clients">
          Créez et gérez vos fiches clients — réutilisables dans vos devis et factures.
          L'IA peut aussi créer une fiche automatiquement depuis le cartouche d'un plan analysé.
        </SectionTitle>
        <Button onClick={openNew} className="rounded-sm gap-2" data-testid="client-new-btn">
          <Plus className="h-4 w-4" /> Nouveau client
        </Button>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)}
               placeholder="Rechercher (nom, société, email, ville…)"
               className="pl-9 rounded-sm" data-testid="client-search-input" />
      </div>

      {loading ? (
        <div className="surface p-10 text-center animate-pulse">Chargement…</div>
      ) : clients.length === 0 ? (
        <div className="surface p-10 text-center space-y-3" data-testid="clients-empty">
          <User className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="font-display font-bold">Aucun client pour l'instant</p>
          <p className="text-sm text-muted-foreground">
            Cliquez sur « Nouveau client » pour créer votre première fiche.
          </p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="clients-grid">
          {clients.map((c) => (
            <div key={c.client_id} className="surface p-4 flex flex-col gap-2"
                 data-testid={`client-card-${c.client_id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="h-9 w-9 rounded-sm bg-primary/10 text-primary grid place-items-center font-display font-bold shrink-0">
                    {(name(c) || "?").slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <p className="font-bold text-sm truncate">{name(c)}</p>
                    {c.company && (c.first_name || c.last_name) && (
                      <p className="text-[11px] text-muted-foreground truncate flex items-center gap-1">
                        <Building2 className="h-3 w-3" />{c.company}
                      </p>
                    )}
                  </div>
                </div>
                {c.source === "ai_plan" && (
                  <Badge variant="outline"
                         className="rounded-sm text-[9px] border-primary/40 text-primary shrink-0">
                    IA
                  </Badge>
                )}
              </div>
              <div className="text-xs text-muted-foreground grid gap-1">
                {c.email && (
                  <span className="flex items-center gap-1 truncate">
                    <Mail className="h-3 w-3 shrink-0" />{c.email}
                  </span>
                )}
                {c.phone && (
                  <span className="flex items-center gap-1">
                    <Phone className="h-3 w-3 shrink-0" />{c.phone}
                  </span>
                )}
                {(c.address || c.city) && (
                  <span className="flex items-center gap-1 truncate">
                    <MapPin className="h-3 w-3 shrink-0" />
                    {[c.address, c.postal_code, c.city].filter(Boolean).join(", ")}
                  </span>
                )}
              </div>
              <div className="flex gap-2 mt-auto pt-2">
                <Button size="sm" className="rounded-sm flex-1"
                        onClick={() => nav(`/devis-editeur?client=${c.client_id}`)}
                        data-testid={`client-quote-${c.client_id}`}>
                  Devis
                </Button>
                <Button size="sm" variant="outline" className="rounded-sm"
                        onClick={() => openEdit(c)} data-testid={`client-edit-${c.client_id}`}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" className="rounded-sm text-destructive"
                        onClick={() => remove(c)} data-testid={`client-delete-${c.client_id}`}>
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-lg" data-testid="client-dialog">
          <DialogHeader>
            <DialogTitle>{editing ? "Modifier le client" : "Nouveau client"}</DialogTitle>
          </DialogHeader>
          <div className="grid sm:grid-cols-2 gap-3">
            <div><Label>Prénom</Label>
              <Input value={form.first_name} onChange={set("first_name")}
                     className="rounded-sm mt-1" data-testid="client-firstname" /></div>
            <div><Label>Nom</Label>
              <Input value={form.last_name} onChange={set("last_name")}
                     className="rounded-sm mt-1" data-testid="client-lastname" /></div>
            <div className="sm:col-span-2"><Label>Société (optionnel)</Label>
              <Input value={form.company} onChange={set("company")}
                     className="rounded-sm mt-1" data-testid="client-company" /></div>
            <div><Label>Email</Label>
              <Input value={form.email} onChange={set("email")} type="email"
                     className="rounded-sm mt-1" data-testid="client-email" /></div>
            <div><Label>Téléphone</Label>
              <Input value={form.phone} onChange={set("phone")}
                     className="rounded-sm mt-1" data-testid="client-phone" /></div>
            <div className="sm:col-span-2"><Label>Adresse</Label>
              <Input value={form.address} onChange={set("address")}
                     className="rounded-sm mt-1" data-testid="client-address" /></div>
            <div><Label>Code postal</Label>
              <Input value={form.postal_code} onChange={set("postal_code")}
                     className="rounded-sm mt-1" data-testid="client-postal" /></div>
            <div><Label>Ville</Label>
              <Input value={form.city} onChange={set("city")}
                     className="rounded-sm mt-1" data-testid="client-city" /></div>
            <div className="sm:col-span-2"><Label>SIRET (optionnel)</Label>
              <Input value={form.siret} onChange={set("siret")}
                     className="rounded-sm mt-1" data-testid="client-siret" /></div>
            <div className="sm:col-span-2"><Label>Notes</Label>
              <Textarea value={form.notes} onChange={set("notes")} rows={2}
                        className="rounded-sm mt-1 resize-none" data-testid="client-notes" /></div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} className="rounded-sm">
              Annuler
            </Button>
            <Button onClick={save} disabled={saving} className="rounded-sm gap-2"
                    data-testid="client-save-btn">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
