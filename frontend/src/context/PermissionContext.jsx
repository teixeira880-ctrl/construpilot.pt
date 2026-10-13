import { createContext, useContext, useEffect, useState, useCallback, useRef } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const DENIED = Object.freeze({ role: null, active: false, permissions: {}, in_org: false, loading: false, error: false });
const PermissionContext = createContext(null);

export const PermissionProvider = ({ children }) => {
  const { user } = useAuth();
  const [state, setState] = useState(DENIED);
  const requestId = useRef(0);
  const controller = useRef(null);
  const refresh = useCallback(async () => {
    const id = ++requestId.current;
    controller.current?.abort();
    controller.current = new AbortController();
    setState({ ...DENIED, subject: user, loading: !!user });
    if (!user) return;
    // Personal tools do not depend on the professional company API.
    if (user.account_type === "particulier" && user.role !== "admin") {
      setState({ ...DENIED, subject: user, active: user.company_active !== false });
      return;
    }
    try {
      const { data } = await api.get("/company/me", { signal: controller.current.signal, timeout: 15000 });
      if (id !== requestId.current) return;
      if (!data || typeof data.active !== "boolean" || !data.permissions || Array.isArray(data.permissions) || typeof data.permissions !== "object") throw new Error("Invalid permissions");
      setState({ ...DENIED, subject: user, role: data.role, active: data.active,
        permissions: data.permissions, in_org: data.in_org === true, role_label: data.role_label });
    } catch {
      if (id === requestId.current) setState({ ...DENIED, subject: user, error: true });
    }
  }, [user]);

  useEffect(() => {
    refresh();
    return () => { requestId.current += 1; controller.current?.abort(); };
  }, [refresh]);

  useEffect(() => {
    const offline = () => {
      requestId.current += 1;
      controller.current?.abort();
      setState({ ...DENIED, subject: user, error: !!user });
    };
    window.addEventListener("offline", offline);
    window.addEventListener("online", refresh);
    return () => {
      window.removeEventListener("offline", offline);
      window.removeEventListener("online", refresh);
    };
  }, [user, refresh]);

  // Never expose the previous identity's permissions, even before the effect runs.
  const current = state.subject === user ? state : { ...DENIED, loading: !!user };
  const can = (feature) => !current.loading && !current.error && current.active === true && current.permissions[feature] === true;
  return <PermissionContext.Provider value={{ ...current, can, refresh }}>{children}</PermissionContext.Provider>;
};

export const usePermissions = () => useContext(PermissionContext) || { ...DENIED, can: () => false, refresh: () => {} };