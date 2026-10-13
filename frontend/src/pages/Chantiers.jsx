import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { HardHat, Plus, Search, FileText, Ruler, Layers, Wrench, Camera, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { ChantierFormDialog, CHANTIER_STATUS } from "@/components/chantiers/ChantierFormDialog";

const STATUS_CLASS = { prospect: "bg-amber-500/10 text-amber-700 border-amber-500/30", en_cours: "bg-primary/10 text-primary border-primary/30", termine: "bg-emerald-500/10 text-emerald-700 border-emerald-500/30" };

export default function Chantiers() {
  const nav = useNavigate();
  const [items, setItems] = useState([]);
  const [state, setState] = useState("loading");
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("");
  const [open, setOpen] = useState(false);

  const load = useCallback(async () => {
    setState("loading");
    try {
      const { data } = await api.get(`/chantiers?q=${encodeURIComponent(q)}&status=${status}`);
      setItems(data.chantiers || []); setState("ready");
    } catch { setState("error"); }
  }, [q, status]);
  useEffect(() => { const t = setTimeout(load, q ? 250 : 0); return () => clearTimeout(t); }, [load, q]);

  const Count = ({ icon: Icon, n, title, label }) => <span className="inline-flex items-center gap-1 text-xs text-muted-foreground" title={title}><Icon className="h-3.5 w-3.5" />{n}<span className="workspace-count-label">{label}</span></span>;

  return (
    <div className="grid gap-6 workspace-collection" data-testid="chantiers-page">
      <header className="workspace-page-heading">
        <div>
          <h1 className="font-display text-2xl font-bold tracking-tight flex items-center gap-2"><HardHat className="h-6 w-6 text-primary" /> Dossiers chantier</h1>
          <p className="text-sm text-muted-foreground mt-1">Un dossier par affaire : client, plans, métrés, devis, factures et photos réunis — sans ressaisie.</p>
        </div>
        <Button className="gap-2" onClick={() => setOpen(true)} data-testid="chantiers-new-btn"><Plus className="h-4 w-4" /> Nouveau chantier</Button>
      </header>

      <div className="workspace-collection-toolbar">
        <div className="workspace-search-field flex-1 min-w-56"><Search size={17} aria-hidden="true" /><input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Rechercher un chantier, un client, une ville…" aria-label="Rechercher" data-testid="chantiers-search" /></div>
        <div className="workspace-status-filters" role="group" aria-label="Filtrer par statut">
          {[["", "Tous"], ...Object.entries(CHANTIER_STATUS)].map(([v, l]) => (
            <button key={v} type="button" aria-pressed={status === v} onClick={() => setStatus(v)} data-testid={`chantiers-filter-${v || "all"}`}
              className={`px-3 h-9 rounded-md border text-sm transition-colors ${status === v ? "bg-primary text-primary-foreground border-primary" : "hover:bg-muted"}`}>{l}</button>
          ))}
        </div>
      </div>

      {state === "error" && <div className="surface p-6 text-sm" data-testid="chantiers-error">Impossible de charger vos chantiers. <button className="text-primary underline" onClick={load}>Réessayer</button></div>}
      {state === "ready" && items.length === 0 && (
        <div className="surface p-10 text-center" data-testid="chantiers-empty">
          <HardHat className="h-10 w-10 mx-auto text-primary/60" />
          <h2 className="font-semibold mt-3">Aucun dossier chantier{q || status ? " pour ce filtre" : ""}</h2>
          <p className="text-sm text-muted-foreground mt-1 max-w-md mx-auto">Créez votre premier dossier : vous retrouverez ensuite le client pré-rempli dans le devis, l'éditeur de plans, l'analyse Pro et le solveur.</p>
          {!q && !status && <Button className="mt-4 gap-2" onClick={() => setOpen(true)} data-testid="chantiers-empty-new"><Plus className="h-4 w-4" /> Créer un chantier</Button>}
        </div>
      )}
      {state === "ready" && items.length > 0 && (
        <div className="grid gap-2" data-testid="chantiers-list">
          {items.map((c) => (
            <Link key={c.chantier_id} to={`/chantiers/${c.chantier_id}`} className="surface workspace-site-card" data-testid={`chantier-row-${c.chantier_id}`}>
              <div className="h-10 w-10 rounded-sm bg-primary/10 text-primary grid place-items-center shrink-0"><HardHat className="h-5 w-5" /></div>
              <div className="min-w-0 flex-1">
                <p className="font-semibold truncate">{c.name}</p>
                <p className="text-xs text-muted-foreground truncate">{[c.client_name, [c.address, c.postal_code, c.city].filter(Boolean).join(" ")].filter(Boolean).join(" · ") || "Client à renseigner"}</p>
              </div>
              <div className="workspace-site-counts">
                <Count icon={FileText} n={c.counts.documents} title="Devis et factures" label="docs" />
                <Count icon={Ruler} n={c.counts.plans} title="Plans" label="plans" />
                {c.counts.plans_pro > 0 && <Count icon={Layers} n={c.counts.plans_pro} title="Analyses Pro" label="analyses" />}
                {c.counts.diagnostics > 0 && <Count icon={Wrench} n={c.counts.diagnostics} title="Diagnostics" label="diagnostics" />}
                {c.counts.reports > 0 && <Count icon={Camera} n={c.counts.reports} title="Comptes rendus" label="rapports" />}
              </div>
              <Badge variant="outline" className={`rounded-sm text-[10px] ${STATUS_CLASS[c.status] || ""}`} data-testid={`chantier-status-${c.chantier_id}`}>{CHANTIER_STATUS[c.status] || c.status}</Badge>
              <ChevronRight className="h-4 w-4 text-muted-foreground" />
            </Link>
          ))}
        </div>
      )}
      <ChantierFormDialog open={open} onOpenChange={setOpen} onSaved={(c) => nav(`/chantiers/${c.chantier_id}`)} />
    </div>
  );
}

