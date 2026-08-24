import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Shield, Save, Plus, Trash2, RefreshCw, Phone, Mail, CheckCircle2, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api, eur, num } from "@/lib/api";
import { useI18n } from "@/context/I18nContext";
import { Stat, SectionTitle } from "@/components/Bits";
import RevenueTab from "@/components/RevenueTab";
import AiModelTab from "@/components/AiModelTab";
import AdminSharedLibraryTab from "@/components/AdminSharedLibraryTab";
import AdminParamLibraryTab from "@/components/AdminParamLibraryTab";
import AdsPanel from "@/components/AdsPanel";
import ProKycPanel from "@/components/ProKycPanel";
import EvolutionLab from "@/components/admin/EvolutionLab";
import { ProfileForm } from "@/components/account/ProfileForm";
import { PasswordForm } from "@/components/account/PasswordForm";
import { DevicesList } from "@/components/account/DevicesList";
import { TwoFaCard } from "@/components/account/TwoFaCard";

export default function Admin() {
  const { t } = useI18n();
  const [stats, setStats] = useState(null);
  const [prices, setPrices] = useState([]);
  const [edits, setEdits] = useState({});
  const [regions, setRegions] = useState([]);
  const [users, setUsers] = useState([]);
  const [projects, setProjects] = useState([]);
  const [leads, setLeads] = useState([]);
  const [leadStats, setLeadStats] = useState(null);
  const [leadFilter, setLeadFilter] = useState("all");
  const [suppliers, setSuppliers] = useState({ builtin: [], custom: [] });
  const [newSup, setNewSup] = useState({ key: "", name: "", domain: "", shipping: 30, free_from: 300 });

  const load = () => {
    api.get("/admin/stats").then(({ data }) => setStats(data));
    api.get("/admin/prices").then(({ data }) => setPrices(data));
    api.get("/admin/regions").then(({ data }) => setRegions(data));
    api.get("/admin/users").then(({ data }) => setUsers(data));
    api.get("/admin/projects").then(({ data }) => setProjects(data));
    api.get("/admin/leads").then(({ data }) => setLeads(data));
    api.get("/admin/leads/stats").then(({ data }) => setLeadStats(data)).catch(() => {});
    api.get("/admin/suppliers").then(({ data }) => setSuppliers(data));
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const savePrice = async (key) => {
    const body = edits[key];
    if (!body) return;
    await api.put(`/admin/prices/${key}`, Object.fromEntries(
      Object.entries(body).map(([k, v]) => [k, Number(v)])
    ));
    toast.success("Prix de référence mis à jour");
    setEdits({ ...edits, [key]: undefined });
    load();
  };

  const saveRegion = async (r, coef) => {
    await api.put("/admin/regions", { country: r.country, region: r.region, coef: Number(coef) });
    toast.success(`Coefficient ${r.region} = ${coef}`);
    load();
  };

  const addSupplier = async () => {
    if (!newSup.key || !newSup.name || !newSup.domain) return toast.error("Clé, nom et domaine requis");
    await api.post("/admin/suppliers", {
      ...newSup, shipping: Number(newSup.shipping), free_from: Number(newSup.free_from),
    });
    toast.success("Fournisseur ajouté");
    setNewSup({ key: "", name: "", domain: "", shipping: 30, free_from: 300 });
    load();
  };

  if (!stats) return <div className="h-40 grid place-items-center"><div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="grid gap-10">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionTitle over={t("admin.over")} title={t("admin.title")}>
          {t("admin.subtitle")}
        </SectionTitle>
        <button
          data-testid="admin-demo-unlock-btn"
          onClick={async () => {
            try {
              const { data } = await api.post("/admin/demo-unlock");
              toast.success(`Mode démo activé — ${data.tier} · toutes les options débloquées`);
              setTimeout(() => window.location.reload(), 900);
            } catch { toast.error("Activation du mode démo impossible"); }
          }}
          className="shrink-0 rounded-sm border border-primary/40 bg-primary/10 hover:bg-primary/20 text-primary px-4 py-2 text-sm font-semibold transition-colors">
          🎬 Mode démo — tout débloquer
          <span className="block text-[11px] font-normal text-muted-foreground">Stripe test · carte 4242 4242 4242 4242</span>
        </button>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 stagger">
        <Stat label={t("admin.k_users")} value={num(stats.users)} testId="admin-stat-users" />
        <Stat label={t("admin.k_projects")} value={num(stats.projects)} testId="admin-stat-projects" />
        <Stat label={t("admin.k_quote_requests")} value={num(stats.leads)} testId="admin-stat-leads" accent />
        <Stat label={t("admin.k_quotes_analyzed")} value={num(stats.quote_analyses)} testId="admin-stat-quotes" />
        <Stat label={t("admin.k_estimated_volume")} value={eur(stats.estimated_volume)} testId="admin-stat-volume" />
      </div>

      <Tabs defaultValue="prices">
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="prices" className="rounded-sm" data-testid="admin-tab-prices">{t("admin.t_prices")}</TabsTrigger>
          <TabsTrigger value="regions" className="rounded-sm" data-testid="admin-tab-regions">{t("admin.t_regions")}</TabsTrigger>
          <TabsTrigger value="suppliers" className="rounded-sm" data-testid="admin-tab-suppliers">{t("admin.t_suppliers")}</TabsTrigger>
          <TabsTrigger value="users" className="rounded-sm" data-testid="admin-tab-users">{t("admin.t_users")}</TabsTrigger>
          <TabsTrigger value="projects" className="rounded-sm" data-testid="admin-tab-projects">{t("admin.t_projects")}</TabsTrigger>
          <TabsTrigger value="leads" className="rounded-sm" data-testid="admin-tab-leads">{t("admin.t_leads")}</TabsTrigger>
          <TabsTrigger value="searches" className="rounded-sm" data-testid="admin-tab-searches">{t("admin.t_searches")}</TabsTrigger>
          <TabsTrigger value="promos" className="rounded-sm" data-testid="admin-tab-promos">{t("admin.t_promos")}</TabsTrigger>
          <TabsTrigger value="kyc" className="rounded-sm" data-testid="admin-tab-kyc">{t("admin.t_kyc")}</TabsTrigger>
          <TabsTrigger value="proskyc" className="rounded-sm" data-testid="admin-tab-proskyc">Pros à valider</TabsTrigger>
          <TabsTrigger value="affiliate" className="rounded-sm" data-testid="admin-tab-affiliate">{t("admin.t_affiliate")}</TabsTrigger>
          <TabsTrigger value="plans" className="rounded-sm" data-testid="admin-tab-plans">{t("admin.t_plans")}</TabsTrigger>
          <TabsTrigger value="revenue" className="rounded-sm" data-testid="admin-tab-revenue">{t("admin.t_revenue")}</TabsTrigger>
          <TabsTrigger value="ai" className="rounded-sm" data-testid="admin-tab-ai">{t("admin.t_ai")}</TabsTrigger>
          <TabsTrigger value="evolution" className="rounded-sm" data-testid="admin-tab-evolution">AI Evolution Lab</TabsTrigger>
          <TabsTrigger value="sharedlib" className="rounded-sm" data-testid="admin-tab-sharedlib">Bibliothèque</TabsTrigger>
          <TabsTrigger value="paramlib" className="rounded-sm" data-testid="admin-tab-paramlib">Ouvrages composés</TabsTrigger>
          <TabsTrigger value="ads" className="rounded-sm" data-testid="admin-tab-ads">Publicité</TabsTrigger>
          <TabsTrigger value="inbox" className="rounded-sm" data-testid="admin-tab-inbox">{t("admin.t_inbox")}</TabsTrigger>
          <TabsTrigger value="errors" className="rounded-sm" data-testid="admin-tab-errors">{t("admin.t_errors")}</TabsTrigger>
          <TabsTrigger value="account" className="rounded-sm" data-testid="admin-tab-account">{t("admin.t_account")}</TabsTrigger>
        </TabsList>

        <TabsContent value="ai" className="mt-6">
          <AiModelTab />
        </TabsContent>

        <TabsContent value="evolution" className="mt-6">
          <EvolutionLab />
        </TabsContent>

        <TabsContent value="sharedlib" className="mt-6">
          <AdminSharedLibraryTab />
        </TabsContent>

        <TabsContent value="paramlib" className="mt-6">
          <AdminParamLibraryTab />
        </TabsContent>

        <TabsContent value="ads" className="mt-6">          <AdsPanel />
        </TabsContent>

        <TabsContent value="proskyc" className="mt-6">
          <ProKycPanel />
        </TabsContent>

        <TabsContent value="account" className="mt-6">
          <div className="max-w-lg space-y-6" data-testid="admin-account-section">
            <SectionTitle over="Administrateur" title="Mon compte">
              Gérez vos informations de profil et votre mot de passe.
            </SectionTitle>
            <ProfileForm />
            <TwoFaCard />
            <PasswordForm />
            <DevicesList />
          </div>
        </TabsContent>

        <TabsContent value="prices" className="mt-6">
          <div className="surface overflow-x-auto">
            <Table data-testid="admin-prices-table">
              <TableHeader>
                <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                  <TableHead>Lot</TableHead>
                  <TableHead>Unité</TableHead>
                  <TableHead className="w-28">Éco</TableHead>
                  <TableHead className="w-28">Standard</TableHead>
                  <TableHead className="w-28">Premium</TableHead>
                  <TableHead className="w-28">M.O. / u</TableHead>
                  <TableHead className="w-28">Heures / u</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {prices.map((p) => (
                  <TableRow key={p.key} className="even:bg-muted/30" data-testid={`admin-price-row-${p.key}`}>
                    <TableCell className="font-medium">{p.name} {p.overridden && <Badge variant="outline" className="ml-2 rounded-sm text-xs">modifié</Badge>}</TableCell>
                    <TableCell className="text-muted-foreground">{p.unit}</TableCell>
                    {["mat_eco", "mat_std", "mat_premium", "labour", "hours"].map((f) => (
                      <TableCell key={f}>
                        <Input
                          type="number" step="any" className="rounded-sm h-9 num"
                          data-testid={`admin-price-${p.key}-${f}`}
                          value={edits[p.key]?.[f] ?? p[f]}
                          onChange={(e) => setEdits({ ...edits, [p.key]: { ...(edits[p.key] || {}), [f]: e.target.value } })}
                        />
                      </TableCell>
                    ))}
                    <TableCell>
                      <Button size="sm" variant="outline" onClick={() => savePrice(p.key)} data-testid={`admin-save-price-${p.key}`} className="rounded-sm">
                        <Save className="h-4 w-4" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="regions" className="mt-6">
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="admin-regions">
            {regions.map((r) => (
              <div key={`${r.country}-${r.region}`} className="surface p-5 flex items-center gap-3">
                <div className="flex-1">
                  <p className="font-medium">{r.region}</p>
                  <p className="text-xs text-muted-foreground">{r.country === "FR" ? "France" : "Portugal"}</p>
                </div>
                <Input
                  type="number" step="0.01" defaultValue={r.coef}
                  data-testid={`admin-region-${r.region}`}
                  onBlur={(e) => Number(e.target.value) !== r.coef && saveRegion(r, e.target.value)}
                  className="rounded-sm h-9 w-24 num"
                />
              </div>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="suppliers" className="mt-6 grid gap-6">
          <div className="surface p-6 grid sm:grid-cols-5 gap-3 items-end" data-testid="admin-add-supplier">
            {[["key", "Clé"], ["name", "Nom"], ["domain", "Domaine"], ["shipping", "Livraison €"], ["free_from", "Franco €"]].map(([k, label]) => (
              <div key={k} className="grid gap-2">
                <Label className="text-xs">{label}</Label>
                <Input value={newSup[k]} onChange={(e) => setNewSup({ ...newSup, [k]: e.target.value })} data-testid={`supplier-${k}-input`} className="rounded-sm h-10" />
              </div>
            ))}
            <Button onClick={addSupplier} data-testid="add-supplier-btn" className="rounded-sm gap-2 sm:col-span-5 w-fit hover:bg-orange-600 hover:text-white">
              <Plus className="h-4 w-4" /> Ajouter le fournisseur
            </Button>
          </div>
          <div className="surface overflow-x-auto">
            <Table data-testid="admin-suppliers-table">
              <TableHeader>
                <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                  <TableHead>Fournisseur</TableHead>
                  <TableHead>Domaine</TableHead>
                  <TableHead className="text-right">Livraison</TableHead>
                  <TableHead className="text-right">Franco</TableHead>
                  <TableHead className="text-right">Délai</TableHead>
                  <TableHead>Type</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {[...suppliers.builtin, ...suppliers.custom].map((s, i) => (
                  <TableRow key={`${s.key}-${i}`} className="even:bg-muted/30">
                    <TableCell className="font-medium">{s.name}</TableCell>
                    <TableCell className="num text-muted-foreground">{s.domain}</TableCell>
                    <TableCell className="num text-right">{eur(s.shipping)}</TableCell>
                    <TableCell className="num text-right">{eur(s.free_from)}</TableCell>
                    <TableCell className="num text-right">{s.delivery_days || 4} j</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="rounded-sm">
                        {suppliers.custom.some((c) => c.key === s.key) ? "personnalisé" : "intégré"}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="users" className="mt-6">
          <div className="surface overflow-x-auto">
            <Table data-testid="admin-users-table">
              <TableHeader>
                <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                  <TableHead>Nom</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Rôle</TableHead>
                  <TableHead>Plan</TableHead>
                  <TableHead>Auth</TableHead>
                  <TableHead>2FA</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((u) => (
                  <TableRow key={u.user_id} className="even:bg-muted/30">
                    <TableCell className="font-medium">{u.name}</TableCell>
                    <TableCell className="num text-muted-foreground">{u.email}</TableCell>
                    <TableCell>
                      <Select
                        value={u.role}
                        onValueChange={async (v) => { await api.put(`/admin/users/${u.user_id}`, { role: v }); toast.success("Rôle mis à jour"); load(); }}
                      >
                        <SelectTrigger className="rounded-sm h-9 w-32" data-testid={`admin-role-${u.user_id}`}><SelectValue /></SelectTrigger>
                        <SelectContent>
                          <SelectItem value="user">user</SelectItem>
                          <SelectItem value="admin">admin</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={u.plan || "free"}
                        onValueChange={async (v) => { await api.put(`/admin/users/${u.user_id}`, { plan: v }); toast.success("Plan mis à jour"); load(); }}
                      >
                        <SelectTrigger className="rounded-sm h-9 w-32" data-testid={`admin-plan-${u.user_id}`}><SelectValue /></SelectTrigger>
                        <SelectContent>
                          {["free", "premium", "pro"].map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">{u.auth_provider}</TableCell>
                    <TableCell>
                      <div className="flex flex-col gap-1.5">
                        {u.two_fa_enabled ? (
                          <Button
                            size="sm"
                            variant="outline"
                            className="rounded-sm h-8 text-xs"
                            data-testid={`admin-disable-2fa-${u.user_id}`}
                            onClick={async () => {
                              await api.put(`/admin/users/${u.user_id}`, { two_fa_enabled: false });
                              toast.success("2FA désactivée pour " + u.email);
                              load();
                            }}
                          >
                            Désactiver 2FA
                          </Button>
                        ) : (
                          <span className="text-muted-foreground text-xs">—</span>
                        )}
                        <Button
                          size="sm"
                          variant="ghost"
                          className="rounded-sm h-7 text-[11px] justify-start px-1 gap-1"
                          data-testid={`admin-set-2fa-email-${u.user_id}`}
                          onClick={async () => {
                            const val = window.prompt(
                              "E-mail de réception des codes 2FA pour " + u.email +
                              "\n(laisser vide = e-mail du compte)", u.two_fa_email || "");
                            if (val === null) return;
                            const { data } = await api.put(`/admin/users/${u.user_id}`, { two_fa_email: val });
                            toast.success(data.two_fa_email
                              ? "Codes 2FA envoyés à " + data.two_fa_email
                              : "E-mail 2FA réinitialisé");
                            load();
                          }}
                        >
                          <Mail className="h-3 w-3" /> {u.two_fa_email || "e-mail 2FA…"}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="projects" className="mt-6">
          <div className="surface overflow-x-auto">
            <Table data-testid="admin-projects-table">
              <TableHeader>
                <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                  <TableHead>Projet</TableHead>
                  <TableHead>Type</TableHead>
                  <TableHead className="text-right">Surface</TableHead>
                  <TableHead className="text-right">Budget</TableHead>
                  <TableHead>Ville</TableHead>
                  <TableHead>Créé le</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {projects.map((p) => (
                  <TableRow key={p.project_id} className="even:bg-muted/30">
                    <TableCell className="font-medium">{p.name}</TableCell>
                    <TableCell className="text-muted-foreground">{p.estimation?.project_type_name}</TableCell>
                    <TableCell className="num text-right">{num(p.surface, 0)} m²</TableCell>
                    <TableCell className="num text-right font-semibold">{eur(p.budget)}</TableCell>
                    <TableCell>{p.city || "—"}</TableCell>
                    <TableCell className="num text-xs text-muted-foreground">
                      {new Date(p.created_at).toLocaleDateString("fr-FR")}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="leads" className="mt-6">
          {leadStats && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-3 mb-6" data-testid="admin-lead-stats">
              {[
                { label: "Total leads", value: leadStats.total, accent: false },
                { label: "Via page d'accueil", value: leadStats.landing, accent: false },
                { label: "Particuliers", value: leadStats.particulier, accent: true },
                { label: "Pros", value: leadStats.pro, accent: true },
                { label: "Nouveaux", value: leadStats.nouveau, accent: false },
                { label: "Gagnés", value: leadStats.gagne, accent: false },
              ].map((s) => (
                <div key={s.label}
                     className={`surface p-4 rounded-sm ${s.accent ? "border-primary/30" : ""}`}
                     data-testid={`admin-lead-stat-${s.label}`}>
                  <p className={`num text-2xl font-extrabold ${s.accent ? "text-primary" : "text-foreground"}`}>{s.value}</p>
                  <p className="text-xs text-muted-foreground mt-1">{s.label}</p>
                </div>
              ))}
            </div>
          )}
          <div className="flex flex-wrap items-center gap-2 mb-4" data-testid="admin-leads-filter">
            {[["all", "Tous"], ["nouveau", "Nouveaux"], ["contacté", "Contactés"],
              ["devis envoyé", "Devis envoyé"], ["gagné", "Gagnés"], ["perdu", "Perdus"],
              ["j2", "Relancés J+2"]].map(([v, lbl]) => (
              <button key={v} onClick={() => setLeadFilter(v)} data-testid={`admin-leads-filter-${v}`}
                className={`px-3 py-1.5 rounded-sm text-xs font-semibold border transition-colors ${leadFilter === v ? "bg-primary text-primary-foreground border-primary" : "border-border hover:border-primary/40"}`}>
                {lbl}
              </button>
            ))}
          </div>
          <div className="grid gap-3" data-testid="admin-leads-list">
            {(() => {
              const shown = leads.filter((l) =>
                leadFilter === "all" ? true : leadFilter === "j2" ? l.j2_reminded : l.status === leadFilter);
              return (<>
                {shown.length === 0 && <p className="surface p-10 text-center text-sm text-muted-foreground">Aucune demande.</p>}
                {shown.map((l) => (
              <div key={l.lead_id} className="surface p-6 grid gap-3">
                <div className="flex flex-wrap items-center gap-4">
                  <div>
                    <p className="font-display font-semibold">{l.name || l.email}</p>
                    <p className="num text-xs text-muted-foreground">{l.email}{l.phone ? " · " + l.phone : ""}</p>
                  </div>
                  {l.source && (
                    <span className="px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase tracking-wide bg-primary/10 text-primary border border-primary/20"
                          data-testid={`admin-lead-source-${l.lead_id}`}>
                      {l.source.replace("landing-hero-", "")}
                    </span>
                  )}
                  {l.j2_reminded && (
                    <span className="px-2 py-0.5 rounded-sm text-[10px] font-semibold uppercase tracking-wide bg-amber-500/15 text-amber-600 dark:text-amber-400 border border-amber-500/30"
                          data-testid={`admin-lead-j2-${l.lead_id}`} title={l.j2_reminded_at || ""}>
                      ✉ Relancé J+2
                    </span>
                  )}
                  {l.budget ? <p className="num ml-auto text-lg font-bold text-primary">{eur(l.budget)}</p> : <span className="ml-auto" />}
                  <Select
                    value={l.status}
                    onValueChange={async (v) => { await api.put(`/admin/leads/${l.lead_id}`, { status: v }); toast.success("Statut mis à jour"); load(); }}
                  >
                    <SelectTrigger className="rounded-sm h-9 w-40" data-testid={`admin-lead-status-${l.lead_id}`}><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {["nouveau", "contacté", "visite planifiée", "devis envoyé", "gagné", "perdu"].map((s) => (
                        <SelectItem key={s} value={s}>{s}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <p className="text-sm text-muted-foreground">{l.address} · {l.availability}</p>
                {l.description && <p className="text-sm">{l.description}</p>}
                {l.project_snapshot && (
                  <p className="num text-xs text-muted-foreground">
                    Projet : {l.project_snapshot.name} · {l.project_snapshot.surface} m² ·
                    estimation {eur(l.project_snapshot.estimation)} · lots : {(l.project_snapshot.lots || []).join(", ")}
                  </p>
                )}
              </div>
            ))}
              </>);
            })()}
          </div>
        </TabsContent>

        <TabsContent value="searches" className="mt-6">
          <div className="surface p-6">
            <p className="overline">Produits les plus recherchés</p>
            <div className="mt-5 grid gap-2" data-testid="admin-top-searches">
              {stats.top_searches.length === 0 && <p className="text-sm text-muted-foreground">Aucune recherche enregistrée.</p>}
              {stats.top_searches.map((s) => (
                <div key={s.query} className="flex items-center justify-between border-b border-border pb-2 text-sm">
                  <span>{s.query}</span>
                  <span className="num text-muted-foreground">{s.count} recherches</span>
                </div>
              ))}
            </div>
            <Button variant="outline" onClick={load} data-testid="admin-refresh-btn" className="mt-6 rounded-sm gap-2">
              <RefreshCw className="h-4 w-4" /> Actualiser
            </Button>
          </div>
        </TabsContent>

        <TabsContent value="promos" className="mt-6">
          <PromoCodesPanel />
        </TabsContent>

        <TabsContent value="kyc" className="mt-6">
          <KycPanel />
        </TabsContent>

        <TabsContent value="affiliate" className="mt-6">
          <AffiliatePanel />
        </TabsContent>

        <TabsContent value="plans" className="mt-6">
          <PlansRevenuePanel />
        </TabsContent>
        <TabsContent value="revenue" className="mt-6">
          <RevenueTab />
        </TabsContent>
        <TabsContent value="inbox" className="mt-6">
          <InboxPanel />
        </TabsContent>
        <TabsContent value="errors" className="mt-6">
          <ClientErrorsPanel />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/* ---------- Promo codes ---------- */
function PromoCodesPanel() {
  const [codes, setCodes] = useState([]);
  const [form, setForm] = useState({ code: "", percent_off: "", amount_off_cents: "", max_redemptions: "", duration: "once", name: "" });
  const [busy, setBusy] = useState(false);

  const load = () => api.get("/admin/promo-codes").then(({ data }) => setCodes(data)).catch(() => {});
  useEffect(() => { load(); }, []);

  const create = async () => {
    if (!form.code || (!form.percent_off && !form.amount_off_cents)) {
      return toast.error("Code + réduction (% ou €) requis");
    }
    setBusy(true);
    try {
      const payload = {
        code: form.code.toUpperCase().trim(),
        duration: form.duration,
        name: form.name || null,
        percent_off: form.percent_off ? Number(form.percent_off) : null,
        amount_off_cents: form.amount_off_cents ? Math.round(Number(form.amount_off_cents) * 100) : null,
        max_redemptions: form.max_redemptions ? Number(form.max_redemptions) : null,
      };
      await api.post("/admin/promo-codes", payload);
      toast.success("Code créé sur Stripe et activé");
      setForm({ code: "", percent_off: "", amount_off_cents: "", max_redemptions: "", duration: "once", name: "" });
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Création impossible");
    } finally { setBusy(false); }
  };

  const toggle = async (c, active) => {
    try {
      await api.patch(`/admin/promo-codes/${c.code}?active=${active}`);
      load();
    } catch { toast.error("Impossible"); }
  };

  return (
    <div className="grid gap-6">
      <div className="surface p-6 grid gap-4" data-testid="promo-form">
        <p className="overline">Créer un code promo</p>
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-3">
          <div className="grid gap-1.5">
            <Label className="text-xs">Code (ex: LANCEMENT10)</Label>
            <Input value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} className="rounded-sm h-10 uppercase" data-testid="promo-code-input" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Réduction %</Label>
            <Input type="number" value={form.percent_off} onChange={(e) => setForm({ ...form, percent_off: e.target.value, amount_off_cents: "" })} className="rounded-sm h-10 num" data-testid="promo-percent-input" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Ou montant € fixe</Label>
            <Input type="number" step="0.01" value={form.amount_off_cents} onChange={(e) => setForm({ ...form, amount_off_cents: e.target.value, percent_off: "" })} className="rounded-sm h-10 num" data-testid="promo-amount-input" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Utilisations max</Label>
            <Input type="number" value={form.max_redemptions} onChange={(e) => setForm({ ...form, max_redemptions: e.target.value })} className="rounded-sm h-10 num" data-testid="promo-max-input" />
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Récurrence</Label>
            <Select value={form.duration} onValueChange={(v) => setForm({ ...form, duration: v })}>
              <SelectTrigger className="rounded-sm h-10" data-testid="promo-duration"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="once">1 fois (premier paiement)</SelectItem>
                <SelectItem value="forever">Chaque paiement</SelectItem>
                <SelectItem value="repeating">3 mois (repeating)</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5">
            <Label className="text-xs">Nom interne (optionnel)</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="rounded-sm h-10" data-testid="promo-name-input" />
          </div>
        </div>
        <Button onClick={create} disabled={busy} data-testid="promo-create-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white justify-self-start">
          <Plus className="h-4 w-4" /> Créer le code
        </Button>
      </div>

      <div className="surface p-6">
        <p className="overline mb-4">Codes actifs ({codes.length})</p>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Code</TableHead><TableHead>Réduction</TableHead><TableHead>Utilisations max</TableHead>
            <TableHead>Statut</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody data-testid="promo-list">
            {codes.map((c) => (
              <TableRow key={c.code}>
                <TableCell className="font-mono">{c.code}</TableCell>
                <TableCell className="num">
                  {c.percent_off ? `${c.percent_off} %`
                   : c.amount_off_cents ? `${(c.amount_off_cents / 100).toFixed(2)} €` : "—"}
                </TableCell>
                <TableCell className="num">{c.max_redemptions || "illimité"}</TableCell>
                <TableCell>
                  <Badge variant={c.active ? "default" : "outline"} className="rounded-sm">
                    {c.active ? "Actif" : "Désactivé"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right">
                  <Button size="sm" variant="outline" onClick={() => toggle(c, !c.active)} className="rounded-sm">
                    {c.active ? "Désactiver" : "Activer"}
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {codes.length === 0 && (
              <TableRow><TableCell colSpan={5} className="text-center text-sm text-muted-foreground py-8">Aucun code promo</TableCell></TableRow>
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

/* ---------- Plans & Revenue ---------- */
function PlansRevenuePanel() {
  const { t } = useI18n();
  const [plans, setPlans] = useState([]);
  const [revenue, setRevenue] = useState(null);
  const [flags, setFlags] = useState({});
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.get("/admin/plans").then(({ data }) => setPlans(data));
    api.get("/admin/revenue").then(({ data }) => setRevenue(data));
    api.get("/admin/feature-flags").then(({ data }) => setFlags(data));
  };
  useEffect(() => { load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const saveFlags = async () => {
    setBusy(true);
    try {
      await api.put("/admin/feature-flags", flags);
      toast.success("Flags sauvegardés");
    } catch { toast.error("Impossible"); }
    finally { setBusy(false); }
  };

  const syncStripe = async () => {
    setBusy(true);
    try {
      await api.post("/admin/plans/sync-stripe");
      toast.success("Catalogue Stripe synchronisé");
      load();
    } catch { toast.error("Sync Stripe impossible"); }
    finally { setBusy(false); }
  };

  return (
    <div className="grid gap-6">
      {revenue && (
        <div className="grid md:grid-cols-4 gap-4" data-testid="admin-revenue-stats">
          <Stat label={t("admin.k_total_revenue")} value={eur(revenue.total_revenue_eur)} accent />
          <Stat label={t("admin.k_active_subs")} value={num(revenue.active_subscriptions)} />
          <Stat label={t("admin.k_active_pass")} value={num(revenue.active_project_pass)} />
          <Stat label={t("admin.k_transactions")} value={num(revenue.transactions_count)} />
        </div>
      )}

      <div className="surface p-6 grid gap-4" data-testid="admin-flags">
        <p className="overline">Feature flags</p>
        <div className="grid sm:grid-cols-2 md:grid-cols-3 gap-3">
          {["marketplace_enabled", "affiliate_enabled", "api_commercial_enabled",
            "white_label_enabled", "referral_enabled", "promo_codes_enabled",
            "trial_enabled"].map((k) => (
            <label key={k} className="flex items-center gap-2 text-sm border border-border rounded-sm p-3 cursor-pointer">
              <input type="checkbox" checked={!!flags[k]} onChange={(e) => setFlags({ ...flags, [k]: e.target.checked })} data-testid={`flag-${k}`} />
              <span className="font-mono text-xs">{k}</span>
            </label>
          ))}
          <div className="border border-border rounded-sm p-3 text-sm">
            <Label className="text-xs">Trial (jours)</Label>
            <Input type="number" value={flags.trial_days || 7} onChange={(e) => setFlags({ ...flags, trial_days: Number(e.target.value) })} className="rounded-sm h-9 num mt-1" />
          </div>
          <div className="border border-border rounded-sm p-3 text-sm">
            <Label className="text-xs">Paywall mode</Label>
            <Select value={flags.paywall_mode || "soft"} onValueChange={(v) => setFlags({ ...flags, paywall_mode: v })}>
              <SelectTrigger className="rounded-sm h-9 mt-1"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="soft">Soft (recommandé)</SelectItem>
                <SelectItem value="hard">Hard (bloquant)</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="flex gap-3">
          <Button onClick={saveFlags} disabled={busy} data-testid="save-flags-btn" className="rounded-sm hover:bg-orange-600 hover:text-white gap-2">
            <Save className="h-4 w-4" /> Sauvegarder les flags
          </Button>
          <Button variant="outline" onClick={syncStripe} disabled={busy} data-testid="sync-stripe-btn" className="rounded-sm gap-2">
            <RefreshCw className="h-4 w-4" /> Synchroniser Stripe
          </Button>
        </div>
      </div>

      <div className="surface p-6" data-testid="admin-plans-table">
        <p className="overline mb-4">Plans configurés ({plans.length})</p>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Nom</TableHead><TableHead>Code</TableHead><TableHead>Public</TableHead>
            <TableHead>Prix</TableHead><TableHead>Type</TableHead><TableHead>Stripe Price ID</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {plans.map((p) => (
              <TableRow key={p.plan_id}>
                <TableCell>{p.name}</TableCell>
                <TableCell className="font-mono text-xs">{p.code}</TableCell>
                <TableCell><Badge variant="outline" className="rounded-sm">{p.audience}</Badge></TableCell>
                <TableCell className="num">{(p.amount_cents / 100).toFixed(2)} € {p.interval ? `/ ${p.interval}` : ""}</TableCell>
                <TableCell>{p.kind}</TableCell>
                <TableCell className="font-mono text-[10px] text-muted-foreground">{p.stripe_price_id || "—"}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}


/* ---------- KYC review ---------- */
function KycPanel() {
  const [rows, setRows] = useState([]);
  const [filter, setFilter] = useState("pending");
  const load = () => api.get(`/admin/kyc${filter ? "?status=" + filter : ""}`).then(({ data }) => setRows(data)).catch(() => {});
  useEffect(() => { load(); }, [filter]); // eslint-disable-line react-hooks/exhaustive-deps
  const act = async (user_id, approve, reason) => {
    try { await api.post("/admin/kyc/review", { user_id, approve, reason: reason || null }); load(); }
    catch { toast.error("Impossible"); }
  };
  return (
    <div className="grid gap-4">
      <div className="flex gap-2" data-testid="kyc-filters">
        {["pending", "verified", "rejected", ""].map((s) => (
          <button key={s || "all"} onClick={() => setFilter(s)}
                  className={`px-3 py-2 text-xs rounded-sm border ${filter === s ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground"}`}>
            {s || "Tous"}
          </button>
        ))}
      </div>
      <div className="surface p-6" data-testid="kyc-list">
        <Table>
          <TableHeader><TableRow>
            <TableHead>Entreprise</TableHead><TableHead>SIREN</TableHead><TableHead>Métiers</TableHead>
            <TableHead>Statut</TableHead><TableHead className="text-right">Actions</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.user_id}>
                <TableCell>{r.company_name || "—"}</TableCell>
                <TableCell className="font-mono text-xs">{r.siren || "—"}</TableCell>
                <TableCell className="text-xs">{(r.trades || []).slice(0, 3).join(", ")}</TableCell>
                <TableCell>
                  <Badge variant={r.verified ? "default" : "outline"} className="rounded-sm">
                    {r.status || "pending"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right space-x-2">
                  {!r.verified && (
                    <>
                      <Button size="sm" onClick={() => act(r.user_id, true)} data-testid={`kyc-approve-${r.user_id}`} className="rounded-sm hover:bg-orange-600 hover:text-white">Valider</Button>
                      <Button size="sm" variant="outline" onClick={() => { const reason = prompt("Motif du refus ?"); if (reason) act(r.user_id, false, reason); }} data-testid={`kyc-reject-${r.user_id}`} className="rounded-sm">Refuser</Button>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {rows.length === 0 && <TableRow><TableCell colSpan={5} className="text-center py-8 text-sm text-muted-foreground">Aucun dossier</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

/* ---------- Inbox — Demandes & activité ---------- */
function InboxPanel() {
  const { t } = useI18n();
  const [hours, setHours] = useState(168);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  const load = () => {
    setLoading(true);
    api.get(`/admin/inbox?hours=${hours}`)
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Chargement impossible"))
      .finally(() => setLoading(false));
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [hours]);

  const [pendingReviews, setPendingReviews] = useState([]);
  const loadPendingReviews = () => api.get("/reviews/site/pending")
    .then(({ data }) => setPendingReviews(data.reviews || [])).catch(() => {});
  useEffect(() => { loadPendingReviews(); }, []);

  const approveReview = async (id) => {
    try { await api.post(`/reviews/site/${id}/approve`); toast.success("Avis publié"); loadPendingReviews(); }
    catch { toast.error("Action impossible"); }
  };
  const deleteReview = async (id) => {
    try { await api.delete(`/reviews/site/${id}`); toast.success("Avis supprimé"); loadPendingReviews(); }
    catch { toast.error("Action impossible"); }
  };

  const exportDeckCsv = async () => {
    try {
      const { data } = await api.get("/investors/deck-requests.csv", { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "text/csv" }));
      const a = document.createElement("a");
      a.href = url; a.download = "leads-investisseurs.csv"; a.click();
      URL.revokeObjectURL(url);
      toast.success("Export CSV téléchargé");
    } catch {
      toast.error("Export impossible");
    }
  };

  return (
    <div className="grid gap-6" data-testid="admin-inbox-panel">
      <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
        <Stat label={t("admin.k_new_leads")} value={num(data?.counts?.new_leads || 0)} accent={data?.counts?.new_leads > 0} />
        <Stat label={t("admin.k_new_users")} value={num(data?.counts?.new_users || 0)} />
        <Stat label={t("admin.k_quotes_sent")} value={num(data?.counts?.quotes_sent || 0)} />
        <Stat label={t("admin.k_quotes_signed")} value={num(data?.counts?.quotes_signed || 0)} accent />
        <Stat label={t("admin.k_quotes_opened")} value={num(data?.counts?.quotes_opened || 0)} />
        <Stat label={t("admin.k_client_errors")} value={num(data?.counts?.client_errors || 0)} accent={data?.counts?.client_errors > 0} />
        <Stat label="Deck investisseurs" value={num(data?.counts?.deck_downloads || 0)} accent={data?.counts?.deck_downloads > 0} />
      </div>

      <div className="surface p-4 flex gap-2 items-center flex-wrap">
        <span className="text-xs text-muted-foreground mr-2">Fenêtre :</span>
        {[24, 168, 720].map((h) => (
          <Button
            key={h}
            size="sm"
            variant={hours === h ? "default" : "outline"}
            onClick={() => setHours(h)}
            data-testid={`inbox-window-${h}h`}
            className="rounded-sm"
          >
            {h === 24 ? "24h" : h === 168 ? "7 jours" : "30 jours"}
          </Button>
        ))}
        <div className="flex-1" />
        <Button size="sm" variant="outline" onClick={load} className="rounded-sm"
                data-testid="inbox-refresh-btn">Actualiser</Button>
      </div>

      {loading && <p className="text-sm text-muted-foreground">Chargement…</p>}

      {data && (
        <>
          <InboxSection title="Leads reçus" items={data.leads || []} empty="Aucun lead sur la période.">
            {(l) => <LeadRow lead={l} onUpdated={load} />}
          </InboxSection>

          <InboxSection title="Nouveaux comptes" items={data.new_users || []} empty="Aucun nouvel utilisateur.">
            {(u) => (
              <div className="flex items-center justify-between text-xs">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold truncate">{u.name || u.email}</p>
                  <p className="text-muted-foreground truncate">
                    {u.email} · rôle <b>{u.role || "user"}</b> · plan {u.plan || "free"}
                  </p>
                </div>
                <span className="text-[10px] text-muted-foreground ml-2">
                  {u.created_at?.slice(0, 10)}
                </span>
              </div>
            )}
          </InboxSection>

          <InboxSection title="Devis récents (activité pros)" items={data.recent_sends || []} empty="Aucun devis envoyé sur la période.">
            {(s) => (
              <div className="flex items-center justify-between text-xs">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold truncate">→ {s.client_email}</p>
                  <p className="text-muted-foreground truncate">
                    {s.client_name || "—"} · <span className="num">{(s.total_ttc || 0).toLocaleString("fr-FR")} €</span>
                  </p>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-sm border ml-2 whitespace-nowrap
                  ${s.signed ? "bg-green-500/15 text-green-600 border-green-500/40"
                             : s.opened_at ? "bg-amber-500/15 text-amber-600 border-amber-500/40"
                                            : "bg-secondary text-muted-foreground border-border"}`}>
                  {s.signed ? "signé" : s.opened_at ? "ouvert" : "envoyé"}
                </span>
              </div>
            )}
          </InboxSection>

          <div className="surface p-5" data-testid="pending-reviews-section">
            <p className="overline mb-3">Avis clients en attente ({pendingReviews.length})</p>
            {pendingReviews.length === 0 ? (
              <p className="text-xs text-muted-foreground">Aucun avis à modérer.</p>
            ) : (
              <div className="grid gap-2">
                {pendingReviews.map((r) => (
                  <div key={r.review_id} className="flex items-start justify-between gap-3 border-b border-border pb-2" data-testid={`pending-review-${r.review_id}`}>
                    <div className="min-w-0">
                      <p className="text-xs font-semibold">{r.name}{r.role ? ` · ${r.role}` : ""} <span className="text-primary">{"★".repeat(r.rating)}</span></p>
                      <p className="text-xs text-muted-foreground">« {r.comment} »</p>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      <button onClick={() => approveReview(r.review_id)} data-testid={`approve-review-${r.review_id}`}
                              className="text-[10px] px-2 py-1 rounded-sm bg-primary text-primary-foreground font-semibold">Publier</button>
                      <button onClick={() => deleteReview(r.review_id)} data-testid={`delete-review-${r.review_id}`}
                              className="text-[10px] px-2 py-1 rounded-sm border border-border text-muted-foreground">Suppr.</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          <InboxSection title="Téléchargements pitch deck (VC)" items={data.deck_downloads || []} empty="Aucun téléchargement du pitch deck sur la période."
            action={
              <Button size="sm" variant="outline" className="rounded-sm gap-2 h-8"
                      data-testid="deck-export-csv-btn" onClick={exportDeckCsv}>
                <Download className="h-3.5 w-3.5" /> Exporter CSV
              </Button>
            }>
            {(d) => (
              <div className="flex items-center justify-between text-xs" data-testid="inbox-deck-row">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold truncate">
                    {d.name || "—"}{d.fund ? ` · ${d.fund}` : ""}
                  </p>
                  <p className="text-muted-foreground truncate">
                    <a href={`mailto:${d.email}`} className="hover:underline">{d.email}</a>
                    {d.note ? ` · ${d.note}` : ""}
                  </p>
                </div>
                <span className="text-[10px] text-muted-foreground ml-2 whitespace-nowrap">
                  {d.created_at?.slice(0, 16).replace("T", " ")}
                </span>
              </div>
            )}
          </InboxSection>

          <InboxSection title="Erreurs client (extrait)" items={(data.recent_errors || []).slice(0, 10)} empty="Aucune erreur sur la période.">
            {(e) => (
              <div className="text-xs">
                <p className="font-mono font-semibold break-all">{e.message}</p>
                <p className="text-muted-foreground">
                  {e.created_at?.slice(0, 19).replace("T", " ")}
                  {e.url ? ` · ${e.url}` : ""}
                  {e.user_id ? ` · user ${e.user_id}` : ""}
                </p>
              </div>
            )}
          </InboxSection>
        </>
      )}
    </div>
  );
}

function InboxSection({ title, items, empty, children, action }) {
  return (
    <div className="surface p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="overline">{title} ({items.length})</p>
        {action}
      </div>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground py-2">{empty}</p>
      ) : (
        <div className="grid gap-2">
          {items.map((it, i) => (
            <div key={i} className="border border-border rounded-sm p-3">
              {children(it)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/* ---------- LeadRow with direct actions (call / email / mark handled) ---------- */
function LeadRow({ lead, onUpdated }) {
  const [status, setStatus] = useState(lead.status || "nouveau");
  const [busy, setBusy] = useState(false);

  const setLeadStatus = async (next) => {
    setBusy(true);
    try {
      await api.put(`/admin/leads/${lead.lead_id}`, { status: next });
      setStatus(next);
      toast.success(`Statut : ${next}`);
      if (onUpdated) onUpdated();
    } catch { toast.error("Mise à jour impossible"); }
    setBusy(false);
  };

  const isDone = ["handled", "won", "lost", "traité"].includes(status);
  return (
    <div className="grid grid-cols-1 sm:grid-cols-[1fr_auto] gap-3 text-xs items-center"
         data-testid={`lead-row-${lead.lead_id}`}>
      <div className="min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className={`font-semibold truncate ${isDone ? "line-through opacity-60" : ""}`}>
            {lead.name || lead.email || "—"}
          </p>
          <span className={`text-[9px] px-1.5 py-0.5 rounded-sm border uppercase tracking-wider whitespace-nowrap
            ${isDone ? "bg-green-500/15 text-green-600 border-green-500/40"
                      : status === "en_cours" ? "bg-amber-500/15 text-amber-600 border-amber-500/40"
                                              : "bg-primary/15 text-primary border-primary/40"}`}>
            {status}
          </span>
        </div>
        <p className="text-muted-foreground truncate">
          {lead.email || "—"}{lead.phone ? ` · ${lead.phone}` : ""}
          {lead.budget ? ` · budget ${lead.budget} €` : ""}
        </p>
        {lead.description && (
          <p className="text-[11px] text-muted-foreground mt-1 line-clamp-2">
            "{lead.description}"
          </p>
        )}
      </div>
      <div className="flex items-center gap-1.5 flex-wrap justify-end">
        {lead.phone && (
          <a
            href={`tel:${lead.phone}`}
            data-testid={`lead-call-${lead.lead_id}`}
            className="rounded-sm border border-border p-1.5 hover:bg-primary hover:text-white hover:border-primary transition"
            title={`Appeler ${lead.phone}`}
          >
            <Phone className="h-3.5 w-3.5" />
          </a>
        )}
        {lead.email && (
          <a
            href={`mailto:${lead.email}?subject=${encodeURIComponent(
              `Re : votre demande ConstruPilot${lead.description ? " · " + lead.description.slice(0, 40) : ""}`
            )}`}
            data-testid={`lead-email-${lead.lead_id}`}
            className="rounded-sm border border-border p-1.5 hover:bg-primary hover:text-white hover:border-primary transition"
            title={`Écrire à ${lead.email}`}
          >
            <Mail className="h-3.5 w-3.5" />
          </a>
        )}
        {!isDone ? (
          <>
            <Button
              size="sm" variant="outline"
              disabled={busy}
              onClick={() => setLeadStatus("en_cours")}
              data-testid={`lead-inprogress-${lead.lead_id}`}
              className="rounded-sm h-7 text-[10px]"
            >
              En cours
            </Button>
            <Button
              size="sm"
              disabled={busy}
              onClick={() => setLeadStatus("handled")}
              data-testid={`lead-handled-${lead.lead_id}`}
              className="rounded-sm h-7 text-[10px]"
            >
              <CheckCircle2 className="h-3 w-3 mr-1" /> Traité
            </Button>
          </>
        ) : (
          <Button
            size="sm" variant="outline"
            disabled={busy}
            onClick={() => setLeadStatus("nouveau")}
            className="rounded-sm h-7 text-[10px]"
          >
            Rouvrir
          </Button>
        )}
      </div>
    </div>
  );
}

/* ---------- Client Errors (ErrorBoundary reports) ---------- */
function ClientErrorsPanel() {
  const { t } = useI18n();
  const [hours, setHours] = useState(24);
  const [data, setData] = useState(null);
  const [trend, setTrend] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState({});

  const load = () => {
    setLoading(true);
    api.get(`/errors/admin/list?hours=${hours}&limit=200`)
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Chargement impossible"))
      .finally(() => setLoading(false));
    api.get(`/errors/admin/trend?days=14`).then(({ data }) => setTrend(data)).catch(() => {});
  };
  useEffect(() => { load(); /* eslint-disable-next-line */ }, [hours]);

  return (
    <div className="grid gap-6" data-testid="admin-client-errors-panel">
      <div className="flex items-center justify-between">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 flex-1">
          <Stat label={t("admin.k_total_errors")} value={num(data?.total || 0)} accent={(data?.total || 0) > 0} />
          <Stat label={t("admin.k_unique_msgs")} value={num(data?.top_messages?.length || 0)} />
          <Stat label={t("admin.k_window")} value={`${hours}h`} />
          <Stat label={t("admin.k_users_affected")} value={num(
            new Set((data?.items || []).map((i) => i.user_id).filter(Boolean)).size)} />
        </div>
      </div>
      <div className="surface p-4 flex gap-2 items-center">
        <span className="text-xs text-muted-foreground mr-2">Fenêtre :</span>
        {[1, 24, 168, 720].map((h) => (
          <Button
            key={h}
            size="sm"
            variant={hours === h ? "default" : "outline"}
            onClick={() => setHours(h)}
            data-testid={`errors-window-${h}h`}
            className="rounded-sm"
          >
            {h === 1 ? "1h" : h === 24 ? "24h" : h === 168 ? "7j" : "30j"}
          </Button>
        ))}
        <div className="flex-1" />
        <Button size="sm" variant="outline" onClick={load} className="rounded-sm"
                data-testid="errors-refresh-btn">Actualiser</Button>
      </div>

      {trend && trend.series && (
        <div className="surface p-4" data-testid="errors-trend-graph">
          <div className="flex items-center justify-between mb-2">
            <h4 className="font-bold text-sm">Évolution des erreurs client (14 jours)</h4>
            <span className="text-xs text-muted-foreground">{num(trend.total)} au total</span>
          </div>
          <div className="flex items-end gap-1 h-24">
            {(() => { const mx = Math.max(1, ...trend.series.map((d) => d.count)); return trend.series.map((d, i) => (
              <div key={i} className="flex-1 flex flex-col items-center justify-end group" data-testid={`errors-bar-${i}`}>
                <div className={`w-full rounded-t-sm ${d.count > 0 ? "bg-red-500/70 group-hover:bg-red-500" : "bg-secondary"} transition-colors`}
                  style={{ height: `${Math.max(3, (d.count / mx) * 100)}%` }} title={`${d.day} : ${d.count}`} />
              </div>
            )); })()}
          </div>
          <div className="flex justify-between text-[10px] text-muted-foreground mt-1">
            <span>{trend.series[0]?.day?.slice(5)}</span>
            <span>{trend.series[trend.series.length - 1]?.day?.slice(5)}</span>
          </div>
          <p className="text-[11px] text-muted-foreground mt-1">Utile pour vérifier la baisse après un correctif (ex. WebGL).</p>
        </div>
      )}

      {loading && <p className="text-sm text-muted-foreground">Chargement…</p>}

      {!loading && data && (
        <>
          <div className="surface p-6">
            <p className="overline mb-4">Top 10 des messages (regroupés)</p>
            {(data.top_messages || []).length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                Aucune erreur sur la période — tout va bien.
              </p>
            ) : (
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Message</TableHead>
                  <TableHead className="w-24 text-right">Occurrences</TableHead>
                  <TableHead className="w-24 text-right">Utilisateurs</TableHead>
                  <TableHead className="w-40">Dernière fois</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {data.top_messages.map((t, i) => (
                    <TableRow key={i} data-testid={`error-top-row-${i}`}>
                      <TableCell className="text-xs font-mono break-all">{t.message}</TableCell>
                      <TableCell className="num text-right font-bold text-destructive">{t.count}</TableCell>
                      <TableCell className="num text-right">{t.affected_users}</TableCell>
                      <TableCell className="text-xs text-muted-foreground">
                        {t.last_seen?.slice(0, 16).replace("T", " ")}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>

          <div className="surface p-6">
            <p className="overline mb-4">Événements bruts ({data.items?.length || 0})</p>
            {(data.items || []).length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">Rien à afficher.</p>
            ) : (
              <div className="grid gap-2">
                {data.items.map((it, i) => (
                  <div key={i} className="border border-border rounded-sm p-3 text-xs"
                       data-testid={`error-item-${i}`}>
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="font-mono break-all font-semibold">{it.message}</p>
                        <p className="text-muted-foreground mt-1">
                          {it.created_at?.slice(0, 19).replace("T", " ")}
                          {it.url && <> · <span className="break-all">{it.url}</span></>}
                          {it.user_id && <> · user <code>{it.user_id}</code></>}
                        </p>
                      </div>
                      <button
                        onClick={() => setExpanded((e) => ({ ...e, [i]: !e[i] }))}
                        className="text-primary text-[11px] whitespace-nowrap"
                        data-testid={`error-toggle-${i}`}
                      >
                        {expanded[i] ? "Masquer" : "Stack"}
                      </button>
                    </div>
                    {expanded[i] && it.stack && (
                      <pre className="mt-2 p-2 bg-secondary/30 rounded-sm text-[10px]
                                       overflow-x-auto whitespace-pre-wrap break-all">
                        {it.stack}
                      </pre>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/* ---------- Affiliate ---------- */
function AffiliatePanel() {
  const { t } = useI18n();
  const [configs, setConfigs] = useState([]);
  const [stats, setStats] = useState(null);
  const load = () => {
    api.get("/admin/affiliate/configs").then(({ data }) => setConfigs(data));
    api.get("/admin/affiliate/stats?days=30").then(({ data }) => setStats(data));
  };
  useEffect(() => { load(); }, []);
  const toggle = async (cfg, enabled) => {
    try { await api.post("/admin/affiliate/configs", { ...cfg, affiliate_enabled: enabled }); load(); }
    catch { toast.error("Impossible"); }
  };
  return (
    <div className="grid gap-6" data-testid="affiliate-panel">
      {stats && (
        <div className="grid md:grid-cols-4 gap-4">
          <Stat label={t("admin.k_clicks")} value={num(stats.totals.affiliate_click || 0)} />
          <Stat label={t("admin.k_redirects")} value={num(stats.totals.supplier_redirect || 0)} />
          <Stat label={t("admin.k_conversions")} value={num(stats.totals.purchase_confirmed || 0)} />
          <Stat label={t("admin.k_revenue_eur")} value={eur(stats.revenue_eur)} accent />
        </div>
      )}
      <div className="surface p-6">
        <p className="overline mb-4">Configurations partenaires</p>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Fournisseur</TableHead><TableHead>Réseau</TableHead>
            <TableHead>Commission</TableHead><TableHead>Cookie</TableHead>
            <TableHead>Actif</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {configs.map((c) => (
              <TableRow key={c.supplier_key}>
                <TableCell className="font-medium">{c.supplier_key}</TableCell>
                <TableCell>{c.affiliate_network || "—"}</TableCell>
                <TableCell className="num">{((c.commission_rate || 0) * 100).toFixed(1)} %</TableCell>
                <TableCell className="num">{c.cookie_duration} j</TableCell>
                <TableCell>
                  <input type="checkbox" checked={!!c.affiliate_enabled}
                         onChange={(e) => toggle(c, e.target.checked)}
                         data-testid={`aff-toggle-${c.supplier_key}`} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

