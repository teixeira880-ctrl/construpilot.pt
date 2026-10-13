import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  ShieldCheck, Wrench, MapPin, Wallet, Plus, ArrowRight, Star, Send,
  Building2, TrendingUp,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, eur, eur2 } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SectionTitle, Stat } from "@/components/Bits";

const AMOUNTS = [
  { cents: 5000, label: "50 €" },
  { cents: 10000, label: "100 €" },
  { cents: 25000, label: "250 €", bonus: "+5 %" },
  { cents: 50000, label: "500 €", bonus: "+10 %" },
];

const KycForm = ({ onSaved }) => {
  const [form, setForm] = useState({
    siren: "", company_name: "", rc_pro_insurer: "", rc_pro_number: "",
    decennale_insurer: "", decennale_number: "",
    trades: "", zones: "", years_experience: "",
  });
  const [busy, setBusy] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/marketplace/kyc", {
        siren: form.siren,
        company_name: form.company_name,
        rc_pro_insurer: form.rc_pro_insurer || null,
        rc_pro_number: form.rc_pro_number || null,
        decennale_insurer: form.decennale_insurer || null,
        decennale_number: form.decennale_number || null,
        trades: form.trades.split(",").map((s) => s.trim()).filter(Boolean),
        zones: form.zones.split(",").map((s) => s.trim()).filter(Boolean),
        years_experience: form.years_experience ? Number(form.years_experience) : null,
      });
      toast.success("Processo enviado — verificação em 48 h");
      onSaved();
    } catch (err) { toast.error(err?.response?.data?.detail || "Impossível"); }
    finally { setBusy(false); }
  };
  return (
    <form onSubmit={submit} className="surface p-6 grid gap-4" data-testid="kyc-form">
      <p className="overline">Tornar-se ConstruPilot Verified</p>
      <div className="grid sm:grid-cols-2 gap-4">
        <div className="grid gap-2">
          <Label>NIPC ou estabelecimento *</Label>
          <Input required value={form.siren} onChange={(e) => setForm({ ...form, siren: e.target.value })}
                 data-testid="kyc-siren" className="rounded-sm h-11 num" />
        </div>
        <div className="grid gap-2">
          <Label>Denominação social *</Label>
          <Input required value={form.company_name} onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                 data-testid="kyc-company" className="rounded-sm h-11" />
        </div>
        <div className="grid gap-2">
          <Label>Seguradora RC Pro</Label>
          <Input value={form.rc_pro_insurer} onChange={(e) => setForm({ ...form, rc_pro_insurer: e.target.value })}
                 data-testid="kyc-rcpro-insurer" className="rounded-sm h-11" />
        </div>
        <div className="grid gap-2">
          <Label>N.º apólice RC Pro</Label>
          <Input value={form.rc_pro_number} onChange={(e) => setForm({ ...form, rc_pro_number: e.target.value })}
                 data-testid="kyc-rcpro-number" className="rounded-sm h-11" />
        </div>
        <div className="grid gap-2">
          <Label>Seguradora decenal</Label>
          <Input value={form.decennale_insurer} onChange={(e) => setForm({ ...form, decennale_insurer: e.target.value })}
                 data-testid="kyc-dec-insurer" className="rounded-sm h-11" />
        </div>
        <div className="grid gap-2">
          <Label>N.º apólice decenal</Label>
          <Input value={form.decennale_number} onChange={(e) => setForm({ ...form, decennale_number: e.target.value })}
                 data-testid="kyc-dec-number" className="rounded-sm h-11" />
        </div>
        <div className="grid gap-2">
          <Label>Profissões (separadas por vírgula)</Label>
          <Input value={form.trades} onChange={(e) => setForm({ ...form, trades: e.target.value })}
                 placeholder="canalizações, eletricidade, azulejo" data-testid="kyc-trades" className="rounded-sm h-11" />
        </div>
        <div className="grid gap-2">
          <Label>Zonas (departamentos)</Label>
          <Input value={form.zones} onChange={(e) => setForm({ ...form, zones: e.target.value })}
                 placeholder="75, 92, 93" data-testid="kyc-zones" className="rounded-sm h-11" />
        </div>
        <div className="grid gap-2">
          <Label>Anos de experiência</Label>
          <Input type="number" value={form.years_experience} onChange={(e) => setForm({ ...form, years_experience: e.target.value })}
                 data-testid="kyc-years" className="rounded-sm h-11 num" />
        </div>
      </div>
      <Button type="submit" disabled={busy} data-testid="kyc-submit" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white justify-self-start">
        <Send className="h-4 w-4" /> {busy ? "A enviar…" : "Submeter o meu processo"}
      </Button>
      <p className="text-xs text-muted-foreground">
        Após verificação (48 h), recebe o distintivo <b>ConstruPilot Verified</b> e aceda aos contactos qualificados.
      </p>
    </form>
  );
};

