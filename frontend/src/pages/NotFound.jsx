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
    { to: "/estimation", label: "Estimer un projet", icon: Search },
    { to: "/prix", label: "Prix des matériaux", icon: FileText },
    { to: "/blog", label: "Le blog", icon: FileText },
  ];
  return (
    <>
      <SEO
        title="Page introuvable (404)"
        description="Cette page n'existe pas ou a été déplacée."
        noindex
      />
      <section className="min-h-[70vh] flex items-center" data-testid="notfound-page">
        <div className="mx-auto max-w-xl px-6 text-center">
          <p className="font-display text-7xl font-extrabold tracking-tighter text-primary">404</p>
          <h1 className="mt-4 font-display text-2xl lg:text-3xl font-bold">
            Cette page n'existe pas
          </h1>
          <p className="mt-3 text-sm text-muted-foreground">
            Le lien est peut-être erroné ou la page a été déplacée. Reprenons votre projet du bon pied.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/">
              <Button className="rounded-lg gap-2" data-testid="notfound-home-btn">
                <Home className="h-4 w-4" /> Retour à l'accueil
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
