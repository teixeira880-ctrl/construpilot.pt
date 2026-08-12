import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { toast } from "sonner";
import {
  Download, Sparkles, ShoppingCart, Plus, Wallet, AlertTriangle, RefreshCw, Package,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, API, eur, eur2, num } from "@/lib/api";
import { EstimationView } from "@/components/EstimationView";
import { LeadDialog } from "@/components/LeadDialog";
import { Stat } from "@/components/Bits";

const NEXT = { todo: "doing", doing: "done", done: "todo" };
const LABEL = { todo: "⏳ À faire", doing: "🔄 En cours", done: "✅ Terminé" };

export default function ProjectDetail() {
  const { id } = useParams();
  const [p, setP] = useState(null);
  const [budget, setBudget] = useState(null);
  const [materials, setMaterials] = useState([]);
  const [optim, setOptim] = useState(null);
  const [busy, setBusy] = useState("");
  const [exp, setExp] = useState({ label: "", amount: "" });

  const load = async () => {
    const { data } = await api.get(`/projects/${id}`);
    setP(data);
    setMaterials(data.materials || []);
    const b = await api.get(`/projects/${id}/budget`);
    setBudget(b.data);
  };
  useEffect(() => { load(); }, [id]);

  if (!p) return <div className="h-40 grid place-items-center"><div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const toggle = async (key) => {
    const progress = { ...p.progress, [key]: NEXT[p.progress[key] || "todo"] };
    await api.patch(`/projects/${id}`, { progress });
    load();
  };

  const genAdvice = async () => {
    setBusy("advice");
    try {
      const { data } = await api.post(`/projects/${id}/advice`);
      setP({ ...p, advice: data.advice });
      toast.success("Conseils IA générés");
    } catch { toast.error("Génération impossible"); }
    finally { setBusy(""); }
  };

  const buildMaterials = async () => {
    setBusy("materials");
    try {
      const { data } = await api.post("/estimation/materials", { lots: p.estimation.lots });
      setMaterials(data.items);
      await api.patch(`/projects/${id}`, { materials: data.items });
      toast.success(`${data.items.length} lignes de matériaux générées`);
    } catch { toast.error("Génération impossible"); }
    finally { setBusy(""); }
  };

  const optimize = async () => {
    setBusy("optimize");
    try {
      const { data } = await api.post("/prices/optimize", {
        items: materials.map((m) => ({ query: m.search, quantity: Math.ceil(m.quantity), name: m.name })),
      });
      setOptim(data);
    } catch { toast.error("Optimisation impossible"); }
    finally { setBusy(""); }
  };

  const addExpense = async () => {
    if (!exp.label || !exp.amount) return;
    const { data } = await api.post(`/projects/${id}/expenses`, {
      label: exp.label, amount: Number(exp.amount),
    });
    setBudget(data);
    setExp({ label: "", amount: "" });
    toast.success("Dépense ajoutée");
  };

  const downloadPdf = async () => {
    setBusy("pdf");
    try {
      const res = await api.get(`/projects/${id}/pdf`, { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Estimation-CMRENOV-${p.name}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("PDF généré");
    } catch { toast.error("PDF indisponible"); }
    finally { setBusy(""); }
  };

  return (
    <div className="grid gap-10">
      <div className="flex flex-col lg:flex-row gap-6 lg:items-end justify-between">
        <div>
          <p className="overline">{p.estimation.project_type_name}</p>
          <h1 className="mt-3 font-display text-3xl lg:text-4xl font-bold tracking-tight" data-testid="project-title">{p.name}</h1>
          <p className="num mt-2 text-sm text-muted-foreground">
            {num(p.surface, 1)} m² · {p.city || p.region || "France"} · finition {p.estimation.finish_level_name}
          </p>
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={downloadPdf} disabled={busy === "pdf"} data-testid="download-pdf-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Download className="h-4 w-4" /> {busy === "pdf" ? "Génération…" : "Télécharger le PDF"}
          </Button>
          <LeadDialog projectId={p.project_id} budget={p.estimation.total_avg} description={p.description} />
        </div>
      </div>

      {budget && (
        <div className="grid gap-4">
          <div className="grid sm:grid-cols-2 lg:grid-cols-5 gap-4 stagger">
            <Stat label="Budget initial" value={eur(budget.initial)} testId="budget-initial" />
            <Stat label="Dépensé" value={eur(budget.spent)} testId="budget-spent" />
            <Stat label="Restant" value={eur(budget.remaining)} testId="budget-remaining" accent />
            <Stat label="Prévision finale" value={eur(budget.forecast)} testId="budget-forecast" />
            <Stat label="Dépassement probable" value={eur(budget.overrun)} sub={`${budget.progress_pct} % réalisé`} testId="budget-overrun" />
          </div>
          <div className="surface p-6">
            <div className="flex items-center gap-4">
              <Wallet className="h-4 w-4 text-primary" />
              <Progress value={Math.min(100, (budget.spent / budget.initial) * 100)} className="h-2 rounded-none" data-testid="budget-gauge" />
              <span className="num text-xs text-muted-foreground whitespace-nowrap">
                {num((budget.spent / budget.initial) * 100, 1)} %
              </span>
            </div>
            {budget.warning && (
              <p className="mt-4 text-sm text-amber-500 flex gap-2" data-testid="budget-warning">
                <AlertTriangle className="h-4 w-4 shrink-0 mt-0.5" /> {budget.warning}
              </p>
            )}
            <div className="mt-6 flex flex-wrap gap-3 items-end">
              <Input placeholder="Libellé de la dépense" value={exp.label} onChange={(e) => setExp({ ...exp, label: e.target.value })} data-testid="expense-label-input" className="rounded-sm max-w-xs" />
              <Input type="number" placeholder="Montant €" value={exp.amount} onChange={(e) => setExp({ ...exp, amount: e.target.value })} data-testid="expense-amount-input" className="rounded-sm max-w-[140px] num" />
              <Button onClick={addExpense} variant="outline" data-testid="add-expense-btn" className="rounded-sm gap-2">
                <Plus className="h-4 w-4" /> Ajouter
              </Button>
            </div>
            {budget.expenses?.length > 0 && (
              <div className="mt-5 grid gap-2" data-testid="expenses-list">
                {budget.expenses.map((e) => (
                  <div key={e.expense_id} className="flex justify-between text-sm border-b border-border pb-2">
                    <span>{e.label}</span>
                    <span className="num font-medium">{eur2(e.amount)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      <Tabs defaultValue="works">
        <TabsList className="rounded-sm flex-wrap h-auto">
          <TabsTrigger value="works" className="rounded-sm" data-testid="pd-tab-works">Travaux & progression</TabsTrigger>
          <TabsTrigger value="estimation" className="rounded-sm" data-testid="pd-tab-estimation">Estimation</TabsTrigger>
          <TabsTrigger value="materials" className="rounded-sm" data-testid="pd-tab-materials">Matériaux & panier</TabsTrigger>
          <TabsTrigger value="advice" className="rounded-sm" data-testid="pd-tab-advice">Conseils IA</TabsTrigger>
        </TabsList>

        <TabsContent value="works" className="mt-6">
          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-3" data-testid="progress-grid">
            {p.estimation.lots.map((l) => (
              <button
                key={l.key} onClick={() => toggle(l.key)} data-testid={`progress-toggle-${l.key}`}
                className="surface p-5 text-left transition-colors hover:border-primary/60"
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="font-medium">{l.name}</p>
                  <Badge variant="outline" className="rounded-sm shrink-0">{LABEL[p.progress?.[l.key] || "todo"]}</Badge>
                </div>
                <p className="num mt-3 text-sm text-primary font-semibold">{eur(l.total)}</p>
                <p className="num mt-1 text-xs text-muted-foreground">{num(l.quantity, 2)} {l.unit} · {num(l.hours, 1)} h</p>
              </button>
            ))}
          </div>
        </TabsContent>

        <TabsContent value="estimation" className="mt-6">
          <EstimationView est={p.estimation} projectId={p.project_id} />
        </TabsContent>

        <TabsContent value="materials" className="mt-6 grid gap-6">
          <div className="flex flex-wrap gap-3">
            <Button onClick={buildMaterials} disabled={busy === "materials"} data-testid="build-materials-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Package className="h-4 w-4" /> {busy === "materials" ? "Calcul…" : "Générer ma liste d'achats"}
            </Button>
            {materials.length > 0 && (
              <Button variant="outline" onClick={optimize} disabled={busy === "optimize"} data-testid="optimize-cart-btn" className="rounded-sm gap-2">
                {busy === "optimize" ? <RefreshCw className="h-4 w-4 animate-spin" /> : <ShoppingCart className="h-4 w-4" />}
                Optimiser mes achats
              </Button>
            )}
          </div>

          {materials.length > 0 && (
            <div className="surface overflow-x-auto">
              <Table data-testid="materials-table">
                <TableHeader>
                  <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                    <TableHead>Matériau</TableHead>
                    <TableHead className="text-right">Quantité</TableHead>
                    <TableHead>Unité</TableHead>
                    <TableHead>Recherche fournisseur</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {materials.map((m, i) => (
                    <TableRow key={i} className="even:bg-muted/30">
                      <TableCell className="font-medium">{m.name}</TableCell>
                      <TableCell className="num text-right">{num(m.quantity, 2)}</TableCell>
                      <TableCell className="text-muted-foreground">{m.unit}</TableCell>
                      <TableCell className="num text-xs text-muted-foreground">{m.search}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}

          {optim && (
            <div className="grid gap-4" data-testid="optimization-result">
              <div className="grid sm:grid-cols-3 gap-4">
                <div className="surface p-6">
                  <p className="overline text-muted-foreground">Tout chez {optim.best_single?.supplier}</p>
                  <p className="num mt-3 text-2xl font-bold">{eur(optim.best_single?.total)}</p>
                </div>
                <div className="surface p-6 border-primary">
                  <p className="overline">Chez {optim.multi_supplier.suppliers_count} fournisseurs</p>
                  <p className="num mt-3 text-2xl font-bold text-primary">{eur(optim.multi_supplier.total)}</p>
                </div>
                <div className="surface p-6">
                  <p className="overline text-muted-foreground">Économie</p>
                  <p className="num mt-3 text-2xl font-bold text-emerald-500">{eur(optim.savings)}</p>
                  <p className="num mt-1 text-xs text-muted-foreground">soit {optim.savings_pct} %</p>
                </div>
              </div>
              <div className="surface overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                      <TableHead>Produit</TableHead>
                      <TableHead className="text-right">Qté</TableHead>
                      <TableHead>Meilleur fournisseur</TableHead>
                      <TableHead className="text-right">Prix unitaire</TableHead>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead>Stock</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {optim.lines.map((l, i) => (
                      <TableRow key={i} className="even:bg-muted/30">
                        <TableCell className="font-medium">{l.name}</TableCell>
                        <TableCell className="num text-right">{l.quantity}</TableCell>
                        <TableCell>{l.supplier}</TableCell>
                        <TableCell className="num text-right">{eur2(l.unit_price)}</TableCell>
                        <TableCell className="num text-right font-semibold text-primary">{eur2(l.total)}</TableCell>
                        <TableCell className="text-xs text-muted-foreground">{l.stock}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <p className="text-xs text-muted-foreground">
                Source : connecteur de démonstration (mode {optim.mode}) — frais de livraison et minimums de
                commande inclus. Vérifié le {new Date(optim.checked_at).toLocaleString("fr-FR")}.
              </p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="advice" className="mt-6">
          <div className="surface p-8">
            <Button onClick={genAdvice} disabled={busy === "advice"} data-testid="generate-advice-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Sparkles className="h-4 w-4" /> {busy === "advice" ? "Génération…" : "Générer les conseils CMRENOV AI"}
            </Button>
            {p.advice && (
              <div className="mt-8 grid gap-3 text-sm" data-testid="advice-content">
                {p.advice.split("\n").filter((l) => l.trim()).map((line, i) => (
                  <p key={i} className="flex gap-3">
                    <span className="text-primary">▸</span>
                    <span>{line.replace(/^[-•*]\s*/, "")}</span>
                  </p>
                ))}
              </div>
            )}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
