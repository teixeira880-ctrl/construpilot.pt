import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { ChevronDown, HardHat, Plus } from "lucide-react";
import Dashboard from "@/pages/Dashboard";
import { TaskHome } from "@/components/dashboard/TaskHome";
import { api } from "@/lib/api";
import { usePermissions } from "@/context/PermissionContext";

/** Painel: « O que precisas de fazer hoje? » por cima do painel existente.
 *  Envolve Dashboard.jsx sem o modificar. Em modo guiado, atalhos e indicadores ficam recolhidos. */
export default function DashboardHome() {
  const [mode, setMode] = useState("guiado");
  const [showSecondary, setShowSecondary] = useState(false);
  const guidedCollapsed = mode === "guiado" && !showSecondary;
  return (
    <div className={`space-y-4${guidedCollapsed ? " cp-guided-collapsed" : ""}`} data-testid="dashboard-home">
      {guidedCollapsed && <style>{".cp-guided-collapsed .dashboard-quick-actions,.cp-guided-collapsed .dashboard-stats{display:none}"}</style>}
      <TaskHome onProfile={p => setMode(p?.mode || "guiado")} />
      <ProjectsWithoutDossier />
      {mode === "guiado" && <button type="button" onClick={() => setShowSecondary(s => !s)} aria-expanded={showSecondary}
        className="inline-flex min-h-10 items-center gap-1 text-sm font-semibold text-muted-foreground" data-testid="dashboard-secondary-toggle">
        <ChevronDown className={`h-4 w-4 transition ${showSecondary ? "rotate-180" : ""}`} />{showSecondary ? "Recolher atalhos e indicadores" : "Mostrar atalhos e indicadores"}</button>}
      <Dashboard />
    </div>
  );
}

/** Projetos (estimativas) e processos de obra são coleções distintas. Mostra os projetos sem processo
 *  e deixa criar um, a pedido — nada é movido nem fundido. */
function ProjectsWithoutDossier() {
  const { can } = usePermissions();
  const allowed = can?.("chantier");
  const [items, setItems] = useState([]);
  useEffect(() => {
    if (!allowed) return;
    api.get("/projects").then(({ data }) => setItems((Array.isArray(data) ? data : data?.projects || []).filter(p => !p.chantier_id).slice(0, 3))).catch(() => {});
  }, [allowed]);
  if (!allowed || !items.length) return null;
  const create = async (p) => {
    try {
      const { data } = await api.post(`/chantiers/from-project/${p.project_id}`);
      setItems(list => list.filter(x => x.project_id !== p.project_id));
      toast.success(data.already_linked ? "Este projeto já tinha um processo de obra." : "Processo de obra criado e ligado ao projeto.", {
        action: { label: "Abrir", onClick: () => window.location.assign(`/chantiers/${data.chantier_id}`) } });
    } catch (e) { toast.error(e?.response?.data?.detail || "Não foi possível criar o processo de obra"); }
  };
  return (
    <section className="rounded-2xl border bg-card p-4" data-testid="projects-without-dossier">
      <h2 className="text-sm font-semibold">Projetos ainda sem processo de obra</h2>
      <p className="text-xs text-muted-foreground">Os projetos (estimativas) e os processos de obra são separados. Crie o processo quando a obra avançar: nada é movido.</p>
      <ul className="mt-2 space-y-2">{items.map(p => <li key={p.project_id} className="flex min-h-11 items-center justify-between gap-2 rounded-xl border px-3">
        <Link to={`/projet/${p.project_id}`} className="truncate text-sm">{p.name || "Projeto"}</Link>
        <button type="button" onClick={() => create(p)} className="inline-flex min-h-9 shrink-0 items-center gap-1 rounded-lg border px-2 text-xs" data-testid={`project-to-dossier-${p.project_id}`}>
          <HardHat className="h-4 w-4" /><Plus className="h-3 w-3" />Criar processo</button></li>)}</ul>
    </section>
  );
}
