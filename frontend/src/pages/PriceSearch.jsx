import { useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Search, Bell, MapPin, TrendingDown, TrendingUp, ExternalLink, Clock, Truck,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api, eur2, num } from "@/lib/api";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";
import { PriceHistoryChart } from "@/components/PriceHistoryChart";
import { useAuth } from "@/context/AuthContext";

const SORTS = {
  cheapest: { label: "Moins cher", fn: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9) },
  total: { label: "Prix total livré", fn: (a, b) => (a.price ?? 1e9) + a.shipping - ((b.price ?? 1e9) + b.shipping) },
  fast: { label: "Livraison rapide", fn: (a, b) => a.delivery_days - b.delivery_days },
  rating: { label: "Avis", fn: (a, b) => b.rating - a.rating },
  stock: { label: "Disponibilité", fn: (a, b) => a.stock.localeCompare(b.stock) },
  brand: { label: "Fournisseur (A-Z)", fn: (a, b) => a.supplier.localeCompare(b.supplier) },
};

const SUGGESTIONS = ["BA13 hydrofuge 250 x 120", "carrelage 60x60", "laine de verre 200mm",
  "peinture murale mate", "colle carrelage 25kg", "parquet stratifié"];

export default function PriceSearch() {
  const [query, setQuery] = useState("BA13 hydrofuge 250 x 120");
  const [data, setData] = useState(null);
  const [sort, setSort] = useState("cheapest");
  const [history, setHistory] = useState(null);
  const [stores, setStores] = useState(null);
  const [radius, setRadius] = useState("20");
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState("");
  const { user } = useAuth();

  const search = async (q = query) => {
    if (q.trim().length < 2) return;
    setBusy(true);
    try {
      const { data: res } = await api.post("/prices/search", { query: q, limit: 10 });
      setData(res);
      const { data: h } = await api.get("/prices/history", { params: { query: q } });
      setHistory(h.current ? h : null);
    } catch { toast.error("Recherche impossible"); }
    finally { setBusy(false); }
  };

  useEffect(() => { search("BA13 hydrofuge 250 x 120"); }, []);

  const locate = () => {
    if (!navigator.geolocation) return toast.error("Géolocalisation non disponible");
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const { data: res } = await api.get("/prices/stores", {
          params: { lat: coords.latitude, lng: coords.longitude, radius_km: Number(radius) },
        });
        setStores(res);
      },
      () => toast.error("Autorisation de localisation refusée")
    );
  };

  const createAlert = async () => {
    if (!user) return toast.error("Connectez-vous pour créer une alerte prix");
    if (!target) return toast.error("Indiquez un prix cible");
    await api.post("/prices/alerts", { query, target_price: Number(target), product: query });
    toast.success(`Alerte créée : nous vous avertirons sous ${eur2(Number(target))}`);
    setTarget("");
  };

  const checkAlertsNow = async () => {
    if (!user) return toast.error("Connectez-vous pour vérifier vos alertes");
    try {
      const { data } = await api.post("/prices/alerts/check-now");
      if (data.notified > 0) {
        toast.success(`${data.notified} email(s) d'alerte envoyé(s)`);
      } else {
        toast.info("Aucun matériau surveillé sous son prix cible pour l'instant");
      }
    } catch { toast.error("Vérification impossible"); }
  };

  const rows = data ? [...data.results].sort(SORTS[sort].fn) : [];

  return (
    <div className="grid gap-10">
      <SEO title="Comparateur prix matériaux BTP" description="Comparez les prix des matériaux de construction chez Point.P, Leroy Merlin, Castorama, Brico Dépôt et 6 autres enseignes. Historique 12 mois et alertes prix." keywords="comparateur prix matériaux, prix Point.P, prix Leroy Merlin, prix carrelage, prix placo, prix bois construction" canonical="/prix" />
      <SectionTitle as="h1" over="Navigateur de prix" title="Comparez les prix matériaux en temps réel">
        10 fournisseurs interrogés, frais de livraison et stock inclus. Le connecteur est standardisé :
        les API officielles se branchent sans modifier l'application.
      </SectionTitle>

      <div className="surface p-2 flex flex-col sm:flex-row gap-2">
        <Input
          value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          data-testid="price-search-input"
          placeholder="Ex : BA13 hydrofuge 250 x 120"
          className="border-0 bg-transparent focus-visible:ring-0 h-11 text-base"
        />
        <Button onClick={() => search()} disabled={busy} data-testid="price-search-btn" className="rounded-sm gap-2 h-11 hover:bg-orange-600 hover:text-white">
          <Search className="h-4 w-4" /> {busy ? "Recherche…" : "Comparer"}
        </Button>
      </div>

      <div className="flex flex-wrap gap-2 -mt-6">
        {SUGGESTIONS.map((s) => (
          <button
            key={s} onClick={() => { setQuery(s); search(s); }} data-testid={`suggestion-${s.slice(0, 8)}`}
            className="px-3 py-1.5 text-xs rounded-sm border border-border text-muted-foreground hover:border-primary hover:text-primary transition-colors"
          >
            {s}
          </button>
        ))}
      </div>

      {data && (
        <>
          <div className="flex flex-wrap items-center gap-4">
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger className="rounded-sm w-56" data-testid="sort-select"><SelectValue /></SelectTrigger>
              <SelectContent>
                {Object.entries(SORTS).map(([k, v]) => <SelectItem key={k} value={k}>{v.label}</SelectItem>)}
              </SelectContent>
            </Select>
            <Badge variant="outline" className="rounded-sm" data-testid="price-mode-badge">
              {data.mode === "demo" ? "Données de démonstration" : "Recherche web temps réel"}
            </Badge>
            <span className="num text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" /> Vérifié le {new Date(data.checked_at).toLocaleString("fr-FR")}
            </span>
          </div>

          <div className="surface overflow-x-auto">
            <Table data-testid="price-results-table">
              <TableHeader>
                <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                  <TableHead>Fournisseur</TableHead>
                  <TableHead>Produit</TableHead>
                  <TableHead className="text-right">Prix</TableHead>
                  <TableHead className="text-right">Livraison</TableHead>
                  <TableHead>Stock</TableHead>
                  <TableHead className="text-right">Prix total</TableHead>
                  <TableHead className="text-right">Délai</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rows.map((r, i) => (
                  <TableRow key={`${r.supplier_key}-${i}`} className="even:bg-muted/30" data-testid={`price-row-${r.supplier_key}`}>
                    <TableCell className="font-medium whitespace-nowrap">
                      {r.supplier}
                      {r.sponsored && (
                        <Badge className="ml-2 rounded-sm bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/40 text-[9px] uppercase tracking-wider" title={r.sponsored_disclosure} data-testid={`sponsored-badge-${r.supplier_key}`}>
                          Sponsorisé
                        </Badge>
                      )}
                      {i === 0 && sort === "cheapest" && !r.sponsored && (
                        <Badge className="ml-2 rounded-sm bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-0">Meilleur prix</Badge>
                      )}
                      {r.is_affiliate && (
                        <Badge variant="outline" className="ml-2 rounded-sm text-[9px] uppercase tracking-wider border-primary/30 text-primary" title={r.affiliate_disclosure} data-testid={`affiliate-badge-${r.supplier_key}`}>
                          Lien partenaire
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="max-w-[280px] truncate">{r.product}</TableCell>
                    <TableCell className="num text-right font-semibold">{r.price ? eur2(r.price) : "—"}</TableCell>
                    <TableCell className="num text-right text-muted-foreground">
                      {r.shipping === 0 ? "Offerte" : eur2(r.shipping)}
                    </TableCell>
                    <TableCell className="text-xs">{r.stock}</TableCell>
                    <TableCell className="num text-right text-primary font-semibold">
                      {r.price ? eur2(r.price + r.shipping) : "—"}
                    </TableCell>
                    <TableCell className="num text-right text-xs text-muted-foreground whitespace-nowrap">
                      <Truck className="inline h-3 w-3 mr-1" />{r.delivery_days} j
                    </TableCell>
                    <TableCell>
                      <a href={r.tracking_url || r.url} target="_blank" rel="noreferrer noopener sponsored"
                         onClick={() => {
                           if (r.sponsored) api.post("/sponsored/click", { supplier_key: r.supplier_key, query }).catch(() => {});
                           if (r.is_affiliate) api.post("/affiliate/click", { supplier_key: r.supplier_key, product_url: r.url, query }).catch(() => {});
                         }}
                         data-testid={`price-link-${r.supplier_key}`}>
                        <ExternalLink className="h-4 w-4 text-muted-foreground hover:text-primary transition-colors" />
                      </a>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <PriceHistoryChart query={query} days={90} />

          <div className="grid lg:grid-cols-3 gap-4">
            {history && (
              <div className="surface p-6" data-testid="price-history">
                <p className="overline">Historique des prix</p>
                <div className="mt-4 grid gap-2 text-sm">
                  <p className="flex justify-between"><span className="text-muted-foreground">Prix actuel</span><span className="num font-semibold">{eur2(history.current)}</span></p>
                  <p className="flex justify-between"><span className="text-muted-foreground">Prix moyen observé</span><span className="num">{eur2(history.avg_30d)}</span></p>
                  <p className="flex justify-between"><span className="text-muted-foreground">Meilleur prix observé</span><span className="num text-emerald-500">{eur2(history.best)}</span></p>
                  <p className="flex justify-between">
                    <span className="text-muted-foreground">Évolution</span>
                    <span className={`num font-semibold ${history.evolution_pct <= 0 ? "text-emerald-500" : "text-red-500"}`}>
                      {history.evolution_pct <= 0 ? <TrendingDown className="inline h-3 w-3 mr-1" /> : <TrendingUp className="inline h-3 w-3 mr-1" />}
                      {history.evolution_pct} %
                    </span>
                  </p>
                </div>
              </div>
            )}

            <div className="surface p-6">
              <p className="overline flex items-center gap-2"><Bell className="h-4 w-4" /> Alerte prix</p>
              <p className="mt-3 text-xs text-muted-foreground">
                Nous surveillons ce produit chaque jour. Vous recevez un email dès qu'il passe sous le prix cible.
              </p>
              <div className="mt-4 flex gap-2">
                <Input type="number" placeholder="Prix cible €" value={target} onChange={(e) => setTarget(e.target.value)} data-testid="alert-target-input" className="rounded-sm num" />
                <Button variant="outline" onClick={createAlert} data-testid="create-alert-btn" className="rounded-sm">Créer</Button>
              </div>
              <Button variant="ghost" size="sm" onClick={checkAlertsNow} data-testid="check-alerts-now-btn" className="mt-3 rounded-sm gap-2 w-full text-xs">
                <Bell className="h-3 w-3" /> Vérifier mes alertes maintenant
              </Button>
            </div>

            <div className="surface p-6">
              <p className="overline flex items-center gap-2"><MapPin className="h-4 w-4" /> Matériaux autour de moi</p>
              <div className="mt-4 flex gap-2">
                <Select value={radius} onValueChange={setRadius}>
                  <SelectTrigger className="rounded-sm" data-testid="radius-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["5", "10", "20", "50"].map((r) => <SelectItem key={r} value={r}>{r} km</SelectItem>)}
                  </SelectContent>
                </Select>
                <Button variant="outline" onClick={locate} data-testid="locate-btn" className="rounded-sm whitespace-nowrap">Me localiser</Button>
              </div>
              {stores && (
                <div className="mt-4 grid gap-2 max-h-52 overflow-y-auto" data-testid="stores-list">
                  {stores.stores.map((s, i) => (
                    <div key={i} className="flex items-center justify-between text-xs border-b border-border pb-2">
                      <span>{s.name}</span>
                      <span className="num text-muted-foreground">{s.distance_km} km {s.open_now ? "· ouvert" : ""}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            {data.mode === "demo"
              ? "Mode démonstration : les prix proviennent du connecteur de démonstration ConstruPilot (clairement identifiés comme tels). Ajoutez une clé de recherche web ou les API fournisseurs pour des prix réels."
              : "Prix indicatifs issus d'une recherche web : vérifiez toujours le prix final sur la page du marchand."}
          </p>
        </>
      )}
    </div>
  );
}
