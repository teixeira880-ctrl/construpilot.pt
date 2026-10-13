import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Library, Search, Loader2, Lock, ChevronDown, ChevronUp } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

const LEVELS = [
  { key: "bas", label: "Baixo", desc: "gama económica" },
  { key: "moyen", label: "Médio", desc: "standard" },
  { key: "haut", label: "Alto", desc: "premium" },
];
const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { maximumFractionDigits: 0 }) + " €";

/** Catalogue partagé ConstruPilot (lecture seule) + choix de la gamme de prix.
 *  Visible pour les entreprises Pro Business. */
export default function SharedLibraryPanel() {
  const [level, setLevel] = useState("moyen");
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [q, setQ] = useState("");
  const [loading, setLoading] = useState(true);
  const [locked, setLocked] = useState(false);
  const [open, setOpen] = useState(false);

  const load = async (search = "") => {
    setLoading(true);
    try {
      const { data } = await api.get("/shared-library", { params: { q: search } });
      setItems(data.items || []);
      setTotal(data.total || 0);
      setLevel(data.level || "moyen");
      setLocked(false);
    } catch (e) {
      if (e?.response?.status === 402) setLocked(true);
    } finally { setLoading(false); }
  };
  useEffect(() => { load(); }, []);
  useEffect(() => {
    const id = setTimeout(() => { if (!locked) load(q); }, 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const changeLevel = async (lvl) => {
    setLevel(lvl);
    try {
      await api.put("/shared-library/level", { level: lvl });
      toast.success(`Gama de preços: ${lvl}`);
    } catch { toast.error("Impossível guardar a gama"); }
  };

  const priceForLevel = (it) =>
    level === "bas" ? it.price_low : level === "haut" ? it.price_high : it.price_mid;

  if (locked) {
    return (
      <div className="rounded-sm border border-border bg-muted/30 p-4 flex items-center gap-3" data-testid="shared-lib-locked">
        <Lock className="h-5 w-5 text-muted-foreground shrink-0" />
        <p className="text-sm text-muted-foreground">
          La <b>biblioteca partilhada ConstruPilot</b> (trabalhos com preço baixo/médio/alto) está reservada ao plano <b>Pro Business</b>.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-sm border border-primary/30 bg-primary/[0.03]" data-testid="shared-lib-panel">
      <div className="flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-2">
          <Library className="h-5 w-5 text-primary" />
          <div>
            <p className="font-semibold text-[15px]">Biblioteca partilhada ConstruPilot</p>
            <p className="text-xs text-muted-foreground">{total} trabalhos · preços indicativos usados pela IA</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1">
            <span className="text-xs text-muted-foreground mr-1">A minha gama:</span>
            {LEVELS.map((l) => (
              <button key={l.key} onClick={() => changeLevel(l.key)}
                      data-testid={`shared-lib-level-${l.key}`}
                      className={`rounded-sm px-3 py-1.5 text-xs font-medium transition-colors border ${
                        level === l.key ? "border-primary bg-primary text-white"
                                        : "border-border hover:border-primary/40"}`}>
                {l.label}
              </button>
            ))}
          </div>
          <Button variant="ghost" size="sm" onClick={() => setOpen((v) => !v)}
                  className="rounded-sm gap-1" data-testid="shared-lib-toggle">
            {open ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
            {open ? "Ocultar" : "Consultar"}
          </Button>
        </div>
      </div>

      {open && (
        <div className="border-t border-border p-4 space-y-3">
          <div className="relative max-w-sm">
            <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)}
                   placeholder="Pesquisar um artigo…" className="rounded-sm pl-9"
                   data-testid="shared-lib-panel-search" />
          </div>
          {loading ? (
            <div className="py-6 text-center"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>
          ) : (
            <div className="max-h-80 overflow-y-auto divide-y divide-border/60">
              {items.length === 0 ? (
                <p className="text-sm text-muted-foreground py-4 text-center">Nenhum trabalho.</p>
              ) : items.map((it) => (
                <div key={it.item_id} className="flex items-center justify-between py-2 gap-3">
                  <div className="min-w-0">
                    <p className="text-sm font-medium truncate">{it.designation}</p>
                    <p className="text-xs text-muted-foreground">{it.category} · {it.unit}</p>
                  </div>
                  <div className="text-right shrink-0">
                    <span className="num font-semibold text-primary">{eur(priceForLevel(it))}</span>
                    <span className="text-xs text-muted-foreground"> /{it.unit}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
          {total > items.length && (
            <p className="text-xs text-muted-foreground">Visualização de {items.length} / {total}. Refine com a pesquisa.</p>
          )}
        </div>
      )}
    </div>
  );
}
