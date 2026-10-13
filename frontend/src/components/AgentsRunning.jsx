import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const POLL_MS = 2500;

// Indicateur global : les agents tournent côté serveur et survivent au changement
// de page. On sonde /agents/active ; dès qu'un run quitte la liste active, on
// signale la fin (le détail reste dans la cloche de notifications + page Agents).
export function AgentsRunning() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [active, setActive] = useState([]);
  const prev = useRef(new Set());
  const timer = useRef(null);

  useEffect(() => {
    let stopped = false;
    let polling = false;
    prev.current = new Set();
    setActive([]);
    if (!user) return undefined;
    const poll = async () => {
      if (polling || stopped) return;
      polling = true;
      try {
        const { data } = await api.get("/agents/active");
        if (stopped) return;
        const rows = data.runs || [];
        const ids = new Set(rows.map((r) => r.run_id));
        const finished = [...prev.current].filter(id => !ids.has(id));
        if (finished.length) {
          const history = await api.get("/agents/runs");
          if (stopped) return;
          const completed = (history.data.runs || []).filter(run => finished.includes(run.run_id));
          const options = { description: "Consultez les résultats et les points à vérifier.", action: { label: "Ouvrir", onClick: () => navigate("/agents") } };
          if (completed.some(run => run.status === "error")) toast.error("Une tâche a été interrompue", options);
          else if (completed.some(run => run.status === "done")) toast.success("Le contrôle est terminé", options);
        }
        prev.current = ids;
        setActive(rows);
      } catch { /* silencieux */ }
      finally { polling = false; }
    };
    poll();
    timer.current = setInterval(poll, POLL_MS);
    return () => { stopped = true; clearInterval(timer.current); };
  }, [user, navigate]);

  if (!user || active.length === 0) return null;
  return (
    <button
      type="button"
      data-testid="agents-running-indicator"
      onClick={() => navigate("/agents")}
      className="fixed bottom-[calc(5.75rem+env(safe-area-inset-bottom))] md:bottom-4 left-4 z-50 flex items-center gap-2 rounded-full border border-primary/30
                 bg-card/95 backdrop-blur px-3.5 py-2 shadow-lg hover:border-primary/60 transition-colors"
    >
      <Loader2 className="h-4 w-4 text-primary animate-spin" />
      <span className="text-xs font-semibold">
        {active.length} agent{active.length > 1 ? "s" : ""} en cours…
      </span>
    </button>
  );
}

export default AgentsRunning;