export default function ProPortal() {
  const { user } = useAuth();
  const [me, setMe] = useState(null);
  const [leads, setLeads] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try { const { data } = await api.get("/pro/me"); setMe(data); } catch { setMe({ registered: false }); }
    try { const { data } = await api.get("/marketplace/leads"); setLeads(data.leads || []); } catch { setLeads([]); }
  };
  useEffect(() => { if (user) load(); }, [user]);

  const recharge = async (cents) => {
    setBusy(true);
    try {
      const { data } = await api.post("/pro/credits/checkout",
        { amount_cents: cents, origin_url: window.location.origin });
      window.location.href = data.url;
    } catch (err) { toast.error(err?.response?.data?.detail || "Impossível"); setBusy(false); }
  };

  const buy = async (leadId) => {
    if (!confirm("Confirmar a compra deste contacto?")) return;
    try {
      await api.post("/marketplace/leads/buy", { lead_id: leadId });
      toast.success("Lead desbloqueado — as coordenadas estão agora visíveis");
      load();
    } catch (err) { toast.error(err?.response?.data?.detail || "Compra impossível"); }
  };

  if (!user) return <div className="surface p-10 text-center">Ligue-se.</div>;
  if (!me) return <div className="surface p-10 text-center">A carregar…</div>;

  if (!me.registered) {
    return (
      <div className="grid gap-8">
        <SectionTitle over="Espaço Pro" title="Torne-se profissional ConstruPilot">
          Receba todas as semanas potenciais clientes qualificados — pontuação 0/100 — nas suas zonas e especialidades. Pague à unidade através dos seus créditos ConstruPilot Pro.
        </SectionTitle>
        <KycForm onSaved={load} />
      </div>
    );
  }

  return (
    <div className="grid gap-8">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-3xl font-extrabold tracking-tighter">{me.company_name}</h1>
            {me.verified ? (
              <Badge className="rounded-sm bg-emerald-500/15 text-emerald-500 border-emerald-500/40 gap-1" data-testid="pro-verified-badge">
                <ShieldCheck className="h-3 w-3" /> {me.badge || "Verificado"}
              </Badge>
            ) : (
              <Badge variant="outline" className="rounded-sm border-amber-500/40 text-amber-500">
                {me.status === "pending" ? "Verificação em curso" : "Não verificado"}
              </Badge>
            )}
          </div>
          <p className="mt-2 text-sm text-muted-foreground flex flex-wrap items-center gap-3">
            <span className="inline-flex items-center gap-1"><Wrench className="h-3 w-3" /> {(me.trades || []).join(", ") || "—"}</span>
            <span className="inline-flex items-center gap-1"><MapPin className="h-3 w-3" /> {(me.zones || []).join(", ") || "—"}</span>
          </p>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-4" data-testid="pro-stats">
        <Stat icon={Wallet} label="Créditos" value={eur2(me.credits_eur)} accent />
        <Stat icon={Star} label="Leads comprados" value={me.leads_bought?.length || 0} />
        <Stat icon={TrendingUp} label="Gasto (€)" value={eur2((me.total_spent_cents || 0) / 100)} />
      </div>

      {me.verified && (
        <div className="surface p-6 grid gap-4" data-testid="pro-recharge">
          <p className="overline">Recarregar os meus créditos</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            {AMOUNTS.map((a) => (
              <button key={a.cents} onClick={() => recharge(a.cents)} disabled={busy}
                      data-testid={`recharge-${a.cents}`}
                      className="border border-border rounded-sm p-4 text-left hover:border-primary transition-colors group">
                <p className="num font-display text-2xl font-extrabold">{a.label}</p>
                {a.bonus && <Badge variant="outline" className="rounded-sm text-[10px] text-primary border-primary/40 mt-1">Bónus {a.bonus}</Badge>}
                <p className="text-xs text-muted-foreground mt-2 group-hover:text-primary">Recarregar →</p>
              </button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Bónus fidelidade automaticamente creditado após pagamento — até +10 %.
          </p>
        </div>
      )}

      <Tabs defaultValue="available">
        <TabsList className="rounded-sm">
          <TabsTrigger value="available" className="rounded-sm" data-testid="pro-tab-available">Leads disponíveis ({leads.length})</TabsTrigger>
          <TabsTrigger value="bought" className="rounded-sm" data-testid="pro-tab-bought">Os meus leads comprados ({me.leads_bought?.length || 0})</TabsTrigger>
        </TabsList>

        <TabsContent value="available" className="mt-6">
          {!me.verified ? (
            <div className="surface p-6 border-amber-500/40 bg-amber-500/5">
              <p className="text-sm">A sua conta está em verificação. Acederá aos contactos após validação.</p>
            </div>
          ) : leads.length === 0 ? (
            <div className="surface p-10 text-center text-muted-foreground text-sm">Nenhum lead disponível por enquanto.</div>
          ) : (
            <div className="grid md:grid-cols-2 gap-4" data-testid="pro-leads-grid">
              {leads.map((l) => (
                <div key={l.lead_id} className="surface p-5 grid gap-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-display font-bold">{l.trade || "Obras"}</p>
                      <p className="text-xs text-muted-foreground">{(l.address || "").slice(0, 60) || "Morada visível após a compra"}</p>
                    </div>
                    <Badge className={`rounded-sm ${l.score >= 75 ? "bg-emerald-500/15 text-emerald-500" : l.score >= 55 ? "bg-primary/15 text-primary" : "bg-secondary text-foreground"}`}>
                      Pontuação {l.score}/100
                    </Badge>
                  </div>
                  <p className="text-sm line-clamp-3 text-muted-foreground">{(l.description || "").slice(0, 200)}</p>
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    {l.budget && <div className="border border-border rounded-sm p-2"><p className="opacity-60">Orçamento</p><p className="num font-semibold">{eur(l.budget)}</p></div>}
                    {l.surface && <div className="border border-border rounded-sm p-2"><p className="opacity-60">Superfície</p><p className="num font-semibold">{l.surface} m²</p></div>}
                    {l.delay_days && <div className="border border-border rounded-sm p-2"><p className="opacity-60">Prazo</p><p className="num font-semibold">{l.delay_days} j</p></div>}
                  </div>
                  <div className="flex items-center justify-between pt-2 border-t border-border">
                    <p className="num font-display text-xl font-bold">{eur2(l.price_cents / 100)}</p>
                    <Button size="sm" onClick={() => buy(l.lead_id)} data-testid={`buy-lead-${l.lead_id}`} className="rounded-sm gap-1 hover:bg-orange-600 hover:text-white">
                      Desbloquear <ArrowRight className="h-3 w-3" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </TabsContent>

        <TabsContent value="bought" className="mt-6">
          {(!me.leads_bought || me.leads_bought.length === 0) ? (
            <div className="surface p-10 text-center text-muted-foreground text-sm">Nenhum lead comprado</div>
          ) : (
            <div className="surface p-6">
              <Table>
                <TableHeader><TableRow>
                  <TableHead>Especialidade</TableHead><TableHead>Cliente</TableHead><TableHead>Contacto</TableHead>
                  <TableHead>Pontuação</TableHead><TableHead>Preço pago</TableHead>
                </TableRow></TableHeader>
                <TableBody data-testid="pro-bought-table">
                  {me.leads_bought.map((l) => (
                    <TableRow key={l.lead_id}>
                      <TableCell>{l.trade || "—"}</TableCell>
                      <TableCell>{l.name}</TableCell>
                      <TableCell className="font-mono text-xs">{l.email} · {l.phone || "—"}</TableCell>
                      <TableCell><Badge variant="outline" className="rounded-sm num">{l.score}</Badge></TableCell>
                      <TableCell className="num">{eur2((l.sold_price_cents || 0) / 100)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
}
