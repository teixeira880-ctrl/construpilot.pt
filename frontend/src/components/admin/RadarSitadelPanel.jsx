import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { RadarOfficialSource } from "@/components/radar/RadarOfficialSource";
import { Button } from "@/components/ui/button";

export default function RadarSitadelPanel() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const load = useCallback(async () => {
    if (pending.current) return;
    pending.current = true;
    try { const { data } = await api.get("/radar/admin/permits/count", { timeout: 15000 }); setStatus(data); setError(""); }
    catch { setError("Impossível ler o estado das licenças (INE)."); }
    finally { pending.current = false; }
  }, []);
  useEffect(() => { load(); }, [load]);
  const running = status?.sync?.departments?.some((d) => d.status === "running");
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(load, 3000);
    return () => clearInterval(timer);
  }, [running, load]);
  return <div className="space-y-3" data-testid="radar-sitadel-panel">
    <h2 className="text-lg font-semibold">Radar · dados oficiais de licenças</h2>
    {error && <div><p role="alert" className="text-sm text-red-700" data-testid="sitadel-admin-error">{error}</p><Button variant="outline" size="sm" onClick={load} data-testid="sitadel-admin-retry">Tentar novamente</Button></div>}
    {status ? <p className="text-sm" data-testid="sitadel-count">{status.count} permis officiels disponibles</p> : !error && <p role="status" className="text-sm text-muted-foreground" data-testid="sitadel-admin-loading">A carregar as licenças oficiais…</p>}
    <RadarOfficialSource sync={status?.sync} onRefresh={load} />
  </div>;
}