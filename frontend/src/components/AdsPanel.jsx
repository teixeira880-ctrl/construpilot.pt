import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Plus, Megaphone, Trash2, Loader2 } from "lucide-react";
import { api, eur, num } from "@/lib/api";
import { SectionTitle, Stat } from "@/components/Bits";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "@/components/ui/alert-dialog";

const PLATFORMS = ["google", "meta", "instagram", "linkedin", "tiktok", "other"];
const EMPTY = { name: "", platform: "google", budget: "", spend: "", leads: "", revenue: "", status: "active" };

export default function AdsPanel() {
  const [rows, setRows] = useState([]);
  const [sum, setSum] = useState(null);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [saving, setSaving] = useState(false);
  const [toDelete, setToDelete] = useState(null);

  const load = () => {
    api.get("/ads/campaigns").then(({ data }) => setRows(data));
    api.get("/ads/summary").then(({ data }) => setSum(data));
  };
  useEffect(() => { load(); }, []);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const save = async () => {
    if (!form.name.trim()) return toast.error("Nom requis");
    setSaving(true);
    try {
      await api.post("/ads/campaigns", {
        name: form.name, platform: form.platform, status: form.status,
        budget: Number(form.budget) || 0, spend: Number(form.spend) || 0,
        leads: Number(form.leads) || 0, revenue: Number(form.revenue) || 0,
      });
      toast.success("Campagne ajoutée"); setOpen(false); setForm(EMPTY); load();
    } catch { toast.error("Erreur"); } finally { setSaving(false); }
  };
  const del = async () => {
    if (!toDelete) return;
    await api.delete(`/ads/campaigns/${toDelete.campaign_id}`); toast.success("Supprimée"); setToDelete(null); load();
  };

  return (
    <div className="grid gap-6" data-testid="ads-panel">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <SectionTitle over="Marketing" title="Publicité & acquisition">
          Suivez vos campagnes publicitaires : dépenses, leads générés, coût par lead et ROI.
        </SectionTitle>
        <Button onClick={() => setOpen(true)} className="rounded-sm gap-2" data-testid="ads-new-btn">
          <Plus className="h-4 w-4" /> Nouvelle campagne
        </Button>
      </div>

      {sum && (
        <div className="grid grid-cols-2 lg:grid-cols-5 gap-3" data-testid="ads-kpis">
          <Stat label="Dépense totale" value={eur(sum.total_spend)} />
          <Stat label="Budget" value={eur(sum.total_budget)} />
          <Stat label="Leads" value={num(sum.total_leads)} accent />
          <Stat label="Coût / lead" value={sum.cpl != null ? eur(sum.cpl) : "—"} />
          <Stat label="ROAS" value={sum.roas != null ? `${sum.roas}×` : "—"} accent />
        </div>
      )}

      {rows.length === 0 ? (
        <div className="surface p-10 text-center space-y-2" data-testid="ads-empty">
          <Megaphone className="h-8 w-8 mx-auto text-muted-foreground" />
          <p className="text-sm text-muted-foreground">Aucune campagne. Ajoutez votre première campagne publicitaire.</p>
        </div>
      ) : (
        <div className="grid gap-2" data-testid="ads-list">
          {rows.map((c) => {
            const cpl = c.leads ? c.spend / c.leads : null;
            return (
              <div key={c.campaign_id} className="surface p-4 rounded-sm flex flex-wrap items-center gap-3" data-testid={`ads-row-${c.campaign_id}`}>
                <div className="min-w-0 flex-1">
                  <p className="font-display font-semibold">{c.name}</p>
                  <p className="text-xs text-muted-foreground uppercase tracking-wide">{c.platform} · {c.status}</p>
                </div>
                <div className="text-right text-sm"><span className="text-muted-foreground text-xs">Dépense</span><br /><span className="num font-bold">{eur(c.spend)}</span></div>
                <div className="text-right text-sm"><span className="text-muted-foreground text-xs">Leads</span><br /><span className="num font-bold">{num(c.leads)}</span></div>
                <div className="text-right text-sm"><span className="text-muted-foreground text-xs">CPL</span><br /><span className="num font-bold text-primary">{cpl != null ? eur(cpl) : "—"}</span></div>
                <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => setToDelete(c)} data-testid={`ads-del-${c.campaign_id}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
            );
          })}
        </div>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>Nouvelle campagne</DialogTitle>
            <DialogDescription>Renseignez la dépense et les leads pour calculer le coût par lead.</DialogDescription>
          </DialogHeader>
          <div className="grid gap-3">
            <div><Label>Nom</Label><Input value={form.name} onChange={set("name")} className="rounded-sm mt-1" data-testid="ads-name" /></div>
            <div><Label>Plateforme</Label>
              <select value={form.platform} onChange={set("platform")} data-testid="ads-platform"
                className="mt-1 w-full rounded-sm border border-border bg-background px-3 py-2 text-sm">
                {PLATFORMS.map((p) => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div><Label>Budget (€)</Label><Input type="number" value={form.budget} onChange={set("budget")} className="rounded-sm mt-1 num" data-testid="ads-budget" /></div>
              <div><Label>Dépense (€)</Label><Input type="number" value={form.spend} onChange={set("spend")} className="rounded-sm mt-1 num" data-testid="ads-spend" /></div>
              <div><Label>Leads</Label><Input type="number" value={form.leads} onChange={set("leads")} className="rounded-sm mt-1 num" data-testid="ads-leads" /></div>
              <div><Label>CA attribué (€)</Label><Input type="number" value={form.revenue} onChange={set("revenue")} className="rounded-sm mt-1 num" data-testid="ads-revenue" /></div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)} className="rounded-sm">Annuler</Button>
            <Button onClick={save} disabled={saving} className="rounded-sm gap-2" data-testid="ads-save">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <AlertDialog open={!!toDelete} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent data-testid="ads-delete-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer la campagne&nbsp;?</AlertDialogTitle>
            <AlertDialogDescription>
              « {toDelete?.name} » sera définitivement supprimée. Cette action est irréversible.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="rounded-sm" data-testid="ads-delete-cancel">Annuler</AlertDialogCancel>
            <AlertDialogAction onClick={del} className="rounded-sm bg-red-600 hover:bg-red-700" data-testid="ads-delete-confirm">Supprimer</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
