import { Link, useLocation } from "react-router-dom";
import { Lock, Sparkles, ArrowRight } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useBilling } from "@/context/BillingContext";

/**
 * Bandeau paywall doux : n'empêche pas l'usage, invite à débloquer.
 * Usage :
 *   const { has } = useBilling();
 *   {!has("savings_details") && <SoftPaywall feature="savings_details" context="savings" />}
 */
const MESSAGES = {
  savings: {
    title: "Desbloqueie a análise completa de poupanças",
    body: "Voyez chaque euro potentiellement économisé sur votre projet : matériaux, alternatives, DIY, fournisseurs.",
  },
  price_search: {
    title: "Compare todos os fornecedores e optimize o seu cesto",
    body: "10 fournisseurs, historique des prix, alertes automatiques, panier optimisé.",
  },
  diy: {
    title: "Descubra todas as tarefas que pode fazer sozinho",
    body: "Guides pas-à-pas, matériel requis, gains estimés, conseils sécurité — pour chaque lot.",
  },
  quote: {
    title: "Análise ilimitada dos seus orçamentos",
    body: "L'IA compare vos devis à la base de prix ConstruPilot et détecte les surcoûts.",
  },
  pdf: {
    title: "Export PDF professionnel",
    body: "Orçamento assinável, logótipo da empresa, discriminação por lote, planeamento incluído.",
  },
  default: {
    title: "Funcionalidade premium",
    body: "Débloquez toutes les fonctionnalités avec Premium ou un Project Pass unique.",
  },
};

export const SoftPaywall = ({ context = "default", compact = false }) => {
  const loc = useLocation();
  const { flags } = useBilling();
  const msg = MESSAGES[context] || MESSAGES.default;
  const testid = `soft-paywall-${context}`;

  if (compact) {
    return (
      <div className="surface p-4 flex items-center gap-3 border-primary/40 bg-primary/5" data-testid={testid}>
        <Lock className="h-4 w-4 text-primary shrink-0" />
        <p className="text-sm">{msg.title}</p>
        <Link to={`/tarifs?from=${encodeURIComponent(loc.pathname)}`} className="ml-auto">
          <Button size="sm" className="rounded-sm gap-1 hover:bg-orange-600 hover:text-white">
            Débloquer <ArrowRight className="h-3 w-3" />
          </Button>
        </Link>
      </div>
    );
  }

  return (
    <div className="surface p-6 border-primary/40 bg-primary/5 grid gap-4" data-testid={testid}>
      <div className="flex items-center gap-3">
        <span className="h-9 w-9 grid place-items-center rounded-sm bg-primary/15 text-primary">
          <Sparkles className="h-4 w-4" />
        </span>
        <div>
          <Badge variant="outline" className="rounded-sm text-[10px] uppercase tracking-wider border-primary/40 text-primary">
            Premium
          </Badge>
          <p className="mt-2 font-display font-bold">{msg.title}</p>
        </div>
      </div>
      <p className="text-sm text-muted-foreground">{msg.body}</p>
      <div className="flex flex-wrap gap-2">
        <Link to={`/tarifs?from=${encodeURIComponent(loc.pathname)}`}>
          <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white" data-testid={`${testid}-cta`}>
            <Sparkles className="h-4 w-4" />
            Essayer Premium {flags?.trial_enabled && flags?.trial_days ? `— ${flags.trial_days} jours offerts` : ""}
          </Button>
        </Link>
        <Link to="/tarifs">
          <Button variant="outline" className="rounded-sm">
            Ou Project Pass — 19,90 €
          </Button>
        </Link>
      </div>
    </div>
  );
};
