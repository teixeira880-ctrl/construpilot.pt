import { useEffect, useState } from "react";
import { toast } from "sonner";
import { MonitorSmartphone, Trash2, LogOut } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";

const fmtDate = (iso) => {
  if (!iso) return "";
  try {
    return new Date(iso).toLocaleString("pt-PT", { dateStyle: "short", timeStyle: "short" });
  } catch {
    return iso.slice(0, 16);
  }
};

export const DevicesList = () => {
  const [devices, setDevices] = useState([]);
  const [busy, setBusy] = useState(false);

  const load = async () => {
    try {
      const { data } = await api.get("/auth/devices");
      setDevices(data.devices || []);
    } catch {
      setDevices([]);
    }
  };
  useEffect(() => { load(); }, []);

  const remove = async (key) => {
    try {
      await api.delete(`/auth/devices/${key}`);
      toast.success("Appareil retiré de l'historique");
      load();
    } catch {
      toast.error("Eliminação impossível");
    }
  };

  const logoutOthers = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/auth/logout-others");
      if (data.token) localStorage.setItem("construpilot_token", data.token);
      toast.success("Tous les autres appareils ont été déconnectés");
      load();
    } catch {
      toast.error("Operação impossível");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="surface p-5 space-y-4" data-testid="devices-list">
      <p className="font-semibold flex items-center gap-2">
        <MonitorSmartphone className="h-4 w-4 text-primary" /> Historique des connexions
      </p>
      {devices.length === 0 ? (
        <p className="text-sm text-muted-foreground">Aucun appareil enregistré pour l'instant.</p>
      ) : (
        <ul className="space-y-2">
          {devices.map((d) => (
            <li key={d.device_key}
                className="flex items-center gap-3 border border-border rounded-sm p-3"
                data-testid={`device-row-${d.device_key.slice(0, 8)}`}>
              <div className="min-w-0 flex-1">
                <p className="text-sm truncate">{d.user_agent}</p>
                <p className="text-xs text-muted-foreground">
                  IP {d.ip} · dernière activité {fmtDate(d.last_seen)}
                </p>
              </div>
              {d.current ? (
                <Badge className="rounded-sm shrink-0" data-testid="device-current-badge">
                  Cet appareil
                </Badge>
              ) : (
                <Button type="button" variant="ghost" size="icon" className="shrink-0"
                        onClick={() => remove(d.device_key)}
                        data-testid={`device-remove-${d.device_key.slice(0, 8)}`}>
                  <Trash2 className="h-4 w-4 text-muted-foreground" />
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <Button type="button" variant="outline" disabled={busy}
              onClick={logoutOthers} className="rounded-sm w-full gap-2"
              data-testid="logout-others-btn">
        <LogOut className="h-4 w-4" /> Déconnecter tous les autres appareils
      </Button>
      <p className="text-[10px] text-muted-foreground">
        Les sessions et jetons de connexion des autres appareils seront immédiatement invalidés.
      </p>
    </div>
  );
};
