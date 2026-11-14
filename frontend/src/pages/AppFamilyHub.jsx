import { Link, useLocation } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { familyByHub, familyLabel, familyDesc } from "@/components/workspace/families";
import { WORKSPACE_LINKS, benefitFor } from "@/components/workspace/navigation";
import { useFamilyMembers, useToolLabel } from "@/components/workspace/FamilyTabs";
import { UpgradeLock } from "@/components/UpgradeLock";

const COPY = {
  pt: { open: "Abrir", empty: "Nenhuma ferramenta desta app está incluída no seu plano.", plans: "Ver as ofertas", login: "Entre na sua conta para usar estas ferramentas." },
  en: { open: "Open", empty: "No tool of this app is included in your plan.", plans: "See plans", login: "Sign in to use these tools." },
  fr: { open: "Ouvrir", empty: "Aucun outil de cette app n'est inclus dans votre offre.", plans: "Voir les offres", login: "Connectez-vous pour utiliser ces outils." },
};

// Página de entrada de uma app fusionada (ex.: Estudos de Engenharia).
export default function AppFamilyHub() {
  const { pathname } = useLocation();
  const { user } = useAuth();
  const { lang } = useI18n();
  const family = familyByHub(pathname);
  const members = useFamilyMembers(family);
  const label = useToolLabel();
  const c = COPY[lang] || COPY.pt;
  if (!family) return null;
  // Sem sessão: mostrar as ferramentas (cada rota aplica o seu próprio acesso).
  const tools = user ? members : family.members.map(to => WORKSPACE_LINKS.find(l => l.to === to)).filter(Boolean);
  return (
    <div className="mx-auto max-w-6xl px-4 py-6" data-testid={`family-hub-${family.id}`}>
      <header className="mb-6 flex items-start gap-4">
        <div className="h-12 w-12 rounded-xl bg-primary/10 flex items-center justify-center shrink-0">
          <family.icon className="h-6 w-6 text-primary" aria-hidden="true" />
        </div>
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{familyLabel(family, lang)}</h1>
          <p className="text-sm text-muted-foreground mt-1 max-w-3xl">{familyDesc(family, lang)}</p>
          {!user && <p className="text-xs text-muted-foreground mt-2">{c.login}</p>}
        </div>
      </header>
      {!tools.length && (
        <div className="surface p-6 text-sm text-muted-foreground" data-testid="family-hub-empty">
          {c.empty} <Link to="/planos" className="text-primary font-medium">{c.plans}</Link>
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {tools.map(item => (
          <Link key={item.to} to={item.locked ? "/planos" : item.to} data-locked={item.locked || undefined}
            data-testid={`family-hub-tool-${item.to.slice(1).replace(/\//g, "-")}`}
            className="group flex items-start gap-3 rounded-xl border border-border bg-card p-4 shadow-sm hover:shadow-md hover:border-primary/40 transition-all">
            <div className="h-11 w-11 rounded-lg bg-primary/10 flex items-center justify-center shrink-0">
              <item.icon className="h-5 w-5 text-primary" aria-hidden="true" />
            </div>
            <div className="min-w-0 flex-1">
              <h2 className="font-semibold text-foreground group-hover:text-primary transition-colors flex items-center gap-2">
                {label(item)}
                {item.locked && <UpgradeLock title={label(item)} requiredLevel={item.requiredLevel} benefit={benefitFor(item.to, item.requiredLevel)} iconSize={12} />}
              </h2>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{benefitFor(item.to, item.requiredLevel || "pro")}</p>
            </div>
            {!item.locked && <ArrowRight className="h-4 w-4 text-muted-foreground group-hover:text-primary mt-1" aria-label={c.open} />}
          </Link>
        ))}
      </div>
    </div>
  );
}
