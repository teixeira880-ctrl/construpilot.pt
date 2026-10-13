import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Calculator, Search, ShoppingCart, FileDown, FilePlus2, Columns3, Loader2, ListPlus, X, Share2, Copy, Mail, MessageSquare, Lock } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, eur, eur2, num } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";

const COMPARE_CONFIG = {
  drywall: {
    variants: [
      { plate_length: 200, plate_width: 120 },
      { plate_length: 250, plate_width: 120 },
      { plate_length: 260, plate_width: 120 },
      { plate_length: 300, plate_width: 120 },
    ],
    label: (v) => `${v.plate_length}×${v.plate_width} cm`,
    metric: { title: "Plaques nécessaires", match: /plaque/i },
    caption: "Ossature, vis et enduit inclus. Le format le moins cher est surligné.",
  },
  tile: {
    variants: [
      { tile_length: 30, tile_width: 30 },
      { tile_length: 45, tile_width: 45 },
      { tile_length: 60, tile_width: 60 },
      { tile_length: 60, tile_width: 120 },
      { tile_length: 90, tile_width: 90 },
    ],
    label: (v) => `${v.tile_length}×${v.tile_width} cm`,
    metric: { title: "Carreaux", match: /carreau/i },
    caption: "Pertes de pose incluses selon le type de pose sélectionné. Le format le moins cher est surligné.",
  },
};

