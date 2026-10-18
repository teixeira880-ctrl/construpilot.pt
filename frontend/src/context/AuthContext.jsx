import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { api } from "@/lib/api";

const AuthContext = createContext(null);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      setUser(data);
      try { localStorage.setItem("construpilot_session", "1"); } catch {}
    } catch (error) {
      if ([401, 403].includes(error.response?.status)) {
        setUser(null);
        try { localStorage.removeItem("construpilot_session"); } catch {}
      }
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    // CRITICAL: si retour du callback OAuth, laisser AuthCallback échanger le session_id
    if (window.location.hash?.includes("session_id=")) {
      setLoading(false);
      return;
    }
    // Seul le serveur peut vérifier le cookie httpOnly. Le stockage local peut
    // être effacé ou bloqué alors que la session est toujours valide.
    checkAuth();
  }, [checkAuth]);

  // Thème mémorisé sur le compte : appliqué dès que l'utilisateur est connu (tous appareils)
  useEffect(() => {
    if (!user?.theme) return;
    document.documentElement.classList.toggle("dark", user.theme === "dark");
    try { localStorage.setItem("construpilot_theme", user.theme); } catch {}
    window.dispatchEvent(new Event("construpilot-theme"));
  }, [user?.theme]);

  const login = async (email, password) => {
    // Auth par cookie httpOnly — le champ `token` éventuellement renvoyé est ignoré.
    const { data } = await api.post("/auth/login", { email, password });
    if (data.two_fa_required) return data;
    setUser(data.user);
    try { localStorage.setItem("construpilot_session", "1"); } catch {}
    return data.user;
  };

  const demoLogin = async (kind) => {
    // Login para conta demo Web Summit. Cookie HttpOnly definido pelo backend.
    // Password NUNCA transita no frontend. Response body contém só o utilizador público.
    const { data } = await api.post("/auth/demo-login", { kind });
    setUser(data.user);
    try { localStorage.setItem("construpilot_session", "1"); } catch {}
    return data.user;
  };

  const verify2fa = async (pendingToken, code) => {
    const { data } = await api.post("/auth/verify-2fa", {
      pending_token: pendingToken, code,
    });
    setUser(data.user);
    try { localStorage.setItem("construpilot_session", "1"); } catch {}
    return data.user;
  };

  const register = async (name, email, password, referredByCode = null, extra = {}) => {
    const payload = { name, email, password, ...extra };
    if (referredByCode) payload.referred_by_code = referredByCode.trim().toUpperCase();
    try { payload.lang = localStorage.getItem("construpilot_lang") || undefined; } catch { /* noop */ }
    try { const ft = localStorage.getItem("cp_first_touch"); if (ft) payload.attribution = JSON.parse(ft); } catch { /* noop */ }    const { data } = await api.post("/auth/register", payload);
    setUser(data.user);
    try { localStorage.setItem("construpilot_session", "1"); } catch {}
    return data.user;
  };

  const logout = async () => {
    try {
      await api.post("/auth/logout");
    } catch {}
    // Nettoyer un éventuel legacy token qui traînerait de l'ancienne version.
    try { localStorage.removeItem("construpilot_token"); localStorage.removeItem("construpilot_session"); } catch {}
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, demoLogin, verify2fa, register, logout, setUser, checkAuth }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => useContext(AuthContext);

