import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { Lock, Search, ArrowRight, Star } from "lucide-react";
import { AppTile } from "@/components/workspace/AppTile";
import { useWorkspaceLinks, useFavorites } from "@/components/workspace/WorkspaceNavigation";
import {
  FAMILY_ORDER, FAMILY_ICONS, familyLabel, familySub, linkTarget, normText, writeFavorites,
} from "@/components/workspace/navigation";
import { SEO } from "@/components/SEO";
import "@/styles/workspace-tiles.css";

// "Todas as ferramentas": seis espaços de trabalho em cartões de vidro, com pesquisa e favoritos.
export default function Apps() {
  const all = useWorkspaceLinks();
  const favs = useFavorites();
  const { hash } = useLocation();
  const [q, setQ] = useState("");
  const needle = normText(q);
  const links = all.filter((l) => !l.home).filter((l) => !needle || normText(`${l.label} ${l.words || ""} ${familyLabel(l.family)}`).includes(needle));
  const families = FAMILY_ORDER.filter((f) => links.some((l) => l.family === f));
  const toggleFav = (to) => writeFavorites(favs.includes(to) ? favs.filter((x) => x !== to) : [...favs, to]);

  useEffect(() => {
    const id = hash?.slice(1);
    if (id) document.getElementById(`familia-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [hash]);

  return (
    <div className="space-y-6" data-testid="apps-page">
      <SEO title="Todas as ferramentas ConstruPilot" description="Todas as ferramentas ConstruPilot (estimativas, orçamentos, plantas, medições, cálculos, assistente IA) num só lugar." canonical="/apps" />
      <header className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <h1 className="font-display text-3xl sm:text-[40px] font-bold tracking-tight leading-tight">
            Todas as <span className="cp-grad-text">ferramentas</span>
          </h1>
          <p className="text-sm sm:text-base text-muted-foreground mt-1.5">Seis espaços de trabalho, pela ordem de um projeto: da planta à fatura.</p>
        </div>
        <label className="cp-glass flex items-center gap-2.5 h-12 px-4 rounded-2xl w-full sm:w-[380px]">
          <Search size={17} className="text-muted-foreground shrink-0" aria-hidden="true" />
          <input type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Pesquisar uma ferramenta…" aria-label="Pesquisar uma ferramenta"
            className="flex-1 min-w-0 bg-transparent outline-none text-[15px]" data-testid="apps-search" />
        </label>
      </header>

      {families.length === 0 && <p className="text-sm text-muted-foreground" data-testid="apps-empty">Nenhuma ferramenta corresponde. Experimente outra palavra.</p>}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3 items-start">
        {families.map((f) => (
          <section key={f} id={`familia-${f}`} className="cp-glass rounded-3xl p-5 flex flex-col gap-3 scroll-mt-24" data-testid={`apps-family-${f}`} aria-labelledby={`fam-${f}`}>
            <div className="flex items-center gap-3">
              <span className="rotate-[-6deg] inline-flex"><AppTile icon={FAMILY_ICONS[f]} family={f} size={48} /></span>
              <div className="min-w-0">
                <h2 id={`fam-${f}`} className="font-display text-lg font-semibold leading-tight">{familyLabel(f)}</h2>
                <p className="text-[13px] text-muted-foreground">{familySub(f)}</p>
              </div>
            </div>
            <div className="flex flex-col">
              {links.filter((l) => l.family === f).map((l) => {
                const fav = favs.includes(l.to);
                return (
                  <div key={l.to} className="group flex items-center gap-1 border-t border-border/60 first:border-t-0">
                    <Link to={linkTarget(l)} data-testid={`app-tile-${l.to}`}
                      className={`flex-1 min-w-0 flex items-center gap-3 rounded-xl px-2 py-2.5 min-h-[48px] transition-colors hover:bg-background/70 ${l.locked ? "opacity-70" : ""}`}>
                      <AppTile icon={l.icon} family={l.family} size={36} />
                      <span className="text-[14.5px] font-semibold leading-tight flex-1">{l.label}</span>
                      {l.locked
                        ? <Lock className="h-3.5 w-3.5 text-primary/70" data-testid="app-lock" aria-label="Incluído nos planos pagos" />
                        : <ArrowRight size={15} className="text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />}
                    </Link>
                    <button type="button" onClick={() => toggleFav(l.to)} aria-pressed={fav}
                      aria-label={fav ? `Retirar ${l.label} dos favoritos` : `Adicionar ${l.label} aos favoritos`}
                      title={fav ? "Retirar dos favoritos" : "Adicionar aos favoritos"} data-testid={`app-fav-${l.to}`}
                      className={`h-11 w-11 shrink-0 grid place-items-center rounded-xl transition-colors hover:bg-background/70 ${fav ? "text-amber-500" : "text-muted-foreground/50 hover:text-amber-500"}`}>
                      <Star className="h-4 w-4" fill={fav ? "currentColor" : "none"} />
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
