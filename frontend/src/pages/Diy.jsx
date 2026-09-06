import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Wrench, ShieldAlert, Clock, Package, Search, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, eur, eur2, num } from "@/lib/api";
import { DifficultyBadge, SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";
import { LeadDialog } from "@/components/LeadDialog";

export default function Diy() {
  const [tasks, setTasks] = useState([]);
  const [guide, setGuide] = useState(null);
  const [area, setArea] = useState(35);
  const [busy, setBusy] = useState(false);
  const [optim, setOptim] = useState(null);
  const [currentKey, setCurrentKey] = useState(null);

  useEffect(() => { api.get("/diy/tasks").then(({ data }) => setTasks(data)); }, []);

  const open = async (key, a = area) => {
    setBusy(true);
    setCurrentKey(key);
    try {
      const { data } = await api.post(`/diy/guide/${key}`, { params: { area: Number(a) } });
      setGuide(data);
      setOptim(null);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch { toast.error("Guia indisponível"); }
    finally { setBusy(false); }
  };

  const findPrices = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/prices/optimize", {
        items: guide.materials.map((m) => ({ query: m.search, quantity: Math.ceil(m.quantity), name: m.name })),
      });
      setOptim(data);
    } catch { toast.error("Pesquisa impossível"); }
    finally { setBusy(false); }
  };

  if (guide) {
    return (
      <div className="grid gap-10">
        <div>
          <Button variant="ghost" onClick={() => setGuide(null)} data-testid="back-to-tasks-btn" className="rounded-sm gap-2 mb-6">
            <ArrowLeft className="h-4 w-4" /> Tous les travaux
          </Button>
          <p className="overline">Je le fais moi-même</p>
          <h1 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight" data-testid="guide-title">{guide.name}</h1>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <DifficultyBadge level={guide.difficulty} label={guide.difficulty_label} />
            <span className="num text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" /> {guide.duration}
            </span>
            {guide.materials?.length > 0 && (
              <div className="flex items-center gap-2">
                <Label className="text-xs">Surface (m²)</Label>
                <Input
                  type="number" value={area} onChange={(e) => setArea(e.target.value)}
                  onBlur={() => open(currentKey, area)} data-testid="guide-area-input"
                  className="rounded-sm h-8 w-24 num"
                />
              </div>
            )}
          </div>
        </div>

        {guide.safety?.length > 0 && (
          <Alert className={`rounded-md ${guide.pro_recommended ? "border-red-500/50 bg-red-500/5" : "border-amber-500/40 bg-amber-500/5"}`} data-testid="guide-safety">
            <ShieldAlert className={`h-5 w-5 ${guide.pro_recommended ? "text-red-500" : "text-amber-500"}`} />
            <AlertTitle className="font-display">
              {guide.pro_recommended ? "Intervenção de profissional fortemente recomendada" : "Sécurité"}
            </AlertTitle>
            <AlertDescription>
              <ul className="mt-2 grid gap-1 text-sm">{guide.safety.map((s, i) => <li key={i}>• {s}</li>)}</ul>
              {guide.pro_recommended && (
                <div className="mt-4"><LeadDialog label="Demander une intervention ConstruPilot" /></div>
              )}
            </AlertDescription>
          </Alert>
        )}

        {guide.materials?.length > 0 && (
          <div className="grid gap-4">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="font-display text-xl font-bold tracking-tight">Matériaux nécessaires</h2>
              <Button variant="outline" size="sm" onClick={findPrices} disabled={busy} data-testid="diy-find-prices-btn" className="rounded-sm gap-2 ml-auto">
                <Search className="h-4 w-4" /> Trouver les meilleurs prix
              </Button>
            </div>
            <div className="surface overflow-x-auto">
              <Table data-testid="guide-materials-table">
                <TableHeader>
                  <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                    <TableHead>Matériau</TableHead>
                    <TableHead className="text-right">Quantité (marge incluse)</TableHead>
                    <TableHead>Unité</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {guide.materials.map((m, i) => (
                    <TableRow key={i} className="even:bg-muted/30">
                      <TableCell className="font-medium">{m.name}</TableCell>
                      <TableCell className="num text-right">{num(m.quantity, 2)}</TableCell>
                      <TableCell className="text-muted-foreground">{m.unit}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
            {guide.calculation && (
              <p className="num text-sm">
                Budget matériaux estimé : <span className="text-primary font-bold">{eur(guide.calculation.estimated_budget)}</span>
              </p>
            )}
            {optim && (
              <div className="surface p-6 grid sm:grid-cols-3 gap-4" data-testid="diy-optimization">
                <div>
                  <p className="overline text-muted-foreground">Un seul fournisseur</p>
                  <p className="num mt-2 text-xl font-bold">{eur(optim.best_single?.total)}</p>
                  <p className="text-xs text-muted-foreground">{optim.best_single?.supplier}</p>
                </div>
                <div>
                  <p className="overline">Multi-fournisseurs</p>
                  <p className="num mt-2 text-xl font-bold text-primary">{eur(optim.multi_supplier.total)}</p>
                  <p className="num text-xs text-muted-foreground">{optim.multi_supplier.suppliers_count} magasins</p>
                </div>
                <div>
                  <p className="overline text-muted-foreground">Économie</p>
                  <p className="num mt-2 text-xl font-bold text-emerald-500">{eur(optim.savings)}</p>
                  <p className="num text-xs text-muted-foreground">{optim.savings_pct} %</p>
                </div>
              </div>
            )}
          </div>
        )}

        <div className="grid gap-4">
          <h2 className="font-display text-xl font-bold tracking-tight">Guide professionnel étape par étape</h2>
          <div className="grid gap-4" data-testid="guide-steps">
            {guide.steps.map((s, i) => (
              <div key={i} className="relative pl-8 border-l-2 border-border pb-2">
                <span className="absolute -left-[11px] top-1 h-5 w-5 grid place-items-center rounded-full bg-primary text-primary-foreground num text-[10px] font-bold">
                  {i + 1}
                </span>
                <div className="surface p-6">
                  <h3 className="font-display font-semibold">{s.title}</h3>
                  <p className="mt-2 text-sm">{s.text}</p>
                  <div className="mt-4 grid sm:grid-cols-3 gap-3 text-xs">
                    {s.tips && (
                      <div className="p-3 rounded-sm border border-emerald-500/30 bg-emerald-500/5">
                        <p className="overline text-emerald-600 dark:text-emerald-400">Conseil ConstruPilot</p>
                        <p className="mt-1 text-muted-foreground">{s.tips}</p>
                      </div>
                    )}
                    {s.mistakes && (
                      <div className="p-3 rounded-sm border border-red-500/30 bg-red-500/5">
                        <p className="overline text-red-600 dark:text-red-400">Erreur à éviter</p>
                        <p className="mt-1 text-muted-foreground">{s.mistakes}</p>
                      </div>
                    )}
                    {s.tools?.length > 0 && (
                      <div className="p-3 rounded-sm border border-border">
                        <p className="overline text-muted-foreground">Outils</p>
                        <p className="mt-1 text-muted-foreground">{s.tools.join(", ")}</p>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-10">
      <SEO title="Guide DIY travaux — Je le fais moi-même" description="Vous voulez faire les travaux vous-même ? ConstruPilot vous calcule les matériaux exacts et vous donne le guide étape par étape pour peindre, poser du carrelage, isoler, etc." keywords="DIY travaux, guide bricolage, faire ses travaux soi-même, poser carrelage soi-même, peindre soi-même" canonical="/diy" />
      <SectionTitle as="h1" over="DIY — Faço eu mesmo os trabalhos" title="Materiais calculados, guia de profissional">
        Choisissez un travail : ConstruPilot calcule les quantités (marges incluses), détaille chaque étape,
        les conseils, les erreurs à éviter et vous alerte quand un professionnel est nécessaire.
      </SectionTitle>

      <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4 stagger" data-testid="diy-tasks-grid">
        {tasks.map((t) => (
          <button
            key={t.key} onClick={() => open(t.key)} data-testid={`diy-task-${t.key}`}
            className="surface p-6 text-left transition-transform duration-200 hover:-translate-y-1 hover:border-primary/60"
          >
            <div className="flex items-start justify-between gap-3">
              <Wrench className="h-5 w-5 text-primary" />
              <DifficultyBadge level={t.difficulty} label={t.difficulty_label} />
            </div>
            <h3 className="mt-5 font-display text-lg font-semibold">{t.name}</h3>
            <p className="num mt-2 text-xs text-muted-foreground">
              {t.steps_count} étapes · {t.duration}
            </p>
            {t.calculator && (
              <p className="mt-3 text-xs text-primary flex items-center gap-1">
                <Package className="h-3 w-3" /> Quantités calculées automatiquement
              </p>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}
