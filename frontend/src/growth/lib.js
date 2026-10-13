import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";

export const useApi = (path, deps = []) => {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const reload = useCallback(async () => {
    if (!path) return;
    setLoading(true);
    try { const r = await api.get(path); setData(r.data); setError(null); }
    catch (e) { setError(e?.response?.data?.detail || "Chargement impossible"); }
    finally { setLoading(false); }
  }, [path]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [reload, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, loading, reload, setData };
};

export const usd = (v) => (v == null ? "—" : `${Number(v).toFixed(4)} $`);
export const dt = (v) => (v ? new Date(v).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "—");
export const err = (e, fallback = "Action impossible") => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : d?.message || fallback;
};
export const SEV = { haute: "bg-red-500/15 text-red-700 dark:text-red-300", moyenne: "bg-amber-500/15 text-amber-700 dark:text-amber-300", basse: "bg-muted text-muted-foreground" };
export const STATUS_FR = { queued: "en attente", running: "en cours", completed: "terminé", stopped: "arrêté", failed: "échec", interrupted: "interrompu", estimated: "estimée", budget_reached: "plafond atteint",
  idea: "idée", brief: "brief", draft: "brouillon", review: "à relire", approved: "approuvé", scheduled: "programmé", published: "publié", archived: "archivé", todo: "à faire", doing: "en cours", done: "fait", fixing: "correction appliquée", fixed: "corrigé", ignored: "ignoré", open: "ouvert" };
