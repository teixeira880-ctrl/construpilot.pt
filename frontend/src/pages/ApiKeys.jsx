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
      toast.success("Chave criada — copie-a, não será mais exibida");
      load();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Impossível criar a chave");
    } finally { setBusy(false); }
  };

  const rotate = async (prefix) => {
    if (!confirm("Rotação: chave antiga desativada imediatamente.")) return;
    try {
      const { data } = await api.post(`/api-keys/${prefix}/rotate`);
      setFreshKey(data);
      load();
    } catch { toast.error("Impossível"); }
  };
  const revoke = async (prefix) => {
    if (!confirm("Revogar esta chave? As chamadas falharão imediatamente.")) return;
    try { await api.delete(`/api-keys/${prefix}`); load(); }
    catch { toast.error("Impossível"); }
  };

  const copy = async (v) => { try { await navigator.clipboard.writeText(v); toast.success("Copiado"); } catch { toast.error("Cópia impossível"); } };

  if (!user) return <div className="surface p-10 text-center">Ligue-se.</div>;

  return (
    <div className="grid gap-8">
      <SectionTitle over="API ConstruPilot" title="Integre o nosso motor de estimativa nas suas ferramentas">
        Construa um simulador de renovação, um orçamento ou uma ferramenta interna a partir dos nossos endpoints
        <code className="mx-1 text-xs bg-secondary px-1.5 rounded-sm">/api/v1/public/estimation</code>,
        <code className="mx-1 text-xs bg-secondary px-1.5 rounded-sm">/prices</code> et
        <code className="mx-1 text-xs bg-secondary px-1.5 rounded-sm">/calculators</code>.
      </SectionTitle>

      <div className="surface p-6 grid gap-4" data-testid="api-key-create">
        <div className="flex items-center gap-2"><Key className="h-4 w-4 text-primary" /><p className="overline">Nova chave API</p></div>
        <div className="grid sm:grid-cols-3 gap-3">
          <div className="grid gap-2">
            <Label>Planta</Label>
            <Select value={form.plan_id} onValueChange={(v) => setForm({ ...form, plan_id: v })}>
              <SelectTrigger className="rounded-sm h-10" data-testid="api-key-plan"><SelectValue /></SelectTrigger>
              <SelectContent>
                {plans.map((p) => (
                  <SelectItem key={p.plan_id} value={p.plan_id}>
                    {p.name} — {(p.amount_cents / 100).toFixed(0)} €/mês · {p.quotas?.api_calls_monthly?.toLocaleString("pt-PT")} appels
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2 sm:col-span-2">
            <Label>Nome (ex: Produção)</Label>
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} data-testid="api-key-name" className="rounded-sm h-10" />
          </div>
        </div>
        <Button onClick={create} disabled={busy} data-testid="api-key-create-btn" className="rounded-sm gap-2 justify-self-start hover:bg-orange-600 hover:text-white">
          <Plus className="h-4 w-4" /> Gerar a chave
        </Button>
        <p className="text-xs text-muted-foreground">
          A chave completa será exibida apenas uma vez — armazene-a imediatamente no seu gestor de segredos.
        </p>
      </div>

      <Dialog open={!!freshKey} onOpenChange={(o) => !o && setFreshKey(null)}>
        <DialogContent className="rounded-sm sm:max-w-lg" data-testid="fresh-key-dialog">
          <DialogHeader>
            <DialogTitle className="font-display text-2xl">A sua nova chave API</DialogTitle>
            <DialogDescription>Copie-a agora — ela não será mais exibida em texto simples.</DialogDescription>
          </DialogHeader>
          <div className="p-3 border border-primary/40 bg-primary/5 rounded-sm break-all font-mono text-sm" data-testid="fresh-key-value">
            {freshKey?.key}
          </div>
          <Button onClick={() => copy(freshKey?.key)} className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Copy className="h-4 w-4" /> Copiar
          </Button>
        </DialogContent>
      </Dialog>

      <div className="surface p-6">
        <p className="overline mb-4">Chaves ativas ({keys.length})</p>
        <Table>
          <TableHeader><TableRow>
            <TableHead>Nome</TableHead><TableHead>Prefixo</TableHead>
            <TableHead>Planta</TableHead><TableHead>Quota / mês</TableHead>
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
                    {k.active ? "Ativo" : "Revogado"}
                  </Badge>
                </TableCell>
                <TableCell className="text-right space-x-2">
                  <Button size="sm" variant="outline" onClick={() => rotate(k.prefix)} className="rounded-sm gap-1" data-testid={`api-key-rotate-${k.prefix}`}>
                    <RefreshCw className="h-3 w-3" /> Rodar
                  </Button>
                  {k.active && (
                    <Button size="sm" variant="outline" onClick={() => revoke(k.prefix)} className="rounded-sm gap-1" data-testid={`api-key-revoke-${k.prefix}`}>
                      <Trash2 className="h-3 w-3" /> Revogar
                    </Button>
                  )}
                </TableCell>
              </TableRow>
            ))}
            {keys.length === 0 && <TableRow><TableCell colSpan={6} className="text-center text-sm text-muted-foreground py-8">Nenhuma chave por enquanto</TableCell></TableRow>}
          </TableBody>
        </Table>
      </div>

      <div className="surface p-6 grid gap-3">
        <div className="flex items-center gap-2"><Rocket className="h-4 w-4 text-primary" /><p className="overline">Exemplo de chamada</p></div>
        <pre className="text-xs bg-secondary/40 p-4 rounded-sm overflow-x-auto"><code>{`curl -X POST https://pilot-build-demo.preview.emergentagent.com/api/v1/public/estimation \\
  -H "X-API-Key: ckp_live_..." \\
  -H "Content-Type: application/json" \\
  -d '{"project_type":"renovation_partielle","surface":40,"finish_level":"standard"}'`}</code></pre>
      </div>
    </div>
  );
}
