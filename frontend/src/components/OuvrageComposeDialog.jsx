import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Boxes, Search, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";

const LEVELS = ["bas", "moyen", "haut"];

/** Insère un ouvrage composé (bibliothèque paramétrique) chiffré dans le devis. */
export function OuvrageComposeDialog({ onAdd }) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [ouvrages, setOuvrages] = useState([]);
  const [loading, setLoading] = useState(false);
  const [locked, setLocked] = useState(false);
  const [level, setLevel] = useState("moyen");
  const [region, setRegion] = useState("standard");
  const [margin, setMargin] = useState(25);
  const [adding, setAdding] = useState("");

  const load = async (search = "") => {
    setLoading(true);
    try {
      const { data } = await api.get("/param-library/ouvrages", { params: { q: search } });
      setOuvrages(data.ouvrages || []); setLocked(false);
    } catch (e) { if (e?.response?.status === 402) setLocked(true); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (open) load(q); /* eslint-disable-next-line */ }, [open]);
  useEffect(() => {
    if (!open) return;
    const id = setTimeout(() => load(q), 300);
    return () => clearTimeout(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q]);

  const add = async (base_code) => {
    setAdding(base_code);
    try {
      const { data } = await api.post("/param-library/quote-line",
        { base_code, level, region, margin_pct: margin, quantity: 1 });
      onAdd(data.line);
      toast.success(`Ajouté : ${data.line.designation} (${data.line.unit_price_ht} €/${data.line.unit})`);
    } catch { toast.error("Impossible d'ajouter l'ouvrage"); }
    finally { setAdding(""); }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" variant="outline" className="rounded-sm gap-1 text-primary border-primary/40"
                data-testid="editor-add-ouvrage">
          <Boxes className="h-3.5 w-3.5" /> Ouvrage composé
        </Button>
      </DialogTrigger>
      <DialogContent className="rounded-sm max-w-2xl max-h-[86vh] overflow-y-auto" data-testid="ouvrage-compose-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Boxes className="h-5 w-5 text-primary" /> Insérer un ouvrage composé</DialogTitle>
        </DialogHeader>
        {locked ? (
          <p className="text-sm text-muted-foreground py-6 text-center">
            Les ouvrages composés (déboursé sec + marge) sont réservés au plan <b>Pro Business</b>.
          </p>
        ) : (
          <>
            <div className="flex flex-wrap gap-3 items-center text-xs">
              <div className="flex gap-1">Gamme :{LEVELS.map((l) => (
                <button key={l} onClick={() => setLevel(l)} className={`rounded-sm px-2 py-1 border capitalize ${level === l ? "border-primary bg-primary text-white" : "border-input"}`}>{l}</button>))}</div>
              <div className="flex gap-1 items-center">Région :
                <select value={region} onChange={(e) => setRegion(e.target.value)} className="rounded-sm border border-input bg-background px-2 py-1">
                  <option value="idf">Île-de-France</option><option value="grandes_villes">Grandes villes</option>
                  <option value="standard">Standard</option><option value="rural">Rural</option>
                </select></div>
              <div className="flex items-center gap-1">Marge :
                <input type="number" value={margin} onChange={(e) => setMargin(Number(e.target.value) || 0)} className="w-14 rounded-sm border border-input bg-background px-2 py-1 text-right num" />%</div>
            </div>
            <div className="relative">
              <Search className="h-4 w-4 absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un ouvrage…"
                     className="rounded-sm pl-9" data-testid="ouvrage-search" />
            </div>
            <div className="max-h-96 overflow-y-auto divide-y divide-border/60">
              {loading ? <div className="py-6 text-center"><Loader2 className="h-5 w-5 animate-spin mx-auto" /></div>
                : ouvrages.length === 0 ? <p className="text-sm text-muted-foreground py-4 text-center">Aucun ouvrage.</p>
                : ouvrages.map((o) => (
                  <div key={o.base_code} className="flex items-center justify-between py-2 gap-3">
                    <div className="min-w-0">
                      <p className="text-sm font-medium truncate">{o.famille}</p>
                      <p className="text-xs text-muted-foreground">{o.base_code} · {o.metier_mo} · {o.lines} composants</p>
                    </div>
                    <Button size="sm" onClick={() => add(o.base_code)} disabled={!!adding}
                            className="rounded-sm gap-1 h-8 shrink-0" data-testid={`ouvrage-add-${o.base_code}`}>
                      {adding === o.base_code ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />} Ajouter
                    </Button>
                  </div>
                ))}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

export default OuvrageComposeDialog;
