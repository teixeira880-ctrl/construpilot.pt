import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Shield, Save, Plus, Trash2, RefreshCw } from "lucide-react";
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
import { Stat, SectionTitle } from "@/components/Bits";

export default function Admin() {
  const [stats, setStats] = useState(null);
  const [prices, setPrices] = useState([]);
  const [edits, setEdits] = useState({});
  const [regions, setRegions] = useState([]);
  const [users, setUsers] = useState([]);
  const [projects, setProjects] = useState([]);
  const [leads, setLeads] = useState([]);
  const [suppliers, setSuppliers] = useState({ builtin: [], custom: [] });
  const [newSup, setNewSup] = useState({ key: "", name: "", domain: "", shipping: 30, free_from: 300 });

  const load = () => {
    api.get("/admin/stats").then(({ data }) => setStats(data));
    api.get("/admin/prices").then(({ data }) => setPrices(data));
    api.get("/admin/regions").then(({ data }) => setRegions(data));
    api.get("/admin/users").then(({ data }) => setUsers(data));
    api.get("/admin/projects").then(({ data }) => setProjects(data));
    api.get("/admin/leads").then(({ data }) => setLeads(data));
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
      <SectionTitle over="Back-office ConstruPilot" title="Administration">
        Prix de référence, coefficients régionaux, fournisseurs, utilisateurs, projets et demandes de devis.
      </SectionTitle>

      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 stagger">
        <Stat label="Utilisateurs" value={num(stats.users)} testId="admin-stat-users" />
        <Stat label="Projets" value={num(stats.projects)} testId="admin-stat-projects" />
        <Stat label="Demandes de devis" value={num(stats.leads)} testId="admin-stat-leads" accent />
        <Stat label="Devis analysés" value={num(stats.quote_analyses)} testId="admin-stat-quotes" />
        <Stat label="Volume estimé" value={eur(stats.estimated_volume)} testId="admin-stat-volume" />
      </div>

      <Tabs defaultValue="prices">
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="prices" className="rounded-sm" data-testid="admin-tab-prices">Prix de référence</TabsTrigger>
          <TabsTrigger value="regions" className="rounded-sm" data-testid="admin-tab-regions">Coefficients régionaux</TabsTrigger>
          <TabsTrigger value="suppliers" className="rounded-sm" data-testid="admin-tab-suppliers">Fournisseurs</TabsTrigger>
          <TabsTrigger value="users" className="rounded-sm" data-testid="admin-tab-users">Utilisateurs</TabsTrigger>
          <TabsTrigger value="projects" className="rounded-sm" data-testid="admin-tab-projects">Projets</TabsTrigger>
          <TabsTrigger value="leads" className="rounded-sm" data-testid="admin-tab-leads">CRM / Devis</TabsTrigger>
          <TabsTrigger value="searches" className="rounded-sm" data-testid="admin-tab-searches">Recherches</TabsTrigger>
          <TabsTrigger value="promos" className="rounded-sm" data-testid="admin-tab-promos">Codes promo</TabsTrigger>
          <TabsTrigger value="kyc" className="rounded-sm" data-testid="admin-tab-kyc">KYC pros</TabsTrigger>
          <TabsTrigger value="affiliate" className="rounded-sm" data-testid="admin-tab-affiliate">Affiliation</TabsTrigger>
          <TabsTrigger value="plans" className="rounded-sm" data-testid="admin-tab-plans">Plans & Revenu</TabsTrigger>
        </TabsList>

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
          <div className="grid gap-3" data-testid="admin-leads-list">
            {leads.length === 0 && <p className="surface p-10 text-center text-sm text-muted-foreground">Aucune demande.</p>}
            {leads.map((l) => (
              <div key={l.lead_id} className="surface p-6 grid gap-3">
                <div className="flex flex-wrap items-center gap-4">
                  <div>
                    <p className="font-display font-semibold">{l.name}</p>
                    <p className="num text-xs text-muted-foreground">{l.email} · {l.phone}</p>
                  </div>
                  <p className="num ml-auto text-lg font-bold text-primary">{eur(l.budget)}</p>
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
          <Stat label="Revenu total" value={eur(revenue.total_revenue_eur)} accent />
          <Stat label="Abonnements actifs" value={num(revenue.active_subscriptions)} />
          <Stat label="Project Pass actifs" value={num(revenue.active_project_pass)} />
          <Stat label="Transactions" value={num(revenue.transactions_count)} />
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

/* ---------- Affiliate ---------- */
function AffiliatePanel() {
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
          <Stat label="Clics (30j)" value={num(stats.totals.affiliate_click || 0)} />
          <Stat label="Redirections" value={num(stats.totals.supplier_redirect || 0)} />
          <Stat label="Conversions" value={num(stats.totals.purchase_confirmed || 0)} />
          <Stat label="Revenu (€)" value={eur(stats.revenue_eur)} accent />
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

