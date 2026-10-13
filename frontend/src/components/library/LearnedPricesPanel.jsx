import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Sparkles, Check, Loader2, ChevronDown, ChevronUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";

const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

export default function LearnedPricesPanel({ onValidated }) {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [open, setOpen] = useState(true);
  const [busy, setBusy] = useState("");
  const [prices, setPrices] = useState({});

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/library/learned?limit=200");
      setItems(data.items || []);
    } catch { /* silencieux */ }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);

  const validate = async (it) => {
    setBusy(it.item_id);
    try {
      const override = prices[it.item_id];
      const body = override != null && override !== "" ? { unit_price_ht: parseFloat(override) } : {};
      await api.post(`/library/${it.item_id}/validate`, body);
      setItems((xs) => xs.filter((x) => x.item_id !== it.item_id));
      toast.success(`« ${it.designation}» validado — preço firme`);
      onValidated?.();
    } catch { toast.error("Validação impossível"); }
    finally { setBusy(""); }
  };

  if (loading) return null;
  if (!items.length) return null;

  return (
    <div className="surface border-amber-400/50" data-testid="learned-prices-panel">
      <button onClick={() => setOpen((o) => !o)} data-testid="learned-toggle"
              className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left">
        <span className="flex items-center gap-2 font-display font-bold text-sm">
          <Sparkles className="h-4 w-4 text-amber-500" />
          {items.length} preço médio{items.length > 1 ? "s" : ""} de mercado aprendidos — a validar
        </span>
        {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
      </button>
      {open && (
        <div className="border-t border-border divide-y divide-border" data-testid="learned-list">
          <p className="px-4 py-2 text-xs text-muted-foreground">
            Estes preços foram estimados automaticamente (web/mercado) nos seus orçamentos. Valide-os para que se tornem os seus preços firmes e tornem as próximas orçamentações mais fiáveis.
          </p>
          {items.map((it) => (
            <div key={it.item_id} className="flex flex-wrap items-center gap-2 px-4 py-3"
                 data-testid={`learned-item-${it.item_id}`}>
              <div className="min-w-0 flex-1">
                <p className="font-medium text-sm truncate">{it.designation}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {it.category || "—"} · {it.unit} · estimado
                </p>
              </div>
              <div className="flex items-center gap-1">
                <Input type="number" step="0.01" min="0"
                       defaultValue={it.unit_price_ht}
                       onChange={(e) => setPrices((p) => ({ ...p, [it.item_id]: e.target.value }))}
                       className="w-28 rounded-sm num h-9" data-testid={`learned-price-${it.item_id}`} />
                <span className="text-xs text-muted-foreground">HT</span>
              </div>
              <Button size="sm" onClick={() => validate(it)} disabled={busy === it.item_id}
                      className="rounded-sm gap-1.5" data-testid={`learned-validate-${it.item_id}`}>
                {busy === it.item_id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Valider
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
