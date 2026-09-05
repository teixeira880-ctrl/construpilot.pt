import { useState } from "react";
import { AlertTriangle, Clock, Wrench, TrendingDown, CalendarDays, ShieldAlert } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { eur, eur2, num } from "@/lib/api";
import { DifficultyBadge, Stat } from "@/components/Bits";
import { LeadDialog } from "@/components/LeadDialog";

export const EstimationView = ({ est, projectId }) => {
  if (!est) return null;
  const b = est.breakdown;
  const dp = est.diy_vs_pro;

  return (
    <div className="grid gap-8" data-testid="estimation-view">
      <div className="surface p-8 relative overflow-hidden grain">
        <div className="absolute -right-24 -top-24 h-64 w-64 bg-primary/20 blur-3xl rounded-full animate-glow" />
        <div className="relative">
          <p className="overline">Travaux estimés</p>
          <p className="num mt-4 text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight" data-testid="estimation-total">
            {eur(est.total_min)} <span className="text-muted-foreground font-normal">–</span> {eur(est.total_max)}
          </p>
          <p className="mt-3 text-base text-muted-foreground">
            {est.project_type_name} · {num(est.surface, 1)} m² · finition {est.finish_level_name} ·
            <span className="num"> {eur2(est.price_per_sqm)}/m²</span>
          </p>
          <div className="mt-8 grid sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {[
              ["Prix économique", est.price_model?.eco?.total, `${num(est.price_model?.eco?.per_sqm, 0)} €/m²`],
              ["Prix moyen", est.total_avg, `${num(est.price_per_sqm, 0)} €/m²`],
              ["Prix premium", est.price_model?.premium?.total, `${num(est.price_model?.premium?.per_sqm, 0)} €/m²`],
            ].map(([label, value, sub], i) => (
              <div key={label} className={`p-5 rounded-sm border ${i === 1 ? "border-primary bg-primary/5" : "border-border"}`}>
                <p className="text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
                <p className={`num mt-2 text-xl font-bold ${i === 1 ? "text-primary" : ""}`}>{eur(value)}</p>
                <p className="num mt-1 text-xs text-muted-foreground">{sub}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 stagger">
        <Stat label="Matériaux" value={eur(b.materials)} testId="stat-materials" />
        <Stat label="Main-d'œuvre" value={eur(b.labour)} testId="stat-labour" />
        <Stat label="Location matériel" value={eur(b.equipment_rental)} testId="stat-equipment" />
        <Stat label="Déchets / évacuation" value={eur(b.waste_disposal)} testId="stat-waste" />
        <Stat label="Marge imprévus" value={eur(b.contingency)} sub={`${Math.round(b.contingency_rate * 100)} % recommandés`} testId="stat-contingency" accent />
      </div>

      {est.safety_alerts?.length > 0 && (
        <Alert className="rounded-md border-red-500/40 bg-red-500/5" data-testid="safety-alerts">
          <ShieldAlert className="h-5 w-5 text-red-500" />
          <AlertTitle className="font-display">Intervention d'un professionnel fortement recommandée</AlertTitle>
          <AlertDescription>
            <ul className="mt-2 grid gap-1 text-sm">
              {est.safety_alerts.slice(0, 6).map((a, i) => <li key={i}>• {a.message}</li>)}
            </ul>
            <div className="mt-4">
              <LeadDialog projectId={projectId} budget={est.total_avg} label="Demander une intervention ConstruPilot" />
            </div>
          </AlertDescription>
        </Alert>
      )}

      <Tabs defaultValue="lots">
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="lots" className="rounded-sm" data-testid="tab-lots">Prix par lot</TabsTrigger>
          <TabsTrigger value="planning" className="rounded-sm" data-testid="tab-planning">Planning</TabsTrigger>
          <TabsTrigger value="diy" className="rounded-sm" data-testid="tab-diy">DIY ou artisan</TabsTrigger>
        </TabsList>

        <TabsContent value="lots" className="mt-6">
          <div className="surface overflow-x-auto">
            <Table data-testid="lots-table">
              <TableHeader>
                <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                  <TableHead>Lot</TableHead>
                  <TableHead className="text-right">Quantité</TableHead>
                  <TableHead className="text-right">Matériaux</TableHead>
                  <TableHead className="text-right">Main-d'œuvre</TableHead>
                  <TableHead className="text-right">Prix / unité</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead className="text-right">Temps</TableHead>
                  <TableHead>Difficulté</TableHead>
                  <TableHead className="min-w-[200px]">Matériel nécessaire</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {est.lots.map((l) => (
                  <TableRow key={l.key} className="even:bg-muted/30" data-testid={`lot-row-${l.key}`}>
                    <TableCell className="font-medium">{l.name}</TableCell>
                    <TableCell className="num text-right">{num(l.quantity, 2)} {l.unit}</TableCell>
                    <TableCell className="num text-right">{eur(l.material_cost)}</TableCell>
                    <TableCell className="num text-right">{eur(l.labour_cost)}</TableCell>
                    <TableCell className="num text-right">{eur2(l.price_per_unit)}</TableCell>
                    <TableCell className="num text-right font-semibold text-primary">{eur(l.total)}</TableCell>
                    <TableCell className="num text-right whitespace-nowrap">{num(l.hours, 1)} h</TableCell>
                    <TableCell><DifficultyBadge level={l.difficulty} label={l.difficulty_label} /></TableCell>
                    <TableCell className="text-xs text-muted-foreground">{l.tools?.join(", ")}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </TabsContent>

        <TabsContent value="planning" className="mt-6">
          <div className="surface p-6">
            <p className="text-sm text-muted-foreground mb-6">
              <CalendarDays className="inline h-4 w-4 mr-2 text-primary" />
              Durée totale estimée : <span className="num font-semibold text-foreground">{est.duration_weeks} semaines</span>
              {" "}· <span className="num">{num(est.total_hours, 0)} h</span> de main-d'œuvre
            </p>
            <div className="grid gap-3" data-testid="planning-list">
              {(est.planning || []).map((p, i) => (
                <div key={p.lot} className="flex items-center gap-4 pl-5 relative border-l-2 border-border py-1">
                  <span className="absolute -left-[7px] h-3 w-3 rounded-full bg-primary" />
                  <span className="num text-xs w-24 shrink-0 text-primary font-semibold">
                    S{p.start_week}{p.end_week !== p.start_week ? `→S${p.end_week}` : ""}
                  </span>
                  <span className="font-medium">{p.name}</span>
                  <span className="num ml-auto text-xs text-muted-foreground">{p.duration_weeks} sem.</span>
                </div>
              ))}
            </div>
          </div>
        </TabsContent>

        <TabsContent value="diy" className="mt-6">
          {dp && (
            <div className="grid lg:grid-cols-3 gap-4" data-testid="diy-vs-pro">
              <div className="surface p-6">
                <p className="overline text-muted-foreground">Par un professionnel</p>
                <p className="num mt-3 text-2xl font-bold">{eur(dp.pro_total)}</p>
              </div>
              <div className="surface p-6 border-primary">
                <p className="overline">En le faisant moi-même</p>
                <p className="num mt-3 text-2xl font-bold text-primary">{eur(dp.diy_total)}</p>
                <p className="num mt-1 text-xs text-muted-foreground"><Clock className="inline h-3 w-3 mr-1" />{num(dp.diy_hours)} h de travail</p>
              </div>
              <div className="surface p-6">
                <p className="overline text-muted-foreground">Économie potentielle</p>
                <p className="num mt-3 text-2xl font-bold text-emerald-500">
                  <TrendingDown className="inline h-5 w-5 mr-1" />{eur(dp.savings)}
                </p>
                <p className="num mt-1 text-xs text-muted-foreground">soit {dp.savings_pct} % · risque {dp.risk}</p>
              </div>
              <div className="lg:col-span-3 surface p-6">
                <p className="overline">Conclusion ConstruPilot</p>
                <p className="mt-3 text-sm">{dp.conclusion}</p>
                <div className="mt-5 flex flex-wrap gap-2">
                  {dp.diy_tasks.map((t) => (
                    <Badge key={t} variant="outline" className="rounded-sm border-emerald-500/40 text-emerald-600 dark:text-emerald-400">
                      <Wrench className="h-3 w-3 mr-1" />{t}
                    </Badge>
                  ))}
                  {dp.pro_tasks.map((t) => (
                    <Badge key={t} variant="outline" className="rounded-sm border-red-500/40 text-red-600 dark:text-red-400">
                      <AlertTriangle className="h-3 w-3 mr-1" />{t}
                    </Badge>
                  ))}
                </div>
              </div>
            </div>
          )}
        </TabsContent>
      </Tabs>
    </div>
  );
};
