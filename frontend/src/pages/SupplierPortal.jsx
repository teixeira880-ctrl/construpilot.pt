import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Store, MousePointerClick, ExternalLink, TrendingUp, Package, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, eur2 } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SectionTitle, Stat } from "@/components/Bits";

const SUPPLIERS = [
  { key: "leroymerlin", label: "Leroy Merlin" },
  { key: "bricodepot", label: "Brico Depôt" },
  { key: "aki", label: "AKI" },
  { key: "bricomarche", label: "Bricomarché" },
  { key: "maxmat", label: "Maxmat" },
  { key: "obramat", label: "Obramat" },
  { key: "bigmat", label: "BigMat" },
  { key: "amazon", label: "Amazon" },
];

export default function SupplierPortal() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  const [claim, setClaim] = useState({ supplier_key: "leroymerlin", contact_name: "", contact_email: "" });
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { const { data } = await api.get(`/suppliers/dashboard?days=${days}`); setData(data); }
    catch { setData({ verified: false }); }
  };
  useEffect(() => { if (user) load(); }, [user, days]); // eslint-disable-line

  const submitClaim = async (e) => {
    e.preventDefault();
    if (!claim.contact_name || !claim.contact_email) return toast.error("Nome + email obrigatórios");
    setBusy(true);
    try {
      await api.post("/suppliers/claim", claim);
      toast.success("Reclamação enviada — validação em 48 h");
      load();
    } catch { toast.error("Impossível"); }
    finally { setBusy(false); }
  };

  if (!user) return <div className="surface p-10 text-center">Ligue-se.</div>;
  if (!data) return <div className="surface p-10 text-center">A carregar…</div>;

  if (!data.verified) {
    return (
      <div className="grid gap-8">
        <SectionTitle over="Espaço Fornecedores" title="Reclame a sua empresa no ConstruPilot">
          Acompanhe os seus cliques, redirecionamentos, GMV e comissões provenientes do comparador. Desbloqueie também os anúncios patrocinados (brevemente).
        </SectionTitle>
        <form onSubmit={submitClaim} className="surface p-6 grid gap-4 max-w-lg" data-testid="supplier-claim-form">
          <div className="grid gap-2">
            <Label>Insígnia a reclamar *</Label>
            <Select value={claim.supplier_key} onValueChange={(v) => setClaim({ ...claim, supplier_key: v })}>
              <SelectTrigger className="rounded-sm h-11" data-testid="supplier-claim-key"><SelectValue /></SelectTrigger>
              <SelectContent>
                {SUPPLIERS.map((s) => <SelectItem key={s.key} value={s.key}>{s.label}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="grid gap-2">
            <Label>Contacto (nome apelido) *</Label>
            <Input required value={claim.contact_name} onChange={(e) => setClaim({ ...claim, contact_name: e.target.value })} data-testid="supplier-claim-name" className="rounded-sm h-11" />
          </div>
          <div className="grid gap-2">
            <Label>Email profissional *</Label>
            <Input type="email" required value={claim.contact_email} onChange={(e) => setClaim({ ...claim, contact_email: e.target.value })} data-testid="supplier-claim-email" className="rounded-sm h-11" />
          </div>
          <Button type="submit" disabled={busy} data-testid="supplier-claim-submit" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white justify-self-start">
            <Send className="h-4 w-4" /> Enviar a reclamação
          </Button>
        </form>
      </div>
    );
  }

  return (
    <div className="grid gap-8">
      <div className="flex flex-wrap justify-between items-center gap-4">
        <div className="flex items-center gap-3">
          <Store className="h-6 w-6 text-primary" />
          <div>
            <p className="overline">Painel de controlo fornecedor</p>
            <h1 className="font-display text-3xl font-extrabold tracking-tighter">{SUPPLIERS.find((s) => s.key === data.supplier_key)?.label || data.supplier_key}</h1>
          </div>
          <Badge variant="outline" className="rounded-sm border-emerald-500/40 text-emerald-500" data-testid="supplier-verified">Verificado</Badge>
        </div>
        <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
          <SelectTrigger className="rounded-sm w-40" data-testid="supplier-days"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="7">Últimos 7 dias</SelectItem>
            <SelectItem value="30">Últimos 30 dias</SelectItem>
            <SelectItem value="90">Últimos 90 dias</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid md:grid-cols-4 gap-4" data-testid="supplier-kpis">
        <Stat icon={MousePointerClick} label="Cliques" value={data.clicks} />
        <Stat icon={ExternalLink} label="Redirecionamentos" value={data.redirects} />
        <Stat icon={TrendingUp} label="Conversões" value={data.conversions} />
        <Stat icon={Package} label="Comissão (€)" value={eur2(data.commission_eur || 0)} accent />
      </div>

      <div className="grid md:grid-cols-2 gap-6">
        <div className="surface p-6" data-testid="supplier-top-products">
          <p className="overline mb-4">Top produtos clicados</p>
          {data.top_products?.length ? (
            <Table>
              <TableHeader><TableRow>
                <TableHead>Produto (URL)</TableHead><TableHead className="text-right">Cliques</TableHead>
              </TableRow></TableHeader>
              <TableBody>
                {data.top_products.map((p) => (
                  <TableRow key={p.url}>
                    <TableCell className="font-mono text-xs truncate max-w-[400px]">{p.url}</TableCell>
                    <TableCell className="text-right num">{p.clicks}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">Nenhum clique no período selecionado.</p>
          )}
        </div>
        <div className="surface p-6" data-testid="supplier-top-queries">
          <p className="overline mb-4">Top pesquisas</p>
          {data.top_queries?.length ? (
            <ul className="grid gap-2">
              {data.top_queries.map((q) => (
                <li key={q.query} className="flex items-center justify-between border-b border-border pb-2 last:border-0">
                  <span className="text-sm">{q.query}</span>
                  <Badge variant="outline" className="rounded-sm num">{q.count}</Badge>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-muted-foreground">Nenhuma pesquisa indexada.</p>
          )}
        </div>
      </div>
    </div>
  );
}
