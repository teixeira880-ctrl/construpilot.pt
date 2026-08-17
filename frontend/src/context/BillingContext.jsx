import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

/**
 * Contexte de facturation ConstruPilot :
 * - tier : 'free' | 'project_pass' | 'premium' | 'pro' | 'pro_business'
 * - active : { entitlement, plan } | null
 * - flags : feature flags (trial_enabled, paywall_mode, marketplace, affiliate…)
 * - has(feature) : bool
 * - refresh() : recharge après paiement
 */
const BillingContext = createContext(null);

const PREMIUM_TIERS = new Set(["project_pass", "premium", "pro", "pro_business"]);
const PRO_BUSINESS_ONLY = new Set(["pro_business"]);

const FEATURE_TIER = {
  unlimited_projects: PREMIUM_TIERS,
  unlimited_estimations: PREMIUM_TIERS,
  ai_advisor_full: PREMIUM_TIERS,
  price_search_full: PREMIUM_TIERS,
  cart_optimization: PREMIUM_TIERS,
  price_alerts: PREMIUM_TIERS,
  quote_analysis: PREMIUM_TIERS,
  savings_details: PREMIUM_TIERS,
  advanced_pdf: PREMIUM_TIERS,
  calculator_pro_tools: PREMIUM_TIERS,
  site_tracking: PRO_BUSINESS_ONLY,
  // Plan 2D + 3D ouverts à tous les utilisateurs connectés (rendus 3D payants à l'unité).
  // Le contrôle fin (offerts / crédits / illimité) est géré côté backend par action.
};

export const BillingProvider = ({ children }) => {
  const { user } = useAuth();
  const [state, setState] = useState({ tier: "free", active: null, loading: false });
  const [flags, setFlags] = useState({ paywall_mode: "soft", trial_enabled: true, trial_days: 7 });

  const refresh = useCallback(async () => {
    if (!user) { setState({ tier: "free", active: null, loading: false }); return; }
    setState((s) => ({ ...s, loading: true }));
    try {
      const [me, pf] = await Promise.all([
        api.get("/billing/me"),
        api.get("/billing/flags").catch(() => ({ data: {} })),
      ]);
      setState({ tier: me.data.tier || "free", active: me.data.active || null, loading: false });
      if (pf.data) setFlags((f) => ({ ...f, ...pf.data }));
    } catch {
      setState({ tier: "free", active: null, loading: false });
    }
  }, [user]);

  useEffect(() => { refresh(); }, [refresh]);

  const has = (feature) => {
    if (user?.role === "admin") return true;
    const tiers = FEATURE_TIER[feature];
    if (!tiers) return true;
    return tiers.has(state.tier);
  };

  return (
    <BillingContext.Provider value={{ ...state, flags, has, refresh }}>
      {children}
    </BillingContext.Provider>
  );
};

export const useBilling = () => {
  const ctx = useContext(BillingContext);
  if (!ctx) return { tier: "free", active: null, flags: {}, has: () => true, refresh: () => {} };
  return ctx;
};