export default function Calculators() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { has } = useBilling();
  const isPremium = has("calculator_pro_tools");
  const gate = () => {
    if (isPremium) return true;
    if (!user) {
      toast.info("Créez un compte et passez Premium pour débloquer cette fonction");
      navigate("/login");
      return false;
    }
    toast.info("Fonction Premium — passez à une offre payante pour l'utiliser 🔒");
    navigate("/tarifs");
    return false;
  };
  const [calcs, setCalcs] = useState([]);
  const [active, setActive] = useState(null);
  const [params, setParams] = useState({});
  const [result, setResult] = useState(null);
  const [optim, setOptim] = useState(null);
  const [compare, setCompare] = useState(null);
  const [cart, setCart] = useState(() => {
    try { return JSON.parse(localStorage.getItem("construpilot_calc_cart") || "[]"); }
    catch { return []; }
  });
  const [busy, setBusy] = useState(false);
  const [busyPdf, setBusyPdf] = useState(false);
  const [addingQuote, setAddingQuote] = useState(false);
  const [shareUrl, setShareUrl] = useState(null);
  const [sharing, setSharing] = useState(false);

  useEffect(() => {
    try { localStorage.setItem("construpilot_calc_cart", JSON.stringify(cart)); } catch { /* ignore */ }
  }, [cart]);

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
    setCompare(null);
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
      setCompare(null);
    } catch { toast.error("Calcul impossible"); }
    finally { setBusy(false); }
  };

  const compareFormats = async () => {
    if (!gate()) return;
    const cfg = COMPARE_CONFIG[active.key];
    if (!cfg) return;
    setBusy(true);
    try {
      const runs = await Promise.all(cfg.variants.map((v) =>
        api.post(`/calculators/${active.key}`, { params: { ...params, ...v } })
          .then(({ data }) => ({
            format: cfg.label(v),
            metric: data.results.find((r) => cfg.metric.match.test(r.label))?.value ?? "—",
            budget: data.estimated_budget,
          }))
      ));
      setCompare({ rows: runs, cfg });
    } catch { toast.error("Comparaison impossible"); }
    finally { setBusy(false); }
  };

  const shareSheet = async () => {
    if (!gate()) return;
    setSharing(true);
    try {
      const inputs = active.fields.map((f) => ({
        label: f.label, value: String(params[f.name] ?? f.default ?? "—").replace(/_/g, " "),
      }));
      const payload = {
        name: active.name, inputs, results: result.results,
        materials: result.materials.map((m) => ({ name: m.name, quantity: Math.round(m.quantity * 100) / 100, unit: m.unit })),
        estimated_budget: result.estimated_budget,
        contractor: user ? (user.company || user.name || "") : "",
      };
      if (optim?.lines?.length) {
        payload.priced_lines = optim.lines.map((l) => ({
          name: l.name, quantity: l.quantity, supplier: l.supplier, unit_price: l.unit_price, total: l.total,
        }));
        payload.priced_total = optim.multi_supplier?.total ?? null;
      }
      const { data } = await api.post("/calculators-share", payload);
      setShareUrl(`${window.location.origin}/fiche/${data.share_id}`);
    } catch { toast.error("Partage impossible"); }
    finally { setSharing(false); }
  };

  const addToSelection = () => {
    setCart((c) => [...c, {
      id: Date.now() + Math.random(),
      name: active.name,
      materials: result.materials.map((m) => ({ name: m.name, quantity: m.quantity, unit: m.unit })),
    }]);
    toast.success(`« ${active.name} » ajouté à la sélection`);
  };

  const buildGroupedQuote = async () => {
    if (!gate()) return;
    if (!user) { toast.info("Connectez-vous pour créer un devis"); navigate("/login"); return; }
    setAddingQuote(true);
    try {
      const lines = cart.flatMap((entry) => entry.materials.map((m) => ({
        designation: m.name, unit: m.unit, qty: Math.ceil(m.quantity),
        unit_price_ht: 0, vat_rate: 10, category: entry.name,
      })));
      const { data } = await api.post("/documents", {
        doc_type: "quote", title: `Devis — ${cart.map((e) => e.name).join(" + ")}`, lines,
      });
      toast.success("Devis groupé créé — complétez les prix");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch { toast.error("Création du devis impossible"); }
    finally { setAddingQuote(false); }
  };

  const exportPdf = async () => {
    if (!gate()) return;
    setBusyPdf(true);
    try {
      const inputs = active.fields.map((f) => ({
        label: f.label, value: String(params[f.name] ?? f.default ?? "—").replace(/_/g, " "),
      }));
      const payload = {
        name: active.name,
        inputs,
        results: result.results,
        materials: result.materials.map((m) => ({ name: m.name, quantity: Math.round(m.quantity * 100) / 100, unit: m.unit })),
        estimated_budget: result.estimated_budget,
      };
      if (optim?.lines?.length) {
        payload.priced_lines = optim.lines.map((l) => ({
          name: l.name, quantity: l.quantity, supplier: l.supplier,
          unit_price: l.unit_price, total: l.total,
        }));
        payload.priced_total = optim.multi_supplier?.total ?? null;
      }
      const { data } = await api.post("/calculators-pdf", payload, { responseType: "blob" });
      const url = URL.createObjectURL(new Blob([data], { type: "application/pdf" }));
      const a = document.createElement("a");
      a.href = url; a.download = `fiche-calcul-${active.key}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
    } catch { toast.error("Export PDF impossible"); }
    finally { setBusyPdf(false); }
  };

  const addToQuote = async () => {
    if (!gate()) return;
    if (!user) {
      toast.info("Connectez-vous pour créer un devis");
      navigate("/login");
      return;
    }
    setAddingQuote(true);
    try {
      const lines = result.materials.map((m) => ({
        designation: m.name, unit: m.unit, qty: Math.ceil(m.quantity),
        unit_price_ht: 0, vat_rate: 10, category: active.name,
      }));
      const { data } = await api.post("/documents", {
        doc_type: "quote", title: `Devis — ${active.name}`, lines,
      });
      toast.success("Devis créé — complétez les prix");
      navigate(`/devis-editeur/${data.doc_id}`);
    } catch { toast.error("Création du devis impossible"); }
    finally { setAddingQuote(false); }
  };

  const findPrices = async () => {
    setBusy(true);
    try {
      const coefficient = Number(localStorage.getItem("construpilot_dept_coef") || 1) || 1;
      const { data } = await api.post("/prices/optimize", {
        coefficient,
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

      {cart.length > 0 && (
        <div className="surface p-5 rounded-md border-primary/40" data-testid="calc-cart">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="overline flex items-center gap-2"><ShoppingCart className="h-3.5 w-3.5" /> Ma sélection ({cart.length} {cart.length > 1 ? "calculs" : "calcul"})</p>
              <div className="mt-2 flex flex-wrap gap-2">
                {cart.map((e, i) => (
                  <span key={e.id} className="inline-flex items-center gap-1.5 text-sm bg-muted/50 border border-border rounded-full pl-3 pr-1.5 py-1" data-testid={`calc-cart-item-${i}`}>
                    {e.name} <span className="text-xs text-muted-foreground">· {e.materials.length} lignes</span>
                    <button onClick={() => setCart((c) => c.filter((x) => x.id !== e.id))} data-testid={`calc-cart-remove-${i}`}
                      className="grid place-items-center h-5 w-5 rounded-full hover:bg-red-500/20 text-muted-foreground hover:text-red-500">
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
              </div>
            </div>
            <div className="flex gap-2">
              <Button variant="ghost" className="rounded-sm text-muted-foreground" onClick={() => setCart([])} data-testid="calc-cart-clear">Vider</Button>
              <Button className="rounded-sm gap-2" disabled={addingQuote} onClick={buildGroupedQuote} data-testid="calc-cart-quote-btn">
                {addingQuote ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePlus2 className="h-4 w-4" />} Créer le devis groupé
              </Button>
            </div>
          </div>
        </div>
      )}

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

                <div className="mt-6 flex flex-wrap gap-2 pt-5 border-t border-border">
                  {!isPremium && (
                    <button onClick={() => navigate("/tarifs")} data-testid="calc-premium-banner"
                      className="w-full mb-1 flex items-center gap-2 text-sm bg-primary/10 border border-primary/30 text-primary rounded-sm px-4 py-2.5 hover:bg-primary/15 transition-colors">
                      <Lock className="h-4 w-4" />
                      <span>Export PDF, devis et partage sont <b>Premium</b> — débloquez-les.</span>
                      <span className="ml-auto font-semibold underline">Passer Premium →</span>
                    </button>
                  )}
                  <Button onClick={exportPdf} disabled={busyPdf} variant="outline" className="rounded-sm gap-2" data-testid="calc-export-pdf-btn">
                    {busyPdf ? <Loader2 className="h-4 w-4 animate-spin" /> : (!isPremium ? <Lock className="h-4 w-4" /> : <FileDown className="h-4 w-4" />)}
                    {optim ? "Exporter PDF (avec prix)" : "Exporter en PDF"}
                  </Button>
                  <Button onClick={addToQuote} disabled={addingQuote} className="rounded-sm gap-2" data-testid="calc-add-quote-btn">
                    {addingQuote ? <Loader2 className="h-4 w-4 animate-spin" /> : <FilePlus2 className="h-4 w-4" />} Ajouter au devis
                  </Button>
                  <Button onClick={addToSelection} variant="outline" className="rounded-sm gap-2" data-testid="calc-add-selection-btn">
                    <ListPlus className="h-4 w-4" /> Ajouter à la sélection
                  </Button>
                  <Button onClick={shareSheet} disabled={sharing} variant="outline" className="rounded-sm gap-2" data-testid="calc-share-btn">
                    {sharing ? <Loader2 className="h-4 w-4 animate-spin" /> : <Share2 className="h-4 w-4" />} Partager la fiche
                  </Button>
                  {COMPARE_CONFIG[active.key] && (
                    <Button onClick={compareFormats} disabled={busy} variant="outline" className="rounded-sm gap-2" data-testid="calc-compare-btn">
                      <Columns3 className="h-4 w-4" /> Comparer les formats
                    </Button>
                  )}
                </div>
              </div>

              {compare && (
                <div className="surface overflow-x-auto" data-testid="calc-compare-table">
                  <div className="px-6 pt-5">
                    <p className="overline">Comparaison des formats</p>
                    <p className="text-xs text-muted-foreground mt-1">{compare.cfg.caption}</p>
                  </div>
                  <Table>
                    <TableHeader>
                      <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                        <TableHead>Format</TableHead>
                        <TableHead className="text-right">{compare.cfg.metric.title}</TableHead>
                        <TableHead className="text-right">Budget estimé</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {compare.rows.map((c, i) => {
                        const best = Math.min(...compare.rows.map((x) => x.budget || Infinity));
                        const isBest = (c.budget || Infinity) === best;
                        return (
                          <TableRow key={i} className={isBest ? "bg-primary/10" : "even:bg-muted/30"}>
                            <TableCell className="font-medium">{c.format} {isBest && <span className="text-primary text-xs font-semibold ml-2">✓ le moins cher</span>}</TableCell>
                            <TableCell className="num text-right">{num(c.metric, 0)}</TableCell>
                            <TableCell className="num text-right font-semibold text-primary">{eur(c.budget)}</TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </div>
              )}

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

      <Dialog open={!!shareUrl} onOpenChange={(o) => !o && setShareUrl(null)}>
        <DialogContent className="max-w-md" data-testid="calc-share-dialog">
          <DialogHeader>
            <DialogTitle>Partager la fiche de calcul</DialogTitle>
            <DialogDescription>Envoyez ce lien à votre client par SMS ou e-mail. Il pourra consulter la fiche sans compte.</DialogDescription>
          </DialogHeader>
          <div className="flex gap-2">
            <Input readOnly value={shareUrl || ""} className="rounded-sm num text-xs" data-testid="calc-share-url" />
            <Button variant="outline" className="rounded-sm gap-1 shrink-0" data-testid="calc-share-copy"
              onClick={() => { navigator.clipboard?.writeText(shareUrl); toast.success("Lien copié"); }}>
              <Copy className="h-4 w-4" /> Copier
            </Button>
          </div>
          {shareUrl && (
            <div className="flex flex-col items-center gap-2 py-2" data-testid="calc-share-qr">
              <img src={`${process.env.REACT_APP_BACKEND_URL}/api/qr?data=${encodeURIComponent(shareUrl)}`}
                   alt="QR code de la fiche" width="150" height="150"
                   className="rounded-md bg-white p-2 border border-border" />
              <p className="text-xs text-muted-foreground">Scannez pour ouvrir la fiche sur le chantier</p>
            </div>
          )}
          <div className="grid grid-cols-2 gap-2 mt-1">
            <a href={`sms:?&body=${encodeURIComponent(`Votre fiche de calcul ConstruPilot : ${shareUrl}`)}`}
               data-testid="calc-share-sms">
              <Button variant="outline" className="w-full rounded-sm gap-2"><MessageSquare className="h-4 w-4" /> SMS</Button>
            </a>
            <a href={`mailto:?subject=${encodeURIComponent("Votre fiche de calcul — ConstruPilot")}&body=${encodeURIComponent(`Bonjour,\n\nVoici votre fiche de calcul détaillée : ${shareUrl}\n\nCordialement.`)}`}
               data-testid="calc-share-email">
              <Button variant="outline" className="w-full rounded-sm gap-2"><Mail className="h-4 w-4" /> E-mail</Button>
            </a>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
