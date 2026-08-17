import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { Hammer, ArrowLeft, Gift, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";
import { useI18n, LangToggle } from "@/context/I18nContext";
import { api, IMAGES } from "@/lib/api";

export default function Login() {
  const { login, register, verify2fa, user } = useAuth();
  const { t } = useI18n();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const refCodeFromUrl = params.get("ref") || "";
  const [busy, setBusy] = useState(false);
  const [tfa, setTfa] = useState(null);
  const [tfaCode, setTfaCode] = useState("");
  const [form, setForm] = useState({ name: "", email: "", password: "", ref: refCodeFromUrl });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  const DEMO_ACCOUNTS = [
    { label: "Client particulier", email: "client@construpilot.fr", password: "Client2026!", color: "border-blue-500/50 text-blue-600" },
    { label: "Pro / Owner (BTP Demo)", email: "pro@construpilot.fr", password: "Pro2026!", color: "border-primary text-primary" },
    { label: "Collègue (member)", email: "collegue@construpilot.fr", password: "Collegue2026!", color: "border-emerald-500/50 text-emerald-600" },
    { label: "Admin (back-office)", email: "admin@construpilot.fr", password: "Construpilot2026!", color: "border-purple-500/50 text-purple-600" },
  ];

  const demoLogin = (acc) => async () => {
    setBusy(true);
    try {
      await login(acc.email, acc.password);
      toast.success(`Connexion démo : ${acc.label}`, { position: "bottom-right", duration: 2500 });
      navigate("/dashboard");
    } catch (err) {
      toast.error(t("login.demo_fail"));
    } finally { setBusy(false); }
  };

  useEffect(() => {
    if (refCodeFromUrl) sessionStorage.setItem("construpilot_ref", refCodeFromUrl.toUpperCase());
  }, [refCodeFromUrl]);

  useEffect(() => {
    if (user) {
      const dest = user.role === "worker"
        ? "/pointage"
        : (user.must_change_password ? "/compte" : "/dashboard");
      navigate(dest, { replace: true });
    }
  }, [user, navigate]);

  const submit = (mode) => async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      let logged = null;
      if (mode === "login") logged = await login(form.email, form.password);
      else {
        const ref = (form.ref || sessionStorage.getItem("construpilot_ref") || "").trim();
        await register(form.name, form.email, form.password, ref || null);
        if (ref) {
          toast.success(`Code parrainage ${ref.toUpperCase()} appliqué — bienvenue !`);
          sessionStorage.removeItem("construpilot_ref");
        }
      }
      if (logged?.two_fa_required) {
        setTfa(logged);
        toast.info(t("login.tfa_sent"), { duration: 5000 });
        return;
      }
      toast.success(t("login.welcome"), { position: "bottom-right", duration: 2500 });
      if (logged?.must_change_password) {
        toast.warning(t("login.temp_pw"), { duration: 6000 });
        navigate("/compte");
      } else {
        navigate("/dashboard");
      }
    } catch (err) {
      toast.error(err?.response?.data?.detail || t("login.fail"));
    } finally {
      setBusy(false);
    }
  };

  const google = () => {
    // CRITICAL: Use window.location.origin directly with NO fallbacks or env variables for auth redirects
    const redirectUrl = window.location.origin + "/dashboard";
    window.location.href = `https://auth.emergentagent.com/?redirect=${encodeURIComponent(redirectUrl)}`;
  };

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      <div className="relative hidden lg:block grain">
        <img src={IMAGES.dashboard_banner} alt="Plans de chantier" className="absolute inset-0 h-full w-full object-cover opacity-50" />
        <div className="absolute inset-0 bg-gradient-to-t from-background via-background/60 to-background/20" />
        <div className="relative h-full p-12 flex flex-col justify-between">
          <Link to="/" className="flex items-center gap-2 w-fit">
            <img src="/construpilot-icon.png" alt="ConstruPilot" className="h-9 w-9 rounded-lg object-cover" />
            <span className="font-display font-extrabold text-lg">Constru<span className="text-primary">Pilot</span></span>
          </Link>
          <div>
            <p className="overline">{t("login.side_overline")}</p>
            <h2 className="mt-4 font-display text-4xl font-bold tracking-tighter max-w-md">
              {t("login.side_title")}
            </h2>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          <div className="flex items-center justify-between mb-8">
            <Link to="/" className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1" data-testid="back-home-link">
              <ArrowLeft className="h-3 w-3" /> {t("login.back_home")}
            </Link>
            <LangToggle />
          </div>
          <h1 className="font-display text-3xl font-bold tracking-tight">{t("login.h1")}</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            {t("login.sub")}
          </p>

          <Button
            variant="outline" onClick={google} data-testid="google-login-btn"
            className="mt-8 w-full rounded-sm gap-3 h-11"
          >
            <svg className="h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 01-2.2 3.32v2.77h3.57c2.08-1.92 3.27-4.74 3.27-8.1z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.65l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0012 23z" />
              <path fill="#FBBC05" d="M5.84 14.11a6.6 6.6 0 010-4.22V7.05H2.18a11 11 0 000 9.9l3.66-2.84z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.05l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z" />
            </svg>
            {t("login.google")}
          </Button>

          <div className="my-6 flex items-center gap-4">
            <span className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">{t("login.or_email")}</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          {tfa ? (
            <form onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              try {
                const u = await verify2fa(tfa.pending_token, tfaCode);
                toast.success(t("login.welcome"), { position: "bottom-right", duration: 2500 });
                if (u?.must_change_password) {
                  toast.warning(t("login.temp_pw"), { duration: 6000 });
                  navigate("/compte");
                } else {
                  navigate("/dashboard");
                }
              } catch (err) {
                const d = err?.response?.data?.detail;
                toast.error(typeof d === "string" ? d : t("login.tfa_wrong"));
              } finally {
                setBusy(false);
              }
            }} className="grid gap-4" data-testid="tfa-form">
              <div>
                <p className="font-semibold">{t("login.tfa_title")}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {t("login.tfa_desc")}
                </p>
              </div>
              <div className="grid gap-2">
                <Label>{t("login.tfa_label")}</Label>
                <Input required inputMode="numeric" autoFocus maxLength={6}
                       value={tfaCode}
                       onChange={(e) => setTfaCode(e.target.value.replace(/\D/g, ""))}
                       placeholder="123456"
                       className="rounded-sm h-12 text-center text-2xl tracking-[0.5em] num"
                       data-testid="tfa-code-input" />
              </div>
              <Button type="submit" disabled={busy || tfaCode.length !== 6}
                      className="rounded-sm h-11" data-testid="tfa-submit-btn">
                {busy ? t("login.tfa_verifying") : t("login.tfa_validate")}
              </Button>
              <div className="flex items-center justify-between text-xs">
                <button type="button" className="text-muted-foreground hover:text-primary"
                        data-testid="tfa-resend-btn"
                        onClick={async () => {
                          try {
                            await api.post("/auth/resend-2fa", { pending_token: tfa.pending_token });
                            toast.success(t("login.tfa_resent"));
                          } catch (err) {
                            const d = err?.response?.data?.detail;
                            toast.error(typeof d === "string" ? d : t("login.tfa_resend_fail"));
                          }
                        }}>
                  {t("login.tfa_resend")}
                </button>
                <button type="button" className="text-muted-foreground hover:text-primary"
                        data-testid="tfa-back-btn"
                        onClick={() => { setTfa(null); setTfaCode(""); }}>
                  {t("login.tfa_back")}
                </button>
              </div>
            </form>
          ) : (
          <Tabs defaultValue="login">
            <TabsList className="w-full rounded-sm">
              <TabsTrigger value="login" className="flex-1 rounded-sm" data-testid="tab-login">{t("login.tab_login")}</TabsTrigger>
              <TabsTrigger value="register" className="flex-1 rounded-sm" data-testid="tab-register">{t("login.tab_register")}</TabsTrigger>
            </TabsList>

            <TabsContent value="login">
              <form onSubmit={submit("login")} className="grid gap-4 mt-6">
                <div className="grid gap-2">
                  <Label>{t("login.email")}</Label>
                  <Input required type="email" value={form.email} onChange={set("email")} data-testid="login-email-input" className="rounded-sm h-11" />
                </div>
                <div className="grid gap-2">
                  <Label>{t("login.password")}</Label>
                  <Input required type="password" value={form.password} onChange={set("password")} data-testid="login-password-input" className="rounded-sm h-11" />
                  <Link to="/reinitialiser" className="text-xs text-muted-foreground hover:text-primary w-fit"
                        data-testid="forgot-password-link">
                    {t("login.forgot")}
                  </Link>
                </div>
                <Button type="submit" disabled={busy} data-testid="login-submit-btn" className="rounded-sm h-11 hover:bg-orange-600 hover:text-white">
                  {busy ? t("login.submitting") : t("login.submit")}
                </Button>
                <p className="text-xs text-muted-foreground">
                  {t("login.demo_hint")} <span className="num">demo@construpilot.fr</span> / <span className="num">Demo2026!</span>
                </p>
              </form>
            </TabsContent>

            <TabsContent value="register">
              <form onSubmit={submit("register")} className="grid gap-4 mt-6">
                <div className="grid gap-2">
                  <Label>{t("login.name")}</Label>
                  <Input required value={form.name} onChange={set("name")} data-testid="register-name-input" className="rounded-sm h-11" />
                </div>
                <div className="grid gap-2">
                  <Label>{t("login.email")}</Label>
                  <Input required type="email" value={form.email} onChange={set("email")} data-testid="register-email-input" className="rounded-sm h-11" />
                </div>
                <div className="grid gap-2">
                  <Label>{t("login.password")}</Label>
                  <Input required type="password" minLength={6} value={form.password} onChange={set("password")} data-testid="register-password-input" className="rounded-sm h-11" />
                </div>
                <div className="grid gap-2">
                  <Label className="flex items-center gap-2 text-xs text-muted-foreground">
                    <Gift className="h-3 w-3" />
                    {t("login.ref_label")}
                  </Label>
                  <Input value={form.ref} onChange={set("ref")} data-testid="register-ref-input" placeholder="CP-XXXXXX" className="rounded-sm h-11 font-mono uppercase" />
                </div>
                <Button type="submit" disabled={busy} data-testid="register-submit-btn" className="rounded-sm h-11 hover:bg-orange-600 hover:text-white">
                  {busy ? t("login.registering") : t("login.register_submit")}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
          )}

          {/* Accès démo — 1 clic */}
          <div className="mt-8 border-t border-border pt-6" data-testid="demo-access-panel">
            <div className="flex items-center gap-2 mb-3">
              <Sparkles className="h-4 w-4 text-primary" />
              <p className="overline">{t("login.demo_over")}</p>
            </div>
            <p className="text-xs text-muted-foreground mb-3">
              {t("login.demo_desc")}
            </p>
            <div className="grid gap-2">
              {DEMO_ACCOUNTS.map((acc) => (
                <button key={acc.email} onClick={demoLogin(acc)} disabled={busy}
                        data-testid={`demo-login-${acc.email.split("@")[0]}`}
                        className={`text-left border rounded-sm p-2 hover:bg-secondary/40 disabled:opacity-40 disabled:cursor-not-allowed ${acc.color}`}>
                  <p className="text-xs font-bold">{acc.label}</p>
                  <p className="text-[10px] text-muted-foreground num">{acc.email}</p>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
