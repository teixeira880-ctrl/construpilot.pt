import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import axios from "axios";
import { Hammer, Sparkles, ArrowRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { eur, num } from "@/lib/api";

/**
 * Page publique lecture seule affichant l'estimation d'un projet via son
 * token de partage. Aucun besoin d'authentification.
 */
export default function PublicEstimation() {
  const { token } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    const base = process.env.REACT_APP_BACKEND_URL;
    axios.get(`${base}/api/public/estimation/${token}`)
      .then(({ data }) => setData(data))
      .catch(() => setErr("Este link é inválido ou foi revogado."));
  }, [token]);

  if (err) {
    return (
      <div className="min-h-screen grid place-items-center p-6" data-testid="public-estimation-error">
        <div className="surface p-10 text-center max-w-md">
          <p className="overline text-destructive">Lien indisponible</p>
          <h1 className="font-display text-2xl font-bold mt-3">{err}</h1>
          <Link to="/" className="mt-6 inline-flex">
            <Button className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              Descobrir ConstruPilot <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
        </div>
      </div>
    );
  }

  if (!data) return (
    <div className="min-h-screen grid place-items-center">
      <div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" />
    </div>
  );

  const { project, estimation } = data;
  const lots = estimation.lots || [];

  return (
    <div className="min-h-screen bg-background">
      {/* Header sobre — pas de nav interne */}
      <header className="border-b border-border">
        <div className="mx-auto max-w-[1100px] px-5 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <span className="h-8 w-8 grid place-items-center bg-primary rounded-sm">
              <Hammer className="h-4 w-4 text-primary-foreground" />
            </span>
            <span className="font-display font-extrabold text-lg">
              Constru<span className="text-primary">Pilot</span>
            </span>
          </Link>
          <Link to="/" data-testid="public-cta-signup">
            <Button size="sm" variant="outline" className="rounded-sm gap-2">
              <Sparkles className="h-4 w-4" /> Fazer a minha própria estimativa
            </Button>
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-[1100px] px-5 py-10 grid gap-10">
        <div>
          <p className="overline">Estimativa partilhada</p>
          <h1 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight" data-testid="public-project-title">
            {project.name}
          </h1>
          <p className="num mt-2 text-sm text-muted-foreground">
            {project.city || project.region || "France"}
            {project.surface ? ` · ${num(project.surface, 1)} m²` : ""}
            {estimation.finish_level_name ? ` · finition ${estimation.finish_level_name}` : ""}
          </p>
        </div>

        <div className="grid sm:grid-cols-3 gap-4 stagger">
          <div className="surface p-6">
            <p className="overline">Budget bas</p>
            <p className="num mt-2 text-2xl font-bold">{eur(estimation.total_min)}</p>
          </div>
          <div className="surface p-6 border-primary" data-testid="public-total-avg">
            <p className="overline">Orçamento estimado</p>
            <p className="num mt-2 text-3xl font-extrabold text-primary">{eur(estimation.total_avg)}</p>
          </div>
          <div className="surface p-6">
            <p className="overline">Budget haut</p>
            <p className="num mt-2 text-2xl font-bold">{eur(estimation.total_max)}</p>
          </div>
        </div>

        {lots.length > 0 && (
          <div className="surface p-6">
            <p className="overline mb-6">Detalhe por especialidade</p>
            <div className="grid md:grid-cols-2 gap-3" data-testid="public-lots">
              {lots.map((l) => (
                <div key={l.key} className="flex items-center justify-between border-b border-border pb-3">
                  <div>
                    <p className="font-medium">{l.name}</p>
                    <p className="num text-xs text-muted-foreground">
                      {num(l.quantity, 2)} {l.unit}
                      {l.hours ? ` · ${num(l.hours, 1)} h` : ""}
                    </p>
                  </div>
                  <Badge variant="outline" className="rounded-sm num">{eur(l.total)}</Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="surface p-8 text-center">
          <p className="overline">Quer o mesmo?</p>
          <h2 className="font-display text-2xl font-bold mt-3">
            Crie a sua estimativa em 3 minutos com ConstruPilot
          </h2>
          <p className="mt-2 text-sm text-muted-foreground max-w-lg mx-auto">
            Preços reais, calculadores materiais, PDF de orçamento, obra foto — gratuito para começar.
          </p>
          <Link to="/" className="mt-6 inline-flex" data-testid="public-cta-bottom">
            <Button size="lg" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Sparkles className="h-4 w-4" /> Estimar o meu projeto
            </Button>
          </Link>
        </div>

        <p className="text-center text-xs text-muted-foreground">
          Estimativa gerada com ConstruPilot — os preços são indicativos e dependem das condições locais.
        </p>
      </main>
    </div>
  );
}
