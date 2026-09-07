import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Key, Copy, Trash2, RefreshCw, Plus, Shield, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogDescription } from "@/components/ui/dialog";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SectionTitle } from "@/components/Bits";

export default function ApiKeys() {
  const { user } = useAuth();
  const [keys, setKeys] = useState([]);
  const [plans, setPlans] = useState([]);
  const [form, setForm] = useState({ plan_id: "api_starter", name: "" });
  const [busy, setBusy] = useState(false);
  const [freshKey, setFreshKey] = useState(null);

  const load = () => {
    api.get("/api-keys").then(({ data }) => setKeys(data)).catch(() => {});
    api.get("/plans?audience=api").then(({ data }) => setPlans(data.plans || [])).catch(() => {});
  };
  useEffect(() => { if (user) load(); }, [user]);

  const create = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/api-keys", form);
      setFreshKey(data);
      toast.success("Clé créée — copiez-la, elle ne sera plus affichée");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Impossible de créer la clé");
    } finally { setBusy(false); }
  };

  const rotate = async (prefix) => {
    if (!confirm("Rotation : ancienne clé désactivée immédiatement.")) return;
    try {
      const { data } = await api.post(`/api-keys/${prefix}/rotate`);
      setFreshKey(data);
      load();
    } catch { toast.error("Impossible"); }
  };
  const revoke = async (prefix) => {
    if (!confirm("Révoquer cette clé ? Les appels échoueront immédiatement.")) return;
    try { await api.delete(`/api-keys/${prefix}`); load(); }
    catch { toast.error("Impossible"); }
  };

  const copy = async (v) => { try { await navigator.clipboard.writeText(v); toast.success("Copié"); } catch { toast.error("Copie impossible"); } };

  if (!user) return <div className="surface p-10 text-center">Connectez-vous.</div>;

  return (
    <div className="grid gap-8">
      <SectionTitle over="API ConstruPilot" title="Intégrez notre moteur d'estimation dans vos outils">
        Construisez un simulateur de rénovation, un devis ou un outil interne à partir de nos endpoints
        <code className="mx-1 text-xs bg-secondary px-1.5 rounded-sm">/api/v1/public/estimation</code>,
        <code className="mx-1 text-xs bg-secondary px-1.5 rounded-sm">/prices</code> et
        <code className="mx-1 text-xs bg-secondary px-1.5 rounded-sm">/calculators</code>.
      </SectionTitle>

      <div className="surface p-6 grid gap-4" data-testid="api-key-create">
        <div className="flex items-center gap-2"><Key className="h-4 w-4 text-primary" /><p className="overline">Nouvelle clé API</p></div>
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="grid gap-2">
            <Label>Plan</Label>
            <Select value={form.plan_id} onValueChange={(v) => setForm({ ...form, plan_id: v })}>
              <SelectTrigger className="rounded-sm h-10" data-testid="api-key-plan"><SelectValue /></SelectTrigger>
              <SelectContent>
                {plans.map((p) => (
                  <SelectItem key={p.plan_id} value={p.plan_id}>
                    {p.name} — {(p.amount_cents / 100).toFixed(0)} €/mois · {p.quotas?.api_calls_monthly?.toLocaleString("pt-PT")} appels
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label>Nom (ex : Production)</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="api-key-name" className="rounded-sm h-10" />
          </div>
        </div>
        <Button onClick={create} disabled={busy} data-testid="api-key-create-btn" className="rounded-sm gap-2 justify-self-start hover:bg-orange-600 hover:text-white">
          <Plus className="h-4 w-4" /> Générer la clé
        </Button>
        <p className="text-xs text-muted-foreground">
          La clé complète ne sera affichée qu'une seule fois — stockez-la immédiatement dans votre gestionnaire de secrets.
        </p>
      </div>

      <Dialog open={!!freshKey} onOpenChange={(o) => !o && setFreshKey(null)}>
        <DialogContent className="rounded-sm sm:max-w-lg" data-testid="fresh-key-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl">Votre nouvelle clé API</DialogTitle>
            <DialogDescription>Copiez-la maintenant — elle ne sera plus affichée en clair.</DialogDescription>
          </DialogHeader>
          <div className="p-3 border border-primary/40 bg-primary/5 rounded-sm break-all font-mono text-sm" data-testid="fresh-key-value">
            {freshKey?.key}
          </div>
          <Button onClick={() => copy(freshKey?.key)} className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Copy className="h-4 w-4" /> Copier
          </Button>
        </DialogContent>
      </Dialog>

      <div className="surface p-6">
        <p className="overline mb-4">Clés actives ({keys.length})</p>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Nom</TableHead><TableHead>Préfixe</TableHead>
            <TableHead>Plan</TableHead><TableHead>Quota / mois</TableHead>
            <TableHead>Estado</TableHead><TableHead className="text-right">Ações</TableHead>
          </TableRow></TableHeader>
          <TableBody data-testid="api-keys-list">
            {keys.map((k) => (
              <TableRow key={k.prefix}>
                <TableCell>{k.name}</TableCell>
                <TableCell className="font-mono text-xs">{k.prefix}…</TableCell>
                <TableCell>{k.plan_id}</TableCell>
                <TableCell className="num">{k.monthly_quota?.toLocaleString("pt-PT")}</TableCell>
                <TableCell>
                  <Badge variant={k.active ? "default" : "outline"} className="rounded-sm">
                    {k.active ? "Actif" : "Révoqué"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right space-x-2">
                  <Button size="sm" variant="outline" onClick={() => rotate(k.prefix)} className="rounded-sm gap-1" data-testid={`api-key-rotate-${k.prefix}`}>
                    <RefreshCw className="h-3 w-3" /> Rotate
                  </Button>
                  {k.active && (
                    <Button size="sm" variant="outline" onClick={() => revoke(k.prefix)} className="rounded-sm gap-1" data-testid={`api-key-revoke-${k.prefix}`}>
                      <Trash2 className="h-3 w-3" /> Révoquer
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {keys.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-8">Aucune clé pour l'instant</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      <div className="surface p-6 grid gap-3">
        <div className="flex items-center gap-2"><Rocket className="h-4 w-4 text-primary" /><p className="overline">Exemple d'appel</p></div>
        <pre className="text-xs bg-secondary/40 p-4 rounded-sm overflow-x-auto"><code>{`curl -X POST https://pilot-build-demo.preview.emergentagent.com/api/v1/public/estimation \\
  -H "X-API-Key: ckp_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"project_type":"renovation_partielle","surface":40,"finish_level":"standard"}'`}</code></pre>
      </div>
    </div>
  );
}
