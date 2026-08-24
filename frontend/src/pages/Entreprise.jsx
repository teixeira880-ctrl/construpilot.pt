import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import {
  Building2, Lock, ArrowRight, Users, UserPlus, Trash2, FileText, Layers,
  HardHat, ClipboardList, Tag, Crown, ShieldCheck, TrendingUp, Wallet, CheckCircle2, XCircle, History, Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { SectionTitle } from "@/components/Bits";
import BrandingDialog from "@/components/BrandingDialog";
import MailboxDialog from "@/components/MailboxDialog";
import { ImportDocumentsDialog } from "@/components/ImportDocumentsDialog";
import DataManagementPanel from "@/components/DataManagementPanel";
import { api, eur } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { usePermissions } from "@/context/PermissionContext";
import { toast } from "sonner";

const QUICK = [
  { key: "devis", to: "/devis", label: "Devis & suivi", icon: FileText },
  { key: "factures", to: "/factures", label: "Factures", icon: FileText },
  { key: "situations", to: "/situations", label: "Situations de travaux", icon: Layers },
  { key: "chantier", to: "/suivi-chantier", label: "Suivi de chantier", icon: ClipboardList },
  { key: "rh", to: "/rh", label: "RH & Pointage", icon: HardHat },
  { key: "catalogue", to: "/mon-catalogue", label: "Catalogue de prix", icon: Tag },
];

const Kpi = ({ icon: Icon, label, value, accent }) => (
  <div className="surface p-5 rounded-md" data-testid={`kpi-${label}`}>
    <div className="flex items-center gap-2 text-muted-foreground"><Icon className="h-4 w-4" /><span className="text-xs">{label}</span></div>
    <p className={`num mt-2 text-2xl font-extrabold ${accent ? "text-primary" : ""}`}>{value}</p>
  </div>
);

export default function Entreprise() {
  const nav = useNavigate();
  const { user } = useAuth();
  const { tier, active: sub } = useBilling();
  const { can, role, role_label, refresh: refreshPerms } = usePermissions();
  const isProBusiness = tier === "pro_business" || user?.role === "admin" || !!user?.invoicing_addon;

  const [data, setData] = useState(null);
  const [activity, setActivity] = useState([]);
  const [actorFilter, setActorFilter] = useState("all");
  const [emp, setEmp] = useState({ name: "", email: "", password: "", role: "member" });
  const [openEmp, setOpenEmp] = useState(false);
  const [busy, setBusy] = useState(false);
  const isManager = role === "owner" || role === "admin" || user?.role === "admin";

  const load = () => {
    if (!isManager) return;
    api.get("/company/dashboard").then(({ data }) => setData(data)).catch(() => {});
    loadActivity(actorFilter);
  };
  const loadActivity = (actor) => {
    const q = actor && actor !== "all" ? `?actor_id=${actor}` : "";
    api.get(`/company/activity${q}`).then(({ data }) => setActivity(data)).catch(() => {});
  };
  const onActorFilter = (v) => { setActorFilter(v); loadActivity(v); };
  const exportJournal = async () => {
    try {
      const q = actorFilter && actorFilter !== "all" ? `?actor_id=${actorFilter}` : "";
      const { data } = await api.get(`/company/activity/export${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "text/csv" }));
      const a = document.createElement("a"); a.href = url; a.download = "journal-activite.csv"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export impossible"); }
  };
  const exportJournalPdf = async () => {
    try {
      const q = actorFilter && actorFilter !== "all" ? `?actor_id=${actorFilter}` : "";
      const { data } = await api.get(`/company/activity/pdf${q}`, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      const a = document.createElement("a"); a.href = url; a.download = "journal-activite.pdf"; a.click();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export PDF impossible"); }
  };
  useEffect(() => { if (isProBusiness) load(); /* eslint-disable-next-line */ }, [isProBusiness, isManager]);

  const createEmp = async () => {
    if (!emp.name || !emp.email || emp.password.length < 6) return toast.error("Nom, e-mail et mot de passe (6+) requis");
    setBusy(true);
    try {
      await api.post("/company/employees", emp);
      toast.success("Employé créé — mot de passe provisoire à communiquer");
      setEmp({ name: "", email: "", password: "", role: "member" });
      setOpenEmp(false); load();
    } catch (e) { toast.error(e?.response?.data?.detail || "Création impossible"); }
    finally { setBusy(false); }
  };
  const setRole = async (uid, r) => {
    try { await api.put(`/company/members/${uid}`, { role: r }); toast.success("Rôle mis à jour"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };
  const toggleActive = async (m) => {
    try { await api.put(`/company/members/${m.user_id}`, { active: !m.active }); toast.success(m.active ? "Accès désactivé" : "Accès réactivé"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };
  const removeMember = async (uid) => {
    try { await api.delete(`/company/members/${uid}`); toast.success("Employé retiré"); load(); }
    catch (e) { toast.error(e?.response?.data?.detail || "Erreur"); }
  };

  if (!isProBusiness) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-24 text-center" data-testid="entreprise-locked">
        <div className="h-14 w-14 rounded-xl bg-primary/10 grid place-items-center mx-auto mb-5"><Lock className="h-7 w-7 text-primary" /></div>
        <h1 className="font-display text-3xl font-bold">Espace Entreprise</h1>
        <p className="text-muted-foreground mt-3">Pilotez toute votre entreprise, vos équipes et leurs accès — réservé au <b>pack Business</b>.</p>
        <Button className="rounded-sm mt-6 gap-2" onClick={() => nav("/tarifs")} data-testid="entreprise-upgrade-btn">Passer au pack Business <ArrowRight className="h-4 w-4" /></Button>
      </div>
    );
  }

  const k = data?.kpis;
  const roles = data?.assignable_roles || [];

  return (
    <div className="max-w-6xl mx-auto px-4 py-10 space-y-8" data-testid="entreprise-page">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <SectionTitle over="Pack Business" title="Espace Entreprise">
          Le tableau de bord central de votre société : activité, équipe, accès et modules métier.
        </SectionTitle>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="rounded-sm gap-1"><ShieldCheck className="h-3.5 w-3.5 text-primary" /> {role_label || "Propriétaire"}</Badge>
          <ImportDocumentsDialog triggerLabel="Importer devis/factures PDF" onImported={load} />
          <BrandingDialog />
          <MailboxDialog />
        </div>
      </div>

      {isManager && k && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3" data-testid="entreprise-kpis">
          <Kpi icon={Wallet} label="CA facturé TTC" value={eur(k.ca_ttc)} accent />
          <Kpi icon={TrendingUp} label="Encours à encaisser" value={eur(k.encours)} />
          <Kpi icon={ShieldCheck} label="Factures conformes" value={`${k.invoices_conformes}/${k.invoices}`} />
          <Kpi icon={Layers} label="Situations" value={k.situations} />
          <Kpi icon={FileText} label="Devis" value={k.quotes} />
          <Kpi icon={ClipboardList} label="Chantiers" value={k.chantiers} />
          <Kpi icon={XCircle} label="Réserves en cours" value={k.open_reserves} />
          <Kpi icon={Users} label="Équipe" value={`${k.members} (${k.workers} ouvriers)`} />
        </div>
      )}

      <div>
        <p className="overline mb-3">Modules</p>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="entreprise-modules">
          {QUICK.filter((q) => can(q.key)).map((q) => (
            <motion.button key={q.key} whileHover={{ y: -3 }} onClick={() => nav(q.to)} data-testid={`module-${q.key}`}
              className="surface rounded-md p-5 text-left flex items-center gap-3 hover:border-primary/40 transition-colors">
              <div className="h-10 w-10 rounded-lg bg-primary/10 grid place-items-center"><q.icon className="h-5 w-5 text-primary" /></div>
              <span className="font-display font-semibold">{q.label}</span>
              <ArrowRight className="h-4 w-4 ml-auto text-muted-foreground" />
            </motion.button>
          ))}
        </div>
      </div>

      {isManager && (
        <div data-testid="entreprise-team">
          <div className="flex items-center justify-between mb-3">
            <p className="overline flex items-center gap-2"><Users className="h-4 w-4" /> Équipe & accès</p>
            <Dialog open={openEmp} onOpenChange={setOpenEmp}>
              <DialogTrigger asChild>
                <Button size="sm" className="rounded-sm gap-2" data-testid="add-employee-btn"><UserPlus className="h-4 w-4" /> Ajouter un employé</Button>
              </DialogTrigger>
              <DialogContent className="max-w-md" data-testid="employee-dialog">
                <DialogHeader><DialogTitle>Nouvel employé</DialogTitle></DialogHeader>
                <div className="grid gap-3 mt-1">
                  <div className="grid gap-1.5"><Label>Nom</Label>
                    <Input value={emp.name} onChange={(e) => setEmp({ ...emp, name: e.target.value })} className="rounded-sm" data-testid="emp-name" /></div>
                  <div className="grid gap-1.5"><Label>E-mail</Label>
                    <Input type="email" value={emp.email} onChange={(e) => setEmp({ ...emp, email: e.target.value })} className="rounded-sm" data-testid="emp-email" /></div>
                  <div className="grid gap-1.5"><Label>Mot de passe provisoire</Label>
                    <Input value={emp.password} onChange={(e) => setEmp({ ...emp, password: e.target.value })} className="rounded-sm" placeholder="6 caractères min." data-testid="emp-password" /></div>
                  <div className="grid gap-1.5"><Label>Rôle</Label>
                    <Select value={emp.role} onValueChange={(v) => setEmp({ ...emp, role: v })}>
                      <SelectTrigger className="rounded-sm" data-testid="emp-role"><SelectValue /></SelectTrigger>
                      <SelectContent>{roles.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
                    </Select>
                  </div>
                </div>
                <DialogFooter className="mt-2">
                  <Button onClick={createEmp} disabled={busy} className="rounded-sm gap-2" data-testid="emp-create-btn"><UserPlus className="h-4 w-4" /> Créer le compte</Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          </div>

          <div className="space-y-2">
            {(data?.members || []).map((m) => (
              <div key={m.user_id} className="surface rounded-sm p-4 flex flex-wrap items-center gap-3" data-testid={`member-${m.user_id}`}>
                <div className="h-9 w-9 rounded-full bg-primary/10 grid place-items-center">
                  {m.role === "owner" ? <Crown className="h-4 w-4 text-primary" /> : <Users className="h-4 w-4 text-primary" />}
                </div>
                <div className="min-w-0">
                  <p className="font-semibold">{m.name || m.email} {m.is_self && <span className="text-xs text-muted-foreground">(vous)</span>}</p>
                  <p className="text-xs text-muted-foreground">{m.email}</p>
                </div>
                <div className="ml-auto flex items-center gap-2">
                  {!m.active && <Badge variant="outline" className="rounded-sm text-red-500 border-red-500/30">Désactivé</Badge>}
                  {m.role === "owner" || m.is_self ? (
                    <Badge className="rounded-sm">{m.role_label}</Badge>
                  ) : (
                    <>
                      <Select value={m.role} onValueChange={(v) => setRole(m.user_id, v)}>
                        <SelectTrigger className="rounded-sm h-9 w-[160px]" data-testid={`member-role-${m.user_id}`}><SelectValue /></SelectTrigger>
                        <SelectContent>{roles.map((r) => <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>)}</SelectContent>
                      </Select>
                      <Button size="sm" variant="outline" className="rounded-sm" onClick={() => toggleActive(m)} data-testid={`member-toggle-${m.user_id}`}>
                        {m.active ? "Désactiver" : "Réactiver"}
                      </Button>
                      <Button size="icon" variant="ghost" className="h-9 w-9 text-red-500" onClick={() => removeMember(m.user_id)} data-testid={`member-remove-${m.user_id}`}><Trash2 className="h-4 w-4" /></Button>
                    </>
                  )}
                </div>
              </div>
            ))}
            {(!data?.members || data.members.length === 0) && (
              <div className="surface rounded-md p-8 text-center text-sm text-muted-foreground">
                Aucun employé pour l'instant. Créez une organisation depuis <button className="text-primary underline" onClick={() => nav("/equipe")}>Équipe</button>, puis ajoutez vos employés.
              </div>
            )}
          </div>
        </div>
      )}

      {isManager && activity.length >= 0 && (
        <div data-testid="entreprise-activity">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
            <p className="overline flex items-center gap-2"><History className="h-4 w-4" /> Activité récente</p>
            <div className="flex items-center gap-2">
              <Select value={actorFilter} onValueChange={onActorFilter}>
                <SelectTrigger className="rounded-sm h-9 w-[180px]" data-testid="activity-filter"><SelectValue placeholder="Tous les employés" /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Tous les employés</SelectItem>
                  {(data?.members || []).map((m) => <SelectItem key={m.user_id} value={m.user_id}>{m.name || m.email}</SelectItem>)}
                </SelectContent>
              </Select>
              <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={exportJournal} data-testid="activity-export"><Download className="h-4 w-4" /> CSV</Button>
              <Button size="sm" variant="outline" className="rounded-sm gap-1.5" onClick={exportJournalPdf} data-testid="activity-export-pdf"><FileText className="h-4 w-4" /> PDF</Button>
            </div>
          </div>
          <div className="surface rounded-md divide-y divide-border/60">
            {activity.length === 0 && <p className="px-4 py-6 text-sm text-muted-foreground text-center">Aucune activité pour ce filtre.</p>}
            {activity.slice(0, 30).map((a) => (
              <div key={a.log_id} className="flex items-center gap-3 px-4 py-3" data-testid={`activity-${a.log_id}`}>
                <div className="h-8 w-8 rounded-full bg-primary/10 grid place-items-center shrink-0">
                  <span className="text-[11px] font-bold text-primary">{(a.actor_name || "?").slice(0, 1).toUpperCase()}</span>
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-sm truncate">
                    <b>{a.actor_name}</b> {a.action_label}
                    {a.label ? <span className="text-muted-foreground"> · {a.label}</span> : ""}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground shrink-0">{new Date(a.created_at).toLocaleString("fr-FR", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" })}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <DataManagementPanel />

      <div className="surface rounded-md p-5 flex flex-wrap items-center justify-between gap-4" data-testid="entreprise-subscription">
        <div>
          <p className="overline">Abonnement</p>
          <p className="font-display font-semibold mt-1 capitalize">{(tier || "free").replace("_", " ")}{typeof sub?.plan === "string" ? ` · ${sub.plan}` : ""}</p>
        </div>
        <Button variant="outline" className="rounded-sm gap-2" onClick={() => nav("/tarifs")} data-testid="entreprise-manage-sub"><Wallet className="h-4 w-4" /> Gérer l'abonnement</Button>
      </div>
    </div>
  );
}
