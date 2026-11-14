import { Link, useLocation } from "react-router-dom";
import { ArrowUpRight, Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { suiteByHub, suiteLabel, suiteDesc } from "@/components/workspace/suites";
import { WORKSPACE_LINKS, benefitFor } from "@/components/workspace/navigation";
import { useSuiteMembers, useToolLabel } from "@/components/workspace/SuiteTabs";
import { AppTile } from "@/components/workspace/AppTile";

const COPY = {
  fr: { empty: "Aucun outil de cette app n'est inclus dans votre offre.", plans: "Voir les offres", login: "Connectez-vous pour utiliser ces outils.", locked: "Offre supérieure requise" },
  pt: { empty: "Nenhuma ferramenta desta app está incluída no seu plano.", plans: "Ver as ofertas", login: "Entre na sua conta para usar estas ferramentas.", locked: "Oferta superior necessária" },
  en: { empty: "No tool of this app is included in your plan.", plans: "See plans", login: "Sign in to use these tools.", locked: "Higher plan required" },
};

// Página de entrada de uma app fusionada (ex.: Estudos de Engenharia).
export default function AppSuiteHub() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const { lang } = useI18n();
  const suite = suiteByHub(pathname);
  const members = useSuiteMembers(suite);
  const label = useToolLabel();
  const c = COPY[lang] || COPY.pt;
  if (!suite) return null;
  // Sem sessão: mostrar as ferramentas (cada rota aplica o seu próprio acesso).
  const tools = user ? members : suite.members.map(to => WORKSPACE_LINKS.find(l => l.to === to && !l.hub)).filter(Boolean);
  return (
    <div className="mx-auto max-w-5xl px-4 sm:px-6 py-6" data-testid={`suite-hub-${suite.id}`}>
      <header className="mb-6 flex items-start gap-4">
        <AppTile icon={suite.icon} family={suite.family} size={48} label={suiteLabel(suite, lang)} />
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">{suiteLabel(suite, lang)}</h1>
          <p className="mt-1 text-sm sm:text-base text-muted-foreground max-w-2xl">{suiteDesc(suite, lang)}</p>
          {!user && <p className="text-xs text-muted-foreground mt-2">{c.login}</p>}
        </div>
      </header>
      {!tools.length && (
        <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground" data-testid="suite-hub-empty">
          {c.empty} <Link to="/planos" className="text-primary font-medium">{c.plans}</Link>
        </div>
      )}
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {tools.map(tool => (
          <Link key={tool.to} to={tool.locked ? "/planos" : tool.to} data-locked={tool.locked || undefined}
            data-testid={`suite-card-${tool.to.slice(1).replace(/\//g, "-")}`}
            className="group text-left rounded-lg border border-border bg-card p-4 min-h-[112px] flex flex-col gap-2 hover:border-primary/60 hover:shadow-sm transition-all">
            <div className="flex items-center gap-2">
              <AppTile icon={tool.icon} family={tool.family} size={36} label={label(tool)} />
              <span className="font-semibold text-sm leading-tight flex-1">{label(tool)}</span>
              {tool.locked
                ? <Lock className="h-3.5 w-3.5 text-amber-500 shrink-0" aria-label={c.locked} />
                : <ArrowUpRight className="h-4 w-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0" aria-hidden="true" />}
            </div>
            <p className="text-xs text-muted-foreground leading-snug">{benefitFor(tool.to, tool.requiredLevel || "pro")}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
