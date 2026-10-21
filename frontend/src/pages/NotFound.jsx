import { useEffect, useState } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { Home, Search, FileText, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SEO } from "@/components/SEO";

let redirectsPromise = null;
const loadRedirects = () => {
  if (!redirectsPromise) {
    redirectsPromise = fetch(`${process.env.REACT_APP_BACKEND_URL}/api/growth/redirects`).then((r) => (r.ok ? r.json() : {})).then((d) => d.redirects || {}).catch(() => ({}));
  }
  return redirectsPromise;
};

export default function NotFound() {
  const { pathname } = useLocation();
  const [target, setTarget] = useState(undefined);
  useEffect(() => {
    let on = true;
    const key = pathname !== "/" && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
    loadRedirects().then((r) => on && setTarget(r[key] || null));
    return () => { on = false; };
  }, [pathname]);
  if (target) return <Navigate to={target} replace />;
  const links = [
    { to: "/estimation", label: "Estimar um projeto", icon: Search },
    { to: "/prix", label: "Preço dos materiais", icon: FileText },
    { to: "/blog", label: "O blogue", icon: FileText },
  ];
  return (
    <>
      <SEO
        title="Página não encontrada (404)"
        description="Esta página não existe ou foi movida."
        noindex
      />
      <section className="min-h-[70vh] flex items-center" data-testid="notfound-page">
        <div className="mx-auto max-w-xl px-6 text-center">
          <p className="font-display text-7xl font-extrabold tracking-tighter text-primary">404</p>
          <h1 className="mt-4 font-display text-2xl lg:text-3xl font-bold">
            Esta página não existe
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            O link pode estar errado ou a página foi movida. Retomemos o seu projeto com o pé direito.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/">
              <Button className="rounded-lg gap-2" data-testid="notfound-home-btn">
                <Home className="h-4 w-4" /> Voltar ao início
              </Button>
            </Link>
          </div>
          <div className="mt-10 grid sm:grid-cols-3 gap-3">
            {links.map((l) => (
              <Link key={l.to} to={l.to}
                    className="surface p-4 text-left hover:border-primary transition-colors group"
                    data-testid={`notfound-link-${l.to.slice(1)}`}>
                <l.icon className="h-4 w-4 text-primary" />
                <p className="mt-2 text-sm font-semibold group-hover:text-primary transition-colors inline-flex items-center gap-1">
                  {l.label} <ArrowRight className="h-3 w-3" />
                </p>
              </Link>
            ))}
          </div>
        </div>
      </section>
    </>
  );
}
