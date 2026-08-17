import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Plus, Trash2, ClipboardList, CheckCircle2, Circle, AlertTriangle, Lock, HardHat } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useBilling } from "@/context/BillingContext";
import { SectionTitle } from "@/components/Bits";

export default function SiteTracking() {
  const navigate = useNavigate();
  const { has } = useBilling();
  const allowed = has("site_tracking");
  const [project, setProject] = useState("");
  const [reports, setReports] = useState([]);
  const [reserves, setReserves] = useState([]);
  const [checklist, setChecklist] = useState([]);
  const [rep, setRep] = useState({ title: "", notes: "" });
  const [res, setRes] = useState({ lot: "", description: "", company: "" });
  const [ck, setCk] = useState({ lot: "", label: "" });

  const load = () => {
    const p = project ? `?project=${encodeURIComponent(project)}` : "";
    api.get(`/site/reports${p}`).then(({ data }) => setReports(data)).catch(() => {});
    api.get(`/site/reserves${p}`).then(({ data }) => setReserves(data)).catch(() => {});
    api.get(`/site/checklist${p}`).then(({ data }) => setChecklist(data)).catch(() => {});
  };
  useEffect(() => { if (allowed) load(); /* eslint-disable-next-line */ }, [project, allowed]);

  if (!allowed) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-24 text-center" data-testid="site-locked">
        <div className="h-14 w-14 rounded-xl bg-primary/10 grid place-items-center mx-auto mb-5"><Lock className="h-7 w-7 text-primary" /></div>
        <h1 className="font-display text-3xl font-bold">Suivi de chantier</h1>
        <p className="text-muted-foreground mt-3">Comptes-rendus, réserves et checklists d'avancement — réservé au <b>pack Business</b>.</p>
        <Button className="rounded-sm mt-6" onClick={() => navigate("/tarifs")} data-testid="site-upgrade-btn">Passer au pack Business</Button>
      </div>
    );
  }

  const need = () => { if (!project.trim()) { toast.error("Indiquez d'abord un nom de chantier"); return false; } return true; };

  const addReport = async () => {
    if (!need()) return;
    await api.post("/site/reports", { project, title: rep.title, notes: rep.notes });
    setRep({ title: "", notes: "" }); toast.success("Compte-rendu ajouté"); load();
  };
  const addReserve = async () => {
    if (!need() || !res.description.trim()) return toast.error("Description requise");
    await api.post("/site/reserves", { project, ...res });
    setRes({ lot: "", description: "", company: "" }); toast.success("Réserve créée"); load();
  };
  const addCk = async () => {
    if (!need() || !ck.label.trim()) return toast.error("Libellé requis");
    await api.post("/site/checklist", { project, ...ck });
    setCk({ lot: "", label: "" }); toast.success("Point ajouté"); load();
  };

  const openCount = reserves.filter((r) => r.status !== "lifted").length;
  const ckDone = checklist.filter((c) => c.done).length;
  const ckPct = checklist.length ? Math.round((ckDone / checklist.length) * 100) : 0;

  return (
    <div className="max-w-5xl mx-auto px-6 py-10 space-y-6" data-testid="site-tracking-page">
      <SectionTitle overline="Pack Business" title="Suivi de chantier" />
      <div className="flex items-center gap-3">
        <HardHat className="h-4 w-4 text-primary" />
        <Input value={project} onChange={(e) => setProject(e.target.value)} placeholder="Nom du chantier (ex. Villa Dupont)"
          className="rounded-sm max-w-sm" data-testid="site-project" />
      </div>

      <Tabs defaultValue="reports">
        <TabsList className="rounded-sm">
          <TabsTrigger value="reports" className="rounded-sm gap-2" data-testid="tab-reports"><ClipboardList className="h-4 w-4" /> Comptes-rendus ({reports.length})</TabsTrigger>
          <TabsTrigger value="reserves" className="rounded-sm gap-2" data-testid="tab-reserves"><AlertTriangle className="h-4 w-4" /> Réserves ({openCount})</TabsTrigger>
          <TabsTrigger value="checklist" className="rounded-sm gap-2" data-testid="tab-checklist"><CheckCircle2 className="h-4 w-4" /> Avancement ({ckPct}%)</TabsTrigger>
        </TabsList>

        <TabsContent value="reports" className="mt-5 space-y-4">
          <div className="surface p-5 rounded-md grid gap-3">
            <Input value={rep.title} onChange={(e) => setRep({ ...rep, title: e.target.value })} placeholder="Titre / date de visite" className="rounded-sm" data-testid="report-title" />
            <Textarea value={rep.notes} onChange={(e) => setRep({ ...rep, notes: e.target.value })} placeholder="Observations, avancement, points bloquants…" rows={3} className="rounded-sm" data-testid="report-notes" />
            <Button onClick={addReport} className="rounded-sm gap-2 w-fit" data-testid="report-add"><Plus className="h-4 w-4" /> Ajouter le compte-rendu</Button>
          </div>
          {reports.map((r) => (
            <div key={r.report_id} className="surface p-4 rounded-md flex justify-between gap-4" data-testid={`report-${r.report_id}`}>
              <div><p className="font-display font-semibold">{r.title || "Visite"}</p><p className="text-sm text-muted-foreground whitespace-pre-wrap mt-1">{r.notes}</p><p className="text-xs text-muted-foreground mt-2">{new Date(r.created_at).toLocaleDateString("fr-FR")}</p></div>
              <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500 shrink-0" onClick={() => api.delete(`/site/reports/${r.report_id}`).then(load)} data-testid={`report-del-${r.report_id}`}><Trash2 className="h-4 w-4" /></Button>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="reserves" className="mt-5 space-y-4">
          <div className="surface p-5 rounded-md grid gap-3 md:grid-cols-4 items-end">
            <Input value={res.lot} onChange={(e) => setRes({ ...res, lot: e.target.value })} placeholder="Lot (ex. Plomberie)" className="rounded-sm" data-testid="reserve-lot" />
            <Input value={res.description} onChange={(e) => setRes({ ...res, description: e.target.value })} placeholder="Description de la réserve" className="rounded-sm md:col-span-2" data-testid="reserve-desc" />
            <Input value={res.company} onChange={(e) => setRes({ ...res, company: e.target.value })} placeholder="Entreprise" className="rounded-sm" data-testid="reserve-company" />
            <Button onClick={addReserve} className="rounded-sm gap-2 w-fit md:col-span-4" data-testid="reserve-add"><Plus className="h-4 w-4" /> Créer la réserve</Button>
          </div>
          {reserves.map((r) => (
            <div key={r.reserve_id} className="surface p-4 rounded-md flex items-center justify-between gap-4" data-testid={`reserve-${r.reserve_id}`}>
              <div className="flex items-center gap-3">
                <button onClick={() => api.patch(`/site/reserves/${r.reserve_id}`).then(load)} data-testid={`reserve-toggle-${r.reserve_id}`}>
                  {r.status === "lifted" ? <CheckCircle2 className="h-5 w-5 text-emerald-500" /> : <Circle className="h-5 w-5 text-amber-500" />}
                </button>
                <div>
                  <p className={`font-medium ${r.status === "lifted" ? "line-through text-muted-foreground" : ""}`}>{r.description}</p>
                  <p className="text-xs text-muted-foreground">{[r.lot, r.company].filter(Boolean).join(" · ") || "—"}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Badge variant={r.status === "lifted" ? "secondary" : "default"}>{r.status === "lifted" ? "Levée" : "En cours"}</Badge>
                <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => api.delete(`/site/reserves/${r.reserve_id}`).then(load)} data-testid={`reserve-del-${r.reserve_id}`}><Trash2 className="h-4 w-4" /></Button>
              </div>
            </div>
          ))}
        </TabsContent>

        <TabsContent value="checklist" className="mt-5 space-y-4">
          <div className="surface p-4 rounded-md">
            <div className="flex justify-between text-sm mb-2"><span className="text-muted-foreground">Avancement global</span><span className="num font-bold text-primary">{ckPct}%</span></div>
            <div className="h-2.5 rounded-full bg-muted overflow-hidden"><div className="h-full bg-primary transition-all" style={{ width: `${ckPct}%` }} /></div>
          </div>
          <div className="surface p-5 rounded-md grid gap-3 md:grid-cols-3 items-end">
            <Input value={ck.lot} onChange={(e) => setCk({ ...ck, lot: e.target.value })} placeholder="Lot" className="rounded-sm" data-testid="ck-lot" />
            <Input value={ck.label} onChange={(e) => setCk({ ...ck, label: e.target.value })} placeholder="Point à contrôler" className="rounded-sm" data-testid="ck-label" />
            <Button onClick={addCk} className="rounded-sm gap-2 w-fit" data-testid="ck-add"><Plus className="h-4 w-4" /> Ajouter</Button>
          </div>
          {checklist.map((c) => (
            <div key={c.item_id} className="surface p-3 px-4 rounded-md flex items-center justify-between gap-3" data-testid={`ck-${c.item_id}`}>
              <button className="flex items-center gap-3 text-left flex-1" onClick={() => api.patch(`/site/checklist/${c.item_id}`).then(load)} data-testid={`ck-toggle-${c.item_id}`}>
                {c.done ? <CheckCircle2 className="h-5 w-5 text-emerald-500" /> : <Circle className="h-5 w-5 text-muted-foreground" />}
                <span className={c.done ? "line-through text-muted-foreground" : ""}>{c.label} {c.lot && <span className="text-xs text-muted-foreground">· {c.lot}</span>}</span>
              </button>
              <Button size="icon" variant="ghost" className="h-8 w-8 text-red-500" onClick={() => api.delete(`/site/checklist/${c.item_id}`).then(load)} data-testid={`ck-del-${c.item_id}`}><Trash2 className="h-4 w-4" /></Button>
            </div>
          ))}
        </TabsContent>
      </Tabs>
    </div>
  );
}
