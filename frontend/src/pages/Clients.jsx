import { useExperienceCopy } from "@/components/workspace/experienceCopy";
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
import { useI18n } from "@/context/I18nContext";
import { useNavigate } from "react-router-dom";
import { useConfirm } from "@/components/ConfirmProvider";

const EMPTY = {
  first_name: "", last_name: "", company: "", email: "", phone: "",
  address: "", postal_code: "", city: "", siret: "", notes: "",
};

export default function Clients() {
  const { user } = useAuth();
  const { t } = useI18n();
  const experience = useExperienceCopy();
  const nav = useNavigate();
  const confirm = useConfirm();
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
    } catch { toast.error(t("crm.load_fail")); }
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
      return toast.error(t("crm.need_identity"));
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
      toast.success(editing ? t("crm.updated") : t("crm.created"));
      setOpen(false);
      load(q);
    } catch (e) { toast.error(e?.response?.data?.detail || t("crm.save_fail")); }
    finally { setSaving(false); }
  };

  const remove = async (c) => {
    if (!(await confirm({
      title: "Eliminar este cliente?",
      description: `${name(c)} será eliminado. Impossível se tiver orçamentos/faturas associados.`,
      confirmLabel: "Eliminar",
    }))) return;
    try { await api.delete(`/clients/${c.client_id}`); toast.success(t("crm.deleted")); load(q); }
    catch (e) { toast.error(e?.response?.data?.detail || t("crm.delete_fail")); }
  };

  const name = (c) =>
    [c.first_name, c.last_name].filter(Boolean).join(" ") || c.company || c.email || "Cliente";

  if (!user) return <div className="surface p-10 text-center">{t("crm.login")}</div>;

  return (
    <div className="grid gap-6 workspace-collection" data-testid="clients-page">
      <div className="workspace-page-heading">
        <SectionTitle as="h1" over={t("crm.over")} title={t("crm.clients_title")}>
          {t("crm.clients_sub")}
        </SectionTitle>
        <Button onClick={openNew} className="rounded-sm gap-2" data-testid="client-new-btn">
          <Plus className="h-4 w-4" /> {t("crm.new_client")}
        </Button>
      </div>

      <div className="relative max-w-md">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)}
               aria-label={t("crm.search_ph")} placeholder={t("crm.search_ph")}
               className="pl-9 rounded-sm" data-testid="client-search-input" />
      </div>

      {loading ? (
        <div className="surface p-10 text-center animate-pulse">{t("crm.loading")}</div>
      ) : clients.length === 0 ? (
        <div className="surface p-10 text-center space-y-3" data-testid="clients-empty">
          <User className="h-10 w-10 mx-auto text-muted-foreground" />
          <p className="font-display font-bold">{t("crm.clients_empty_title")}</p>
          <p className="text-sm text-muted-foreground">
            {t("crm.clients_empty_sub")}
          </p>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="clients-grid">
          {clients.map((c) => (
            <div key={c.client_id} className="surface p-5 flex flex-col gap-3 workspace-client-card"
                 data-testid={`client-card-${c.client_id}`}>
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <div className="h-9 w-9 rounded-sm bg-primary/10 text-primary grid place-items-center font-display font-bold shrink-0">
                    {(name(c) || "?").slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0">
                    <button onClick={() => nav(`/clients/${c.client_id}`)}
                            className="font-bold text-sm truncate hover:text-primary text-left w-full"
                            data-testid={`client-open-${c.client_id}`}>{name(c)}</button>
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
                  <a href={`mailto:${c.email}`} className="workspace-client-contact">
                    <Mail className="h-3 w-3 shrink-0" />{c.email}
                  </a>
                )}
                {c.phone && (
                  <a href={`tel:${c.phone}`} className="workspace-client-contact">
                    <Phone className="h-3 w-3 shrink-0" />{c.phone}
                  </a>
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
                  {t("crm.quote_btn")}
                </Button>
                <Button size="sm" variant="outline" className="rounded-sm"
                        aria-label={`${experience("edit")} : ${name(c)}`} onClick={() => openEdit(c)} data-testid={`client-edit-${c.client_id}`}>
                  <Pencil className="h-3.5 w-3.5" />
                </Button>
                <Button size="sm" variant="ghost" className="rounded-sm text-destructive"
                        aria-label={`${t("common.delete", "Eliminar")} : ${name(c)}`} onClick={() => remove(c)} data-testid={`client-delete-${c.client_id}`}>
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
            <DialogTitle>{editing ? t("crm.edit_client") : t("crm.new_client")}</DialogTitle>
          </DialogHeader>
          <div className="grid sm:grid-cols-2 gap-3">
            <div><Label htmlFor="client-firstname">{t("crm.firstname")}</Label>
              <Input value={form.first_name} onChange={set("first_name")}
                     className="rounded-sm mt-1" id="client-firstname" data-testid="client-firstname" /></div>
            <div><Label htmlFor="client-lastname">{t("crm.lastname")}</Label>
              <Input value={form.last_name} onChange={set("last_name")}
                     className="rounded-sm mt-1" id="client-lastname" data-testid="client-lastname" /></div>
            <div className="sm:col-span-2"><Label htmlFor="client-company">{t("crm.company_opt")}</Label>
              <Input value={form.company} onChange={set("company")}
                     className="rounded-sm mt-1" id="client-company" data-testid="client-company" /></div>
            <div><Label htmlFor="client-email">{t("crm.email")}</Label>
              <Input value={form.email} onChange={set("email")} type="email"
                     className="rounded-sm mt-1" id="client-email" data-testid="client-email" /></div>
            <div><Label htmlFor="client-phone">{t("crm.phone")}</Label>
              <Input value={form.phone} onChange={set("phone")}
                     className="rounded-sm mt-1" id="client-phone" data-testid="client-phone" /></div>
            <div className="sm:col-span-2"><Label htmlFor="client-address">{t("crm.address")}</Label>
              <Input value={form.address} onChange={set("address")}
                     className="rounded-sm mt-1" id="client-address" data-testid="client-address" /></div>
            <div><Label htmlFor="client-postal">{t("crm.postal")}</Label>
              <Input value={form.postal_code} onChange={set("postal_code")}
                     className="rounded-sm mt-1" id="client-postal" data-testid="client-postal" /></div>
            <div><Label htmlFor="client-city">{t("crm.city")}</Label>
              <Input value={form.city} onChange={set("city")}
                     className="rounded-sm mt-1" id="client-city" data-testid="client-city" /></div>
            <div className="sm:col-span-2"><Label htmlFor="client-siret">{t("crm.siret_opt")}</Label>
              <Input value={form.siret} onChange={set("siret")}
                     className="rounded-sm mt-1" id="client-siret" data-testid="client-siret" /></div>
            <div className="sm:col-span-2"><Label htmlFor="client-notes">{t("crm.notes")}</Label>
              <Textarea value={form.notes} onChange={set("notes")} rows={2}
                        className="rounded-sm mt-1 resize-none" id="client-notes" data-testid="client-notes" /></div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} className="rounded-sm">
              {t("crm.cancel")}
            </Button>
            <Button onClick={save} disabled={saving} className="rounded-sm gap-2"
                    data-testid="client-save-btn">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} {t("crm.save")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

