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
    catch (e) { setError(e?.response?.data?.detail || "Não foi possível carregar"); }
    finally { setLoading(false); }
  }, [path]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { reload(); }, [reload, ...deps]); // eslint-disable-line react-hooks/exhaustive-deps
  return { data, error, loading, reload, setData };
};

export const usd = (v) => (v == null ? "—" : `${Number(v).toFixed(4)} $`);
export const dt = (v) => (v ? new Date(v).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" }) : "—");
export const err = (e, fallback = "Ação impossível") => {
  const d = e?.response?.data?.detail;
  return typeof d === "string" ? d : d?.message || fallback;
};
export const SEV = { haute: "bg-red-500/15 text-red-700 dark:text-red-300", moyenne: "bg-amber-500/15 text-amber-700 dark:text-amber-300", basse: "bg-muted text-muted-foreground" };
export const STATUS_FR = { queued: "en attente", running: "en cours", completed: "concluída", stopped: "parado", failed: "falha", interrupted: "interrompu", estimated: "estimada", budget_reached: "plafond atteint",
  idea: "ideia", brief: "brief", draft: "brouillon", review: "a rever", approved: "aprovado", scheduled: "agendado", published: "publicado", archived: "arquivado", todo: "a fazer", doing: "en cours", done: "fait", fixing: "correção aplicada", fixed: "corrigido", ignored: "ignorado", open: "ouvert" };
