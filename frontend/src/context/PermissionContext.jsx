import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * Permissions Espace Entreprise.
 * - role : owner | admin | chef_chantier | comptable | member | ouvrier
 * - can(feature) : bool (dashboard, devis, factures, situations, chantier, rh, catalogue, entreprise, pointage)
 * Solo (sans org) et owner/admin → accès complet. Les rôles limités restreignent l'accès.
 */
const PermissionContext = createContext(null);
const ALL = { dashboard: true, devis: true, factures: true, situations: true, chantier: true, rh: true, catalogue: true, entreprise: true, pointage: true };

export const PermissionProvider = ({ children }) => {
  const { user } = useAuth();
  const [state, setState] = useState({ role: "owner", active: true, permissions: ALL, in_org: false, loading: true });

  const refresh = useCallback(async () => {
    if (!user) { setState({ role: "owner", active: true, permissions: ALL, in_org: false, loading: false }); return; }
    try {
      const { data } = await api.get("/company/me");
      setState({ role: data.role, active: data.active, permissions: data.permissions || ALL,
        in_org: data.in_org, role_label: data.role_label, loading: false });
    } catch {
      setState({ role: "owner", active: true, permissions: ALL, in_org: false, loading: false });
    }
  }, [user]);

  useEffect(() => { refresh(); }, [refresh]);

  const can = (feature) => state.permissions?.[feature] !== false;

  return (
    <PermissionContext.Provider value={{ ...state, can, refresh }}>
      {children}
    </PermissionContext.Provider>
  );
};

export const usePermissions = () => {
  const ctx = useContext(PermissionContext);
  if (!ctx) return { role: "owner", active: true, permissions: ALL, in_org: false, can: () => true, refresh: () => {} };
  return ctx;
};
