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
  useEffect(load, []);

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
      <SectionTitle over="Back-office CMRENOV" title="Administration">
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
      </Tabs>
    </div>
  );
}
