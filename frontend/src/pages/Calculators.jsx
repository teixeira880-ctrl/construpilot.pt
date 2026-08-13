import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Calculator, Search, ShoppingCart } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, eur, eur2, num } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";

export default function Calculators() {
  const [calcs, setCalcs] = useState([]);
  const [active, setActive] = useState(null);
  const [params, setParams] = useState({});
  const [result, setResult] = useState(null);
  const [optim, setOptim] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/calculators").then(({ data }) => {
      setCalcs(data);
      pick(data[0]);
    });
  }, []);

  const pick = (c) => {
    setActive(c);
    setResult(null);
    setOptim(null);
    const init = {};
    c.fields.forEach((f) => { if (f.default !== null && f.default !== undefined) init[f.name] = f.default; });
    setParams(init);
  };

  const run = async () => {
    setBusy(true);
    try {
      const { data } = await api.post(`/calculators/${active.key}`, { params });
      setResult(data);
      setOptim(null);
    } catch { toast.error("Calcul impossible"); }
    finally { setBusy(false); }
  };

  const findPrices = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/prices/optimize", {
        items: result.materials.map((m) => ({ query: m.search, quantity: Math.ceil(m.quantity), name: m.name })),
      });
      setOptim(data);
    } catch { toast.error("Recherche impossible"); }
    finally { setBusy(false); }
  };

  if (!active) return <div className="h-40 grid place-items-center"><div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  return (
    <div className="grid gap-10">
      <SEO title="Calculateurs matériaux BTP" description="Calculez les quantités exactes de peinture, carrelage, placo, béton et isolation pour vos chantiers. Marges de sécurité incluses. Génère la liste de courses matériaux." keywords="calculateur peinture, calculateur carrelage, calculateur placo, calculateur béton, calculateur isolation, quantité matériaux" canonical="/calculateurs" />
      <SectionTitle as="h1" over="Calculateur de matériaux" title="Les quantités exactes, marges incluses">
        Calculs déterministes et vérifiables : surfaces, volumes, pertes de pose et conditionnements.
      </SectionTitle>

      <div className="flex flex-wrap gap-2" data-testid="calculator-tabs">
        {calcs.map((c) => (
          <button
            key={c.key} onClick={() => pick(c)} data-testid={`calculator-tab-${c.key}`}
            className={`px-4 py-2.5 text-sm rounded-sm border transition-colors ${
              active.key === c.key ? "border-primary bg-primary/15 text-primary font-semibold" : "border-border text-muted-foreground hover:border-primary/50"
            }`}
          >
            {c.name}
          </button>
        ))}
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="surface p-6 grid gap-5 h-fit" data-testid="calculator-form">
          {active.fields.map((f) => (
            <div key={f.name} className="grid gap-2">
              <Label>{f.label}</Label>
              {f.type === "select" ? (
                <Select value={String(params[f.name] ?? "")} onValueChange={(v) => setParams({ ...params, [f.name]: v })}>
                  <SelectTrigger className="rounded-sm h-11" data-testid={`calc-field-${f.name}`}><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {f.options.map((o) => <SelectItem key={o} value={o}>{o.replace(/_/g, " ")}</SelectItem>)}
                  </SelectContent>
                </Select>
              ) : f.type === "boolean" ? (
                <Switch
                  checked={!!params[f.name]} data-testid={`calc-field-${f.name}`}
                  onCheckedChange={(v) => setParams({ ...params, [f.name]: v })}
                />
              ) : (
                <Input
                  type="number" step="any" value={params[f.name] ?? ""} data-testid={`calc-field-${f.name}`}
                  onChange={(e) => setParams({ ...params, [f.name]: e.target.value })}
                  className="rounded-sm h-11 num"
                />
              )}
            </div>
          ))}
          <Button onClick={run} disabled={busy} data-testid="calculate-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Calculator className="h-4 w-4" /> Calculer
          </Button>
        </div>

        <div className="lg:col-span-2 grid gap-6">
          {!result && (
            <div className="surface p-12 text-center text-sm text-muted-foreground" data-testid="calculator-empty">
              Renseignez les dimensions puis lancez le calcul.
            </div>
          )}
          {result && (
            <>
              <div className="surface p-6" data-testid="calculator-results">
                <p className="overline">Résultats</p>
                <div className="mt-5 grid sm:grid-cols-2 gap-3">
                  {result.results.map((r, i) => (
                    <div key={i} className="p-4 border border-border rounded-sm">
                      <p className="text-xs text-muted-foreground">{r.label}</p>
                      <p className="num mt-1 text-lg font-bold">{num(r.value, 2)} <span className="text-sm font-normal text-muted-foreground">{r.unit}</span></p>
                    </div>
                  ))}
                </div>
                <p className="num mt-6 text-sm">
                  Budget matériaux estimé : <span className="text-primary font-bold text-lg">{eur(result.estimated_budget)}</span>
                </p>
              </div>

              <div className="surface overflow-x-auto">
                <Table data-testid="calculator-materials">
                  <TableHeader>
                    <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                      <TableHead>Matériau à acheter</TableHead>
                      <TableHead className="text-right">Quantité</TableHead>
                      <TableHead>Unité</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {result.materials.map((m, i) => (
                      <TableRow key={i} className="even:bg-muted/30">
                        <TableCell className="font-medium">{m.name}</TableCell>
                        <TableCell className="num text-right">{num(m.quantity, 2)}</TableCell>
                        <TableCell className="text-muted-foreground">{m.unit}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              <Button variant="outline" onClick={findPrices} disabled={busy} data-testid="find-prices-btn" className="rounded-sm gap-2 w-fit">
                <Search className="h-4 w-4" /> Trouver les meilleurs prix pour cette liste
              </Button>

              {optim && (
                <div className="grid gap-4" data-testid="calculator-optimization">
                  <div className="grid sm:grid-cols-3 gap-4">
                    <div className="surface p-6">
                      <p className="overline text-muted-foreground">Tout chez {optim.best_single?.supplier}</p>
                      <p className="num mt-3 text-xl font-bold">{eur(optim.best_single?.total)}</p>
                    </div>
                    <div className="surface p-6 border-primary">
                      <p className="overline">Multi-fournisseurs</p>
                      <p className="num mt-3 text-xl font-bold text-primary">{eur(optim.multi_supplier.total)}</p>
                    </div>
                    <div className="surface p-6">
                      <p className="overline text-muted-foreground">Économie</p>
                      <p className="num mt-3 text-xl font-bold text-emerald-500">{eur(optim.savings)}</p>
                    </div>
                  </div>
                  <div className="surface overflow-x-auto">
                    <Table>
                      <TableHeader>
                        <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                          <TableHead>Produit</TableHead>
                          <TableHead className="text-right">Qté</TableHead>
                          <TableHead>Fournisseur</TableHead>
                          <TableHead className="text-right">PU</TableHead>
                          <TableHead className="text-right">Total</TableHead>
                        </TableRow>
                      </TableHeader>
                      <TableBody>
                        {optim.lines.map((l, i) => (
                          <TableRow key={i} className="even:bg-muted/30">
                            <TableCell>{l.name}</TableCell>
                            <TableCell className="num text-right">{l.quantity}</TableCell>
                            <TableCell>{l.supplier}</TableCell>
                            <TableCell className="num text-right">{eur2(l.unit_price)}</TableCell>
                            <TableCell className="num text-right font-semibold text-primary">{eur2(l.total)}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </div>
                  <p className="text-xs text-muted-foreground flex items-center gap-2">
                    <ShoppingCart className="h-3 w-3" /> Mode {optim.mode} — prix de démonstration, branchez les
                    API fournisseurs pour des prix réels.
                  </p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
