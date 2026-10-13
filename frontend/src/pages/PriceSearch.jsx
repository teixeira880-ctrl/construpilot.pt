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
  cheapest: { label: "Mais barato", fn: (a, b) => (a.price ?? 1e9) - (b.price ?? 1e9) },
  total: { label: "Preço total entregue", fn: (a, b) => (a.price ?? 1e9) + a.shipping - ((b.price ?? 1e9) + b.shipping) },
  fast: { label: "Entrega rápida", fn: (a, b) => a.delivery_days - b.delivery_days },
  rating: { label: "Avaliações", fn: (a, b) => b.rating - a.rating },
  stock: { label: "Disponibilidade", fn: (a, b) => a.stock.localeCompare(b.stock) },
  brand: { label: "Fornecedor (A-Z)", fn: (a, b) => a.supplier.localeCompare(b.supplier) },
};

const SUGGESTIONS = ["BA13 hidrófugo 250 x 120", "mosaico 60x60", "lã de vidro 200mm",
  "tinta mural mate", "cola azulejo 25kg", "soalho laminado"];

function relativeAge(iso) {
  if (!iso) return null;
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (Number.isNaN(diff) || diff < 0) return null;
  if (diff < 60) return "agora mesmo";
  if (diff < 3600) return `há ${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `há ${Math.floor(diff / 3600)} h`;
  return `há ${Math.floor(diff / 86400)} j`;
}

export default function PriceSearch() {
  const [query, setQuery] = useState("BA13 hidrófugo 250 x 120");
  const [data, setData] = useState(null);
  const [sort, setSort] = useState("cheapest");
  const [history, setHistory] = useState(null);
  const [stores, setStores] = useState(null);
  const [radius, setRadius] = useState("20");
  const [busy, setBusy] = useState(false);
  const [target, setTarget] = useState("");
  const [smsChannel, setSmsChannel] = useState(false);
  const [smsPhone, setSmsPhone] = useState("");
  // Batch d'estimations depuis Smart Project (fix bug "Comparer prix matériaux")
  const [estimationBatch, setEstimationBatch] = useState(null);
  const { user } = useAuth();

  const search = async (q = query) => {
    if (q.trim().length < 2) return;
    setQuery(q);
    setBusy(true);
    try {
      const { data: res } = await api.post("/prices/search", { query: q, limit: 10 });
      setData(res);
      const { data: h } = await api.get("/prices/history", { params: { query: q } });
      setHistory(h.current ? h : null);
    } catch { toast.error("Pesquisa impossível"); }
    finally { setBusy(false); }
  };

  useEffect(() => {
    // Récupère le batch de Smart Project s'il existe (moins de 30 min)
    const raw = sessionStorage.getItem("construpilot_price_search_batch");
    if (raw) {
      try {
        const batch = JSON.parse(raw);
        if (batch.ts && Date.now() - batch.ts < 30 * 60 * 1000) {
          setEstimationBatch(batch);
          // Lance la première recherche automatiquement sur le 1er item
          if (batch.items?.length > 0) {
            search(batch.items[0].search || batch.items[0].name);
            return;
          }
        }
      } catch { /* ignore */ }
    }
    search("BA13 hidrófugo 250 x 120");
    // eslint-disable-next-line
  }, []);

  const locate = () => {
    if (!navigator.geolocation) return toast.error("Geolocalização não disponível");
    navigator.geolocation.getCurrentPosition(
      async ({ coords }) => {
        const { data: res } = await api.get("/prices/stores", {
          params: { lat: coords.latitude, lng: coords.longitude, radius_km: Number(radius) },
        });
        setStores(res);
      },
      () => toast.error("Autorização de localização recusada")
    );
  };

  const createAlert = async () => {
    if (!user) return toast.error("Inicie sessão para criar um alerta de preço");
    if (!target) return toast.error("Indique um preço alvo");
    const channels = ["email"];
    if (smsChannel) {
      if (!smsPhone || !smsPhone.trim().startsWith("+")) {
        return toast.error("Número obrigatório para SMS (formato +33…)");
      }
      channels.push("sms");
    }
    try {
      await api.post("/prices/alerts", {
        query, target_price: Number(target), product: query,
        channels, phone: smsChannel ? smsPhone.trim() : null,
      });
      const canaux = smsChannel ? "email + SMS" : "email";
      toast.success(`Alerta criado: ${canaux} assim que ${eur2(Number(target))} atteint`);
      setTarget("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Criação impossível");
    }
  };

  const checkAlertsNow = async () => {
    if (!user) return toast.error("Inicie sessão para verificar os seus alertas");
    try {
      const { data } = await api.post("/prices/alerts/check-now");
      if (data.notified > 0) {
        toast.success(`${data.notified} e-mail(s) de alerta enviado(s)`);
      } else {
        toast.info("Nenhum material monitorizado abaixo do seu preço-alvo de momento");
      }
    } catch { toast.error("Verificação impossível"); }
  };

  const rows = data ? [...data.results].sort(SORTS[sort].fn) : [];

  return (
    <div className="grid gap-10">
      <SEO title="Comparador preços materiais construção" description="Compare os preços dos materiais de construção na Point.P, Leroy Merlin, Castorama, Brico Dépôt e 6 outras insígnias. Histórico 12 meses e alertas de preço." keywords="comparador preços materiais, preço Leroy Merlin, preço Maxmat, preço azulejo, preço pladur, preço madeira construção" canonical="/prix" />
      <SectionTitle as="h1" over="Navegador de preços" title="Compare os preços materiais em tempo real">
        10 fornecedores consultados, portes e stock incluídos. O conector é normalizado: as API oficiais ligam-se sem modificar a aplicação.
      </SectionTitle>

      <div className="surface p-2 flex flex-col sm:flex-row gap-2">
        <Input
          value={query} onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && search()}
          data-testid="price-search-input"
          placeholder="Ex: BA13 hidrófugo 250 x 120"
          className="border-0 bg-transparent focus-visible:ring-0 h-11 text-base"
        />
        <Button onClick={() => search()} disabled={busy} data-testid="price-search-btn" className="rounded-sm gap-2 h-11 hover:bg-orange-600 hover:text-white">
          <Search className="h-4 w-4" /> {busy ? "A pesquisar…" : "Comparar"}
        </Button>
      </div>

      {estimationBatch && estimationBatch.items?.length > 0 && (
        <div className="surface p-5 border-primary/40 -mt-6" data-testid="estimation-batch-panel">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div>
              <p className="overline">Materiais da sua estimativa</p>
              <p className="text-sm mt-1">
                <span className="font-medium">{estimationBatch.project_name}</span>
                {estimationBatch.total_avg > 0 && (
                  <span className="text-muted-foreground"> · Orçamento médio <span className="num">{eur2(estimationBatch.total_avg)}</span></span>
                )}
              </p>
            </div>
            <button
              onClick={() => { sessionStorage.removeItem("construpilot_price_search_batch"); setEstimationBatch(null); }}
              data-testid="estimation-batch-clear"
              className="text-xs text-muted-foreground hover:text-destructive underline-offset-2 hover:underline"
            >
              Apagar esta especialidade
            </button>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            {estimationBatch.items.slice(0, 12).map((it, i) => {
              const q = it.search || it.name;
              return (
                <button
                  key={i}
                  onClick={() => search(q)}
                  data-testid={`batch-item-${i}`}
                  className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-sm border text-xs transition-colors ${
                    query === q ? "border-primary bg-primary/10 text-primary" : "border-border hover:border-primary"
                  }`}
                  title={`${it.quantity} ${it.unit} — ${it.name}`}
                >
                  <span className="font-medium">{it.name}</span>
                  <Badge variant="outline" className="text-[10px] rounded-sm num shrink-0">
                    {it.quantity} {it.unit}
                  </Badge>
                </button>
              );
            })}
            {estimationBatch.items.length > 12 && (
              <span className="text-xs text-muted-foreground self-center">
                + {estimationBatch.items.length - 12} outros…
              </span>
            )}
          </div>
        </div>
      )}

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
              {data.mode === "demo" ? "Dados de demonstração" : "Pesquisa web em tempo real"}
            </Badge>
            <span className="num text-xs text-muted-foreground flex items-center gap-1">
              <Clock className="h-3 w-3" /> Verificado a {new Date(data.checked_at).toLocaleString("pt-PT")}
            </span>
          </div>

          <div className="surface overflow-x-auto">
            <Table data-testid="price-results-table">
              <TableHeader>
                <TableRow className="bg-secondary/60 hover:bg-secondary/60">
                  <TableHead>Fornecedor</TableHead>
                  <TableHead>Produto</TableHead>
                  <TableHead className="text-right">Preço</TableHead>
                  <TableHead className="text-right">Entrega</TableHead>
                  <TableHead>Stock</TableHead>
                  <TableHead className="text-right">Preço total</TableHead>
                  <TableHead className="text-right">Prazo</TableHead>
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
                          Patrocinado
                        </Badge>
                      )}
                      {i === 0 && sort === "cheapest" && !r.sponsored && (
                        <Badge className="ml-2 rounded-sm bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-0">Melhor preço</Badge>
                      )}
                      {r.is_affiliate && (
                        <Badge variant="outline" className="ml-2 rounded-sm text-[9px] uppercase tracking-wider border-primary/30 text-primary" title={r.affiliate_disclosure} data-testid={`affiliate-badge-${r.supplier_key}`}>
                          Ligação de parceiro
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="max-w-[280px] truncate">
                      {r.product}
                      {r.checked_at && (
                        <span className="ml-2 text-[10px] text-muted-foreground align-middle"
                              title={`Verificado a ${new Date(r.checked_at).toLocaleString("pt-PT")}`}
                              data-testid={`price-freshness-${r.supplier_key}`}>
                          · {relativeAge(r.checked_at)}
                        </span>
                      )}
                    </TableCell>
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
                <p className="overline">Histórico dos preços</p>
                <div className="mt-4 grid gap-2 text-sm">
                  <p className="flex justify-between"><span className="text-muted-foreground">Preço atual</span><span className="num font-semibold">{eur2(history.current)}</span></p>
                  <p className="flex justify-between"><span className="text-muted-foreground">Preço médio observado</span><span className="num">{eur2(history.avg_30d)}</span></p>
                  <p className="flex justify-between"><span className="text-muted-foreground">Melhor preço observado</span><span className="num text-emerald-500">{eur2(history.best)}</span></p>
                  <p className="flex justify-between">
                    <span className="text-muted-foreground">Evolução</span>
                    <span className={`num font-semibold ${history.evolution_pct <= 0 ? "text-emerald-500" : "text-red-500"}`}>
                      {history.evolution_pct <= 0 ? <TrendingDown className="inline h-3 w-3 mr-1" /> : <TrendingUp className="inline h-3 w-3 mr-1" />}
                      {history.evolution_pct} %
                    </span>
                  </p>
                </div>
              </div>
            )}

            <div className="surface p-6">
              <p className="overline flex items-center gap-2"><Bell className="h-4 w-4" /> Alerta preço</p>
              <p className="mt-3 text-xs text-muted-foreground">
                Monitorizamos este produto todos os dias. Recebe um email assim que fica abaixo do preço alvo.
              </p>
              <div className="mt-4 flex gap-2">
                <Input type="number" placeholder="Preço alvo €" value={target} onChange={(e) => setTarget(e.target.value)} data-testid="alert-target-input" className="rounded-sm num" />
                <Button variant="outline" onClick={createAlert} data-testid="create-alert-btn" className="rounded-sm">Criar</Button>
              </div>
              <label className="mt-3 flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
                <input
                  type="checkbox"
                  checked={smsChannel}
                  onChange={(e) => setSmsChannel(e.target.checked)}
                  data-testid="alert-sms-toggle"
                  className="accent-primary h-3.5 w-3.5"
                />
                Também por SMS
              </label>
              {smsChannel && (
                <Input
                  type="tel"
                  placeholder="+33612345678"
                  value={smsPhone}
                  onChange={(e) => setSmsPhone(e.target.value)}
                  data-testid="alert-sms-phone"
                  className="mt-2 rounded-sm num h-9 text-xs"
                />
              )}
              <Button variant="ghost" size="sm" onClick={checkAlertsNow} data-testid="check-alerts-now-btn" className="mt-3 rounded-sm gap-2 w-full text-xs">
                <Bell className="h-3 w-3" /> Verificar os meus alertas agora
              </Button>
            </div>

            <div className="surface p-6">
              <p className="overline flex items-center gap-2"><MapPin className="h-4 w-4" /> Materiais perto de mim</p>
              <div className="mt-4 flex gap-2">
                <Select value={radius} onValueChange={setRadius}>
                  <SelectTrigger className="rounded-sm" data-testid="radius-select"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {["5", "10", "20", "50"].map((r) => <SelectItem key={r} value={r}>{r} km</SelectItem>)}
                  </SelectContent>
                </Select>
                <Button variant="outline" onClick={locate} data-testid="locate-btn" className="rounded-sm whitespace-nowrap">Localizar-me</Button>
              </div>
              {stores && (
                <div className="mt-4 grid gap-2 max-h-52 overflow-y-auto" data-testid="stores-list">
                  {stores.stores.map((s, i) => (
                    <div key={i} className="flex items-center justify-between text-xs border-b border-border pb-2">
                      <span>{s.name}</span>
                      <span className="num text-muted-foreground">{s.distance_km} km {s.open_now ? "· aberto" : ""}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            {data.mode === "demo"
              ? "Modo demonstração: os preços provêm do conector de demonstração ConstruPilot (claramente identificados como tal). Adicione uma chave de pesquisa web ou as API de fornecedores para preços reais."
              : "Preços indicativos obtidos de uma pesquisa web: verifique sempre o preço final na página do comerciante."}
          </p>
        </>
      )}
    </div>
  );
}
