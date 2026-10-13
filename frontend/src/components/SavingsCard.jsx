import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { PiggyBank, Sparkles, ChevronDown, Lock, TrendingDown } from "lucide-react";
import { api, eur } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useBilling } from "@/context/BillingContext";

const ICON_BY_KEY = {
  materials_optimization: TrendingDown,
  alternative_materials: Sparkles,
  diy_savings: PiggyBank,
  supplier_optimization: TrendingDown,
};

export const SavingsCard = ({ estimation, projectId }) => {
  const { tier } = useBilling();
  const [data, setData] = useState(null);
  const [expanded, setExpanded] = useState(false);
  const isPremium = tier !== "free";

  useEffect(() => {
    let alive = true;
    const promise = projectId
      ? api.get(`/projects/${projectId}/savings`)
      : api.post("/savings/analyse", { estimation });
    promise.then(({ data }) => { if (alive) setData(data); })
           .catch(() => alive && setData({ items: [], total: 0 }));
    return () => { alive = false; };
  }, [projectId, estimation]);

  if (!data) {
    return <div className="surface p-6 h-32 animate-pulse" />;
  }
  if (!data.items || data.items.length === 0 || !data.total) return null;

  return (
    <div className="surface p-6 grid gap-4 border-primary/30 bg-gradient-to-br from-primary/5 to-transparent" data-testid="savings-card">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <span className="h-11 w-11 grid place-items-center rounded-sm bg-primary/15 text-primary">
            <PiggyBank className="h-5 w-5" />
          </span>
          <div>
            <p className="overline">Economias potenciais</p>
            <p className="font-display text-3xl font-extrabold tracking-tighter num mt-1" data-testid="savings-total">
              {eur(data.total)}
            </p>
            <p className="text-xs text-muted-foreground mt-1">
              soit ~{data.pct_of_project} % do orçamento total do projeto
            </p>
          </div>
        </div>
        {data.roi_multiplier > 5 && (
          <Badge className="rounded-sm bg-primary text-primary-foreground uppercase tracking-wider text-[10px]">
            ROI {data.roi_multiplier}× o Project Pass
          </Badge>
        )}
      </div>

      <p className="text-sm text-muted-foreground">{data.message}</p>

      <div className="grid sm:grid-cols-2 gap-3">
        {data.items.map((item, i) => {
          const Icon = ICON_BY_KEY[item.key] || Sparkles;
          const showDetails = isPremium || i === 0;
          return (
            <div key={item.key}
                 data-testid={`savings-item-${item.key}`}
                 className={`rounded-sm p-3 border ${showDetails ? "border-border bg-background/70" : "border-border/60 bg-background/40"}`}>
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-primary" />
                <p className="font-display font-semibold text-sm">{item.label}</p>
              </div>
              <p className="num font-display text-xl font-bold mt-2">
                {showDetails ? eur(item.amount) : "•• ••• €"}
              </p>
              {showDetails ? (
                <p className="text-xs text-muted-foreground mt-1">{item.basis}</p>
              ) : (
                <p className="text-xs text-muted-foreground mt-1 flex items-center gap-1">
                  <Lock className="h-3 w-3" /> Detalhe desbloqueado com Premium ou Project Pass
                </p>
              )}
              {expanded && showDetails && item.description && (
                <p className="text-xs text-muted-foreground mt-2 border-t border-border pt-2">
                  {item.description}
                </p>
              )}
            </div>
          );
        })}
      </div>

      {isPremium ? (
        <button onClick={() => setExpanded((v) => !v)}
                data-testid="savings-toggle-details"
                className="text-xs text-primary hover:underline inline-flex items-center gap-1 self-start">
          {expanded ? "Reduzir" : "Ver as explicações detalhadas"}
          <ChevronDown className={`h-3 w-3 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
      ) : (
        <div className="flex flex-wrap gap-3 pt-2 border-t border-border">
          <Link to="/tarifs">
            <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white" data-testid="savings-upgrade-cta">
              <Sparkles className="h-4 w-4" />
              Desbloquear todas as poupanças — Premium 19 €/mês
            </Button>
          </Link>
          <p className="text-xs text-muted-foreground self-center">
            Investir 19,90 € (Project Pass) pode render-lhe {eur(data.total)} de poupança.
          </p>
        </div>
      )}
    </div>
  );
};
