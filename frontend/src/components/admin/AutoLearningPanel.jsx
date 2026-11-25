import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Brain, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const eur = (n) => n == null ? "—" : (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

// Admin : estado do ciclo de aprendizagem (feedback + uso) e biblioteca geral aprendida (anónima, k-anonimato).
export default function AutoLearningPanel() {
  const [dash, setDash] = useState(null);
  const [pool, setPool] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = () => {
    api.get("/learning/dashboard").then(({ data }) => setDash(data)).catch(() => {});
    api.get("/learning/global-pool?limit=300").then(({ data }) => setPool(data.items || [])).catch(() => {});
  };
  useEffect(load, []);

  const promote = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/learning/global-pool/promote", { gkeys: [] });
      toast.success(`Biblioteca geral: ${data.added} obra(s) adicionada(s), ${data.updated} atualizada(s)`);
      load();
    } catch { toast.error("Integração impossível"); }
    finally { setBusy(false); }
  };

  if (!dash) return null;
  const tiles = [
    ["Preços observados", dash.auto_price_observations],
    ["Preços reais (assinados / faturados / compras)", dash.auto_real_price_observations],
    ["Empresas a ensinar", dash.auto_companies_learning],
    ["Pedidos de clientes memorizados", dash.auto_client_requests],
    ["👍 / 👎 (a sua empresa)", `${dash.thumbs_up} / ${dash.thumbs_down}`],
    [`Biblioteca geral aprendida (≥ ${dash.k_anon} empresas)`, `${dash.global_pool_published} / ${dash.global_pool_candidates}`],
  ];

  return (
    <div className="surface rounded-md p-5 space-y-4 border border-primary/30" data-testid="auto-learning-panel">
      <div className="flex items-start gap-3">
        <Brain className="h-6 w-6 text-primary mt-0.5" />
        <div className="flex-1">
          <h3 className="font-display font-bold text-lg">Aprendizagem automática com o uso</h3>
          <p className="text-sm text-muted-foreground">
            Cada cliente tem a sua memória privada (obras, materiais, preços reais, pedidos, correções 👎), injetada só
            nos seus prompts. A biblioteca geral cresce de forma anónima: um preço só aparece quando {dash.k_anon} empresas
            distintas praticam a mesma obra.
          </p>
        </div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3" data-testid="auto-learning-tiles">
        {tiles.map(([label, value]) => (
          <div key={label} className="rounded-sm border p-3">
            <div className="text-xs text-muted-foreground">{label}</div>
            <div className="font-display font-bold text-lg num">{value ?? 0}</div>
          </div>
        ))}
      </div>
      <div className="flex items-center justify-between gap-3">
        <h4 className="font-semibold text-sm">Preços gerais aprendidos ({pool.length})</h4>
        <Button size="sm" variant="outline" className="rounded-sm gap-2" disabled={busy || !pool.length} onClick={promote} data-testid="auto-learning-promote">
          {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Upload className="h-4 w-4" />} Integrar na biblioteca geral PT
        </Button>
      </div>
      {pool.length > 0 && (
        <div className="max-h-72 overflow-auto divide-y divide-border border rounded-sm" data-testid="auto-learning-pool">
          {pool.map((r) => (
            <div key={r.gkey} className="grid grid-cols-12 gap-2 px-3 py-2 text-xs items-center">
              <span className="col-span-12 md:col-span-6 truncate">{r.designation}</span>
              <span className="col-span-4 md:col-span-2 text-muted-foreground">{r.n_orgs} empresas</span>
              <span className="col-span-4 md:col-span-2 text-right num font-bold">{eur(r.unit_price_ht)}/{r.unit}</span>
              <span className="col-span-4 md:col-span-2 text-right num text-muted-foreground">{eur(r.price_low)} – {eur(r.price_high)}{r.promoted_at ? " ✓" : ""}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
