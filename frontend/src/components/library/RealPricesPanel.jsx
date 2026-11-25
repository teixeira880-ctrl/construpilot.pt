import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Brain, ChevronDown, ChevronUp } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";

const eur = (n) => n == null ? "—" : (Number(n) || 0).toLocaleString("pt-PT", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

// O que a ConstruPilot aprendeu automaticamente com ESTA empresa (obras, materiais, preços reais)
// + escolha de contribuir anonimamente para a biblioteca geral.
export default function RealPricesPanel() {
  const [mem, setMem] = useState(null);
  const [settings, setSettings] = useState(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    api.get("/learning/my-memory").then(({ data }) => setMem(data)).catch(() => {});
    api.get("/learning/settings").then(({ data }) => setSettings(data)).catch(() => {});
  }, []);

  const toggleShare = async (v) => {
    try {
      const { data } = await api.put("/learning/settings", { share_anonymous_prices: v });
      setSettings(data);
      toast.success(v ? "Contribuição anónima ativada" : "Contribuição anónima desativada");
    } catch { toast.error("Não foi possível guardar"); }
  };

  if (!mem && !settings) return null;
  const items = mem?.items || [];

  return (
    <div className="surface" data-testid="real-prices-panel">
      <button onClick={() => setOpen((o) => !o)} data-testid="real-prices-toggle"
              className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left">
        <span className="flex items-center gap-2 font-display font-bold text-sm">
          <Brain className="h-4 w-4 text-primary" />
          Aprendizagem automática — {items.length} obra{items.length === 1 ? "" : "s"} com preço real memorizado
          {mem?.purchases ? ` · ${mem.purchases} compra${mem.purchases > 1 ? "s" : ""} de materiais` : ""}
        </span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <div className="border-t border-border" data-testid="real-prices-body">
          <p className="px-4 py-2 text-xs text-muted-foreground">
            Cada orçamento, fatura e encomenda a fornecedor ensina a ConstruPilot: as suas obras, os materiais e os
            preços que realmente pratica (assinados e faturados contam mais). O assistente usa esta memória só para a
            sua empresa.
          </p>
          {settings && (
            <label className="flex items-start gap-3 px-4 py-2 text-xs" data-testid="real-prices-share">
              <Switch checked={!!settings.share_anonymous_prices} onCheckedChange={toggleShare} data-testid="real-prices-share-switch" />
              <span>
                Contribuir anonimamente para a biblioteca geral ConstruPilot. Só é partilhado um preço mediano por obra,
                sem nome, cliente nem documento, e só quando pelo menos {settings.k_anon} empresas praticam a mesma obra.
              </span>
            </label>
          )}
          {items.length > 0 && (
            <div className="divide-y divide-border" data-testid="real-prices-list">
              {items.slice(0, 50).map((it) => {
                const s = it.price_stats || {};
                return (
                  <div key={it.item_id || it.designation} className="grid grid-cols-12 gap-2 px-4 py-2 text-xs items-center">
                    <span className="col-span-12 md:col-span-6 font-medium truncate">{it.designation}</span>
                    <span className="col-span-4 md:col-span-2 text-muted-foreground">{s.n} uso{s.n > 1 ? "s" : ""}{s.n_real ? ` · ${s.n_real} real` : ""}</span>
                    <span className="col-span-4 md:col-span-2 text-right num font-bold">{eur(s.median_real ?? s.median)}/{it.unit}</span>
                    <span className="col-span-4 md:col-span-2 text-right num text-muted-foreground">{eur(s.min)} – {eur(s.max)}</span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
