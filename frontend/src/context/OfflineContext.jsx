import { createContext, useContext, useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CloudOff, RefreshCw, CheckCircle2 } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { pendingCount, flushQueue } from "@/lib/offlineProjects";

const OfflineContext = createContext(null);

export const OfflineProvider = ({ children }) => {
  const { user } = useAuth();
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  const [pending, setPending] = useState(0);
  const [syncing, setSyncing] = useState(false);
  const uid = user?.user_id;
  const busy = useRef(false);

  const refreshPending = useCallback(async () => {
    if (!uid) { setPending(0); return; }
    setPending(await pendingCount(uid));
  }, [uid]);

  const sync = useCallback(async () => {
    if (!uid || busy.current || typeof navigator !== "undefined" && !navigator.onLine) return;
    const count = await pendingCount(uid);
    if (count === 0) return;
    busy.current = true; setSyncing(true);
    try {
      const done = await flushQueue(uid);
      if (done > 0) {
        toast.success(`${done} modification(s) synchronisée(s).`, { icon: <CheckCircle2 className="h-4 w-4" /> });
        window.dispatchEvent(new Event("construpilot-offline-synced"));
      }
    } finally {
      busy.current = false; setSyncing(false);
      await refreshPending();
    }
  }, [uid, refreshPending]);

  useEffect(() => { refreshPending(); }, [refreshPending]);

  useEffect(() => {
    const goOnline = () => { setOnline(true); sync(); };
    const goOffline = () => { setOnline(false); toast.warning("Hors connexion — vos modifications seront synchronisées au retour du réseau."); };
    const onQueued = () => refreshPending();
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    window.addEventListener("construpilot-offline-queued", onQueued);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
      window.removeEventListener("construpilot-offline-queued", onQueued);
    };
  }, [sync, refreshPending]);

  // Attempt an initial sync when a user session is present and we are online.
  useEffect(() => { if (uid && online) sync(); }, [uid, online, sync]);

  const value = { online, pending, syncing, sync, refreshPending };
  return (
    <OfflineContext.Provider value={value}>
      {(!online || pending > 0) && (
        <div className={`cp-offline-bar ${online ? "is-pending" : "is-offline"}`} data-testid="offline-bar" role="status">
          {!online
            ? <><CloudOff className="h-4 w-4" /> <span>Mode hors connexion{pending > 0 ? ` · ${pending} modif. en attente` : ""}</span></>
            : <><RefreshCw className={`h-4 w-4 ${syncing ? "animate-spin" : ""}`} /> <span>{syncing ? "Synchronisation…" : `${pending} modif. à synchroniser`}</span>
                {!syncing && <button type="button" className="cp-offline-sync" onClick={sync} data-testid="offline-sync-btn">Synchroniser</button>}</>}
        </div>
      )}
      {children}
    </OfflineContext.Provider>
  );
};

export const useOffline = () => useContext(OfflineContext) || { online: true, pending: 0, syncing: false, sync: () => {}, refreshPending: () => {} };
