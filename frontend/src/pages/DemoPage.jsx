import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { toast } from "sonner";
import { Hammer, Briefcase, User, ArrowRight, WifiOff, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { useI18n } from "@/context/I18nContext";
import { api } from "@/lib/api";
import {
  enableDemoMode,
  isDemoActive,
  resetDemoStore,
} from "@/lib/demoInterceptor";

/**
 * Página dedicada `/demo` — 2 CTAs grandes para o QR code do stand Web Summit.
 * Zero password no frontend, cookie HttpOnly definido pelo backend em `/auth/demo-login`.
 */
export default function DemoPage() {
  const { demoLogin, user } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [status, setStatus] = useState({ pro: null, particular: null });
  const [busy, setBusy] = useState(null);

  useEffect(() => {
    api.get("/auth/demo-status").then(({ data }) => setStatus(data)).catch(() => {
      // Em modo demo offline (interceptor activo), a chamada acima resolve local
      // devolvendo { enabled: true, kind }. Em modo normal com backend KO,
      // devolve pro/particular false para esconder os CTA.
      setStatus({ pro: false, particular: false });
    });
  }, []);

  useEffect(() => {
    if (user) navigate("/dashboard");
  }, [user, navigate]);

  const onPick = async (kind) => {
    if (busy) return;
    setBusy(kind);
    try {
      await demoLogin(kind);
      toast.success(t("login.demo_hint") || "Modo demo activado.");
      navigate("/dashboard");
    } catch (err) {
      const detail = err?.response?.data?.detail;
      const unavailable = detail?.error === "demo_unavailable";
      toast.error(
        unavailable
          ? (t("login.demo_fail") || "Demo indisponível. Tente mais tarde.")
          : (t("login.demo_fail") || "Demo login falhou.")
      );
    } finally {
      setBusy(null);
    }
  };

  const onPickOffline = async (kind) => {
    if (busy) return;
    setBusy(kind);
    try {
      enableDemoMode({ kind });
      // Com a flag activa, `demoLogin` resolve pelo interceptor (zero rede).
      await demoLogin(kind);
      toast.success("Modo offline WebSummit activado — pode fechar os dados móveis.");
      navigate("/dashboard");
    } catch (err) {
      toast.error("Não foi possível activar o modo offline. Tente novamente.");
    } finally {
      setBusy(null);
    }
  };

  const onReset = async () => {
    await resetDemoStore();
    toast.success("Demo offline reiniciada.");
    setTimeout(() => window.location.reload(), 400);
  };

  const anyAvailable = status.pro || status.particular;
  const loading = status.pro === null;

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="border-b border-border">
        <div className="mx-auto max-w-5xl px-5 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2" data-testid="demo-header-home">
            <Hammer className="h-5 w-5 text-primary" />
            <span className="font-display font-bold">ConstruPilot</span>
          </Link>
          <Link to="/login" className="text-sm text-muted-foreground hover:text-primary" data-testid="demo-header-login">
            {t("login.tab_login") || "Entrar"}
          </Link>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-5 py-12" data-testid="demo-page">
        <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">
          {t("demo_page.title") || "Experimentar o ConstruPilot"}
        </h1>
        <p className="mt-4 text-base text-muted-foreground">
          {t("demo_page.subtitle") || "Explore a plataforma sem criar conta. Dados fictícios, sessão temporária, zero compromisso."}
        </p>

        {loading && (
          <div className="mt-10 h-24 animate-pulse rounded-md bg-muted" data-testid="demo-loading" />
        )}

        {!loading && !anyAvailable && (
          <div className="mt-10 rounded-md border border-destructive/30 bg-destructive/5 p-6" data-testid="demo-unavailable">
            <p className="font-medium">{t("demo_page.unavailable_title") || "Demo indisponível"}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t("demo_page.unavailable_desc") || "O modo demonstração não está activo neste momento. Por favor crie uma conta ou volte mais tarde."}
            </p>
            <Button className="mt-4" asChild data-testid="demo-fallback-register">
              <Link to="/login?tab=register">{t("demo_page.register_cta") || "Criar conta grátis"}</Link>
            </Button>
          </div>
        )}

        {!loading && anyAvailable && (
          <div className="mt-10 grid gap-4 sm:grid-cols-2">
            {status.pro && (
              <button
                type="button"
                onClick={() => onPick("pro")}
                disabled={!!busy}
                data-testid="demo-page-pro-btn"
                className="group text-left rounded-md border border-border bg-card p-6 transition hover:border-primary hover:shadow-md disabled:opacity-50"
              >
                <div className="flex items-center gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <Briefcase className="h-5 w-5 text-primary" />
                  </div>
                  <h2 className="font-display text-lg font-semibold">
                    {t("demo_page.pro_title") || "Profissional"}
                  </h2>
                </div>
                <p className="mt-3 text-sm text-muted-foreground">
                  {t("demo_page.pro_desc") || "Projecto Moradia Martins com planta, medições e orçamento. Teste PlanTakeoff, Assistente de Obra e Chiffrer."}
                </p>
                <div className="mt-4 inline-flex items-center text-sm font-medium text-primary">
                  {busy === "pro" ? (t("demo_page.loading") || "A entrar…") : (t("demo_page.pro_cta") || "Entrar como profissional")}
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </div>
              </button>
            )}

            {status.particular && (
              <button
                type="button"
                onClick={() => onPick("particular")}
                disabled={!!busy}
                data-testid="demo-page-particular-btn"
                className="group text-left rounded-md border border-border bg-card p-6 transition hover:border-primary hover:shadow-md disabled:opacity-50"
              >
                <div className="flex items-center gap-3">
                  <div className="rounded-full bg-primary/10 p-2">
                    <User className="h-5 w-5 text-primary" />
                  </div>
                  <h2 className="font-display text-lg font-semibold">
                    {t("demo_page.particular_title") || "Particular"}
                  </h2>
                </div>
                <p className="mt-3 text-sm text-muted-foreground">
                  {t("demo_page.particular_desc") || "Experimente o estimador de obras, o assistente IA e as calculadoras. Plano gratuito, sem cartão."}
                </p>
                <div className="mt-4 inline-flex items-center text-sm font-medium text-primary">
                  {busy === "particular" ? (t("demo_page.loading") || "A entrar…") : (t("demo_page.particular_cta") || "Entrar como particular")}
                  <ArrowRight className="ml-2 h-4 w-4 transition-transform group-hover:translate-x-1" />
                </div>
              </button>
            )}
          </div>
        )}

        <div className="mt-8 rounded-md border border-dashed border-border bg-muted/30 p-4" data-testid="demo-notice">
          <p className="text-xs text-muted-foreground">
            {t("demo_page.notice") || "Em modo demo algumas acções (envio de emails, pagamentos, assinaturas, facturação) estão desactivadas. Os dados são sintéticos e repostos diariamente."}
          </p>
        </div>

        {/* LOTE 2 WebSummit — Modo offline para o stand (modo avião após 1ª carga) */}
        <div className="mt-6 rounded-md border border-primary/30 bg-primary/5 p-5" data-testid="demo-offline-block">
          <div className="flex items-start gap-3">
            <div className="rounded-full bg-primary/15 p-2">
              <WifiOff className="h-5 w-5 text-primary" />
            </div>
            <div className="flex-1">
              <p className="font-display font-semibold">Modo offline — stand WebSummit</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Carrega as fixtures da Moradia Martins em cache. Depois pode activar modo avião e a demo continua a funcionar (login, projecto, estimativa, dossier, assistente). Fluxo apenas para as contas demo — contas normais nunca são afectadas.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  size="sm"
                  variant="outline"
                  className="rounded-sm"
                  onClick={() => onPickOffline("pro")}
                  disabled={!!busy}
                  data-testid="demo-offline-pro-btn"
                >
                  <Briefcase className="h-4 w-4 mr-2" />
                  Offline — Profissional
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  className="rounded-sm"
                  onClick={() => onPickOffline("particular")}
                  disabled={!!busy}
                  data-testid="demo-offline-particular-btn"
                >
                  <User className="h-4 w-4 mr-2" />
                  Offline — Particular
                </Button>
                {isDemoActive() && (
                  <Button
                    size="sm"
                    variant="ghost"
                    className="rounded-sm text-destructive"
                    onClick={onReset}
                    data-testid="demo-offline-reset-btn"
                  >
                    <RotateCcw className="h-4 w-4 mr-2" />
                    Reiniciar demo
                  </Button>
                )}
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
