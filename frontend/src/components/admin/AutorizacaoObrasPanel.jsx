import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

const API = process.env.REACT_APP_BACKEND_URL;

export default function AutorizacaoObrasPanel() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    try {
      const r = await fetch(`${API}/api/admin/autorizacao-obras/settings`, { credentials: "include" });
      const d = await r.json();
      if (d.ok) setCfg(d.settings);
    } catch { /* ignore */ }
  };
  useEffect(() => { load(); }, []);

  const save = async () => {
    setLoading(true);
    try {
      const r = await fetch(`${API}/api/admin/autorizacao-obras/settings`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, credentials: "include",
        body: JSON.stringify(cfg),
      });
      const d = await r.json();
      if (d.ok) { setCfg(d.settings); toast.success("Preferências guardadas."); }
      else toast.error("Falha ao guardar.");
    } finally { setLoading(false); }
  };

  if (!cfg) return <Card className="p-4">A carregar…</Card>;

  const set = (k, v) => setCfg({ ...cfg, [k]: v });

  return (
    <Card className="p-5" data-testid="admin-autorizacao-panel">
      <h3 className="text-lg font-semibold mb-1">Autorização de obras — venda</h3>
      <p className="text-sm text-muted-foreground mb-4">
        O diagnóstico guiado é sempre gratuito. Esta secção controla a venda do processo completo
        (requerimento + memória + ficha + estimativa). A venda está desativada por defeito.
      </p>

      <div className="space-y-4">
        <label className="flex items-center justify-between gap-4 p-3 rounded border">
          <span><strong>Venda ativa</strong><br /><span className="text-xs text-muted-foreground">Quando desativada, o botão de pagamento devolve 403.</span></span>
          <Switch checked={!!cfg.sale_enabled} onCheckedChange={(v) => set("sale_enabled", v)} data-testid="admin-autorizacao-sale-enabled" />
        </label>

        <div className="grid gap-3 sm:grid-cols-2">
          <div>
            <Label htmlFor="pr">Preço (€)</Label>
            <Input id="pr" type="number" min="0" step="1" value={cfg.price_eur || 0}
                   onChange={(e) => set("price_eur", parseFloat(e.target.value) || 0)}
                   data-testid="admin-autorizacao-price" />
          </div>
          <div>
            <Label htmlFor="cur">Moeda</Label>
            <Input id="cur" value={cfg.currency || "eur"} onChange={(e) => set("currency", e.target.value)}
                   data-testid="admin-autorizacao-currency" />
          </div>
        </div>

        <label className="flex items-center justify-between gap-4 p-3 rounded border">
          <span>Incluído no plano Pro</span>
          <Switch checked={!!cfg.included_in_pro} onCheckedChange={(v) => set("included_in_pro", v)} data-testid="admin-autorizacao-pro" />
        </label>
        <label className="flex items-center justify-between gap-4 p-3 rounded border">
          <span>Incluído no plano Business</span>
          <Switch checked={!!cfg.included_in_business} onCheckedChange={(v) => set("included_in_business", v)} data-testid="admin-autorizacao-business" />
        </label>

        <div>
          <Label htmlFor="pname">Nome do produto no Stripe</Label>
          <Input id="pname" value={cfg.stripe_product_name || ""}
                 onChange={(e) => set("stripe_product_name", e.target.value)}
                 data-testid="admin-autorizacao-pname" />
        </div>

        <Button onClick={save} disabled={loading} data-testid="admin-autorizacao-save">
          {loading ? "A guardar…" : "Guardar"}
        </Button>
      </div>
    </Card>
  );
}
