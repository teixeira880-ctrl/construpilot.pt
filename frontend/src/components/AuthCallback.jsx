import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function AuthCallback() {
  const navigate = useNavigate();
  const { setUser } = useAuth();
  const hasProcessed = useRef(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (hasProcessed.current) return;
    hasProcessed.current = true;
    const params = new URLSearchParams(window.location.hash.replace("#", "?"));
    const sessionId = params.get("session_id");
    (async () => {
      try {
        const { data } = await api.post("/auth/session", { session_id: sessionId }, {
          headers: { "X-Session-ID": sessionId },
        });
        window.history.replaceState({}, document.title, window.location.pathname);
        if (data.two_fa_required) {
          navigate("/login", { replace: true, state: { twoFactor: data } });
          return;
        }
        setUser(data.user);
        // Auth par cookie httpOnly — le backend a déjà posé session_token.
        try { localStorage.setItem("construpilot_session", "1"); } catch {}
        navigate("/dashboard", { replace: true, state: { user: data.user } });
      } catch (e) {
        setError("Connexion Google impossible. Réessayez.");
        setTimeout(() => navigate("/login", { replace: true }), 2000);
      }
    })();
  }, [navigate, setUser]);

  return (
    <div className="min-h-screen grid place-items-center bg-background" data-testid="auth-callback">
      <div className="text-center">
        <div className="h-10 w-10 mx-auto border-2 border-primary border-t-transparent rounded-full animate-spin" />
        <p className="mt-6 text-sm text-muted-foreground">
          {error || "Connexion à ConstruPilot…"}
        </p>
      </div>
    </div>
  );
}

