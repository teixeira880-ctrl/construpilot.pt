import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Loader2, Copy, Wand2, Merge } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { api } from "@/lib/api";

const SRC = { starter: "Catalogue", devis: "Devis", dpgf: "DPGF", import_devis: "Imports", manual: "Saisie" };
const eur = (n) => (Number(n) || 0).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " €";

export default function LibraryDuplicatesDialog({ open, onClose, onDone }) {
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [keep, setKeep] = useState({});
  const [busy, setBusy] = useState(false);

  const load = async () => {
    setLoading(true);
    try {
      const { data } = await api.get("/library/duplicates");
      setData(data);
      const def = {};
      (data.groups || []).forEach((g) => { def[g.key] = g.items[0]?.item_id; });
      setKeep(def);
    } catch { toast.error("Impossible de charger les doublons"); }
    finally { setLoading(false); }
  };
  useEffect(() => { if (open) load(); }, [open]);

  const mergeGroup = async (g) => {
    const keep_id = keep[g.key];
    if (!keep_id) return;
    setBusy(true);
    try {
      await api.post("/library/merge", { keep_id, remove_ids: g.items.map((i) => i.item_id).filter((id) => id !== keep_id) });
      toast.success("Doublons fusionnés");
      await load(); onDone?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Fusion impossible"); }
    finally { setBusy(false); }
  };

  const mergeAll = async () => {
    if (!window.confirm("Fusionner tous les doublons ? Le poste le plus récent de chaque groupe est conservé.")) return;
    setBusy(true);
    try {
      const { data } = await api.post("/library/merge-all");
      toast.success(`${data.removed} doublon(s) supprimé(s)`);
      await load(); onDone?.();
    } catch (e) { toast.error(e?.response?.data?.detail || "Fusion impossible"); }
    finally { setBusy(false); }
  };

  const groups = data?.groups || [];

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-w-2xl" data-testid="library-duplicates-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2"><Copy className="h-4 w-4 text-primary" /> Nettoyage des doublons</DialogTitle>
          <DialogDescription>
            Postes très proches (même désignation + unité) provenant de vos devis, DPGF ou saisies.
            Choisissez celui à conserver, les autres sont supprimés.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="py-10 text-center text-sm text-muted-foreground"><Loader2 className="h-5 w-5 animate-spin mx-auto mb-2" /> Analyse…</div>
        ) : groups.length === 0 ? (
          <div className="py-10 text-center space-y-1" data-testid="library-duplicates-empty">
            <p className="font-display font-bold">Aucun doublon détecté</p>
            <p className="text-sm text-muted-foreground">Votre bibliothèque est déjà propre.</p>
          </div>
        ) : (
          <div className="grid gap-3 max-h-[55vh] overflow-y-auto pr-1">
            <div className="flex items-center justify-between rounded-sm bg-secondary/30 px-3 py-2">
              <p className="text-xs text-muted-foreground">{data.group_count} groupe(s) · {data.duplicate_count} doublon(s) à retirer</p>
              <Button size="sm" onClick={mergeAll} disabled={busy} className="rounded-sm gap-1.5 h-7" data-testid="library-merge-all-btn">
                <Wand2 className="h-3.5 w-3.5" /> Tout fusionner
              </Button>
            </div>
            {groups.map((g) => (
              <div key={g.key} className="rounded-sm border border-border p-3" data-testid={`library-dup-group-${g.key}`}>
                <div className="grid gap-1.5">
                  {g.items.map((it) => (
                    <label key={it.item_id} className="flex items-center gap-2 text-sm cursor-pointer">
                      <input type="radio" name={`keep-${g.key}`} checked={keep[g.key] === it.item_id}
                             onChange={() => setKeep((k) => ({ ...k, [g.key]: it.item_id }))}
                             data-testid={`library-dup-keep-${it.item_id}`} />
                      <span className="font-medium truncate flex-1">{it.designation}</span>
                      <Badge variant="outline" className="rounded-sm text-[10px]">{SRC[it.source] || it.source || "Saisie"}</Badge>
                      <span className="num text-xs text-muted-foreground w-14 text-right">{it.unit}</span>
                      <span className="num font-bold text-xs w-20 text-right">{eur(it.unit_price_ht)}</span>
                    </label>
                  ))}
                </div>
                <div className="flex justify-end mt-2">
                  <Button size="sm" variant="outline" onClick={() => mergeGroup(g)} disabled={busy} className="rounded-sm gap-1.5 h-7 text-xs" data-testid={`library-dup-merge-${g.key}`}>
                    <Merge className="h-3.5 w-3.5" /> Fusionner ce groupe
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} className="rounded-sm">Fermer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
