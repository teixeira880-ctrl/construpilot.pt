import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Hammer, ArrowLeft } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useAuth } from "@/context/AuthContext";
import { IMAGES } from "@/lib/api";

export default function Login() {
  const { login, register, user } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  if (user) navigate("/dashboard", { replace: true });

  const submit = (mode) => async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      if (mode === "login") await login(form.email, form.password);
      else await register(form.name, form.email, form.password);
      toast.success("Bienvenue chez CMRENOV AI");
      navigate("/dashboard");
    } catch (err) {
      toast.error(err?.response?.data?.detail || "Échec de la connexion");
    } finally {
      setBusy(false);
    }
  };

  const google = () => {
    // REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
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
            <span className="h-8 w-8 grid place-items-center bg-primary rounded-sm">
              <Hammer className="h-4 w-4 text-primary-foreground" />
            </span>
            <span className="font-display font-extrabold text-lg">CMRENOV<span className="text-primary"> AI</span></span>
          </Link>
          <div>
            <p className="overline">Estimez. Comparez. Construisez.</p>
            <h2 className="mt-4 font-display text-4xl font-bold tracking-tighter max-w-md">
              Des prix réels. Des conseils de pros. Un chantier mieux maîtrisé.
            </h2>
          </div>
        </div>
      </div>

      <div className="flex items-center justify-center p-6 lg:p-12">
        <div className="w-full max-w-md">
          <Link to="/" className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 mb-8" data-testid="back-home-link">
            <ArrowLeft className="h-3 w-3" /> Retour à l'accueil
          </Link>
          <h1 className="font-display text-3xl font-bold tracking-tight">Votre espace travaux</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Sauvegardez vos projets, estimations, listes de matériaux et devis.
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
            Continuer avec Google
          </Button>

          <div className="my-6 flex items-center gap-4">
            <span className="h-px flex-1 bg-border" />
            <span className="text-xs text-muted-foreground">ou par email</span>
            <span className="h-px flex-1 bg-border" />
          </div>

          <Tabs defaultValue="login">
            <TabsList className="w-full rounded-sm">
              <TabsTrigger value="login" className="flex-1 rounded-sm" data-testid="tab-login">Connexion</TabsTrigger>
              <TabsTrigger value="register" className="flex-1 rounded-sm" data-testid="tab-register">Créer un compte</TabsTrigger>
            </TabsList>

            <TabsContent value="login">
              <form onSubmit={submit("login")} className="grid gap-4 mt-6">
                <div className="grid gap-2">
                  <Label>Email</Label>
                  <Input required type="email" value={form.email} onChange={set("email")} data-testid="login-email-input" className="rounded-sm h-11" />
                </div>
                <div className="grid gap-2">
                  <Label>Mot de passe</Label>
                  <Input required type="password" value={form.password} onChange={set("password")} data-testid="login-password-input" className="rounded-sm h-11" />
                </div>
                <Button type="submit" disabled={busy} data-testid="login-submit-btn" className="rounded-sm h-11 hover:bg-orange-600 hover:text-white">
                  {busy ? "Connexion…" : "Se connecter"}
                </Button>
                <p className="text-xs text-muted-foreground">
                  Compte de démonstration : <span className="num">demo@cmrenov.fr</span> / <span className="num">Demo2026!</span>
                </p>
              </form>
            </TabsContent>

            <TabsContent value="register">
              <form onSubmit={submit("register")} className="grid gap-4 mt-6">
                <div className="grid gap-2">
                  <Label>Nom complet</Label>
                  <Input required value={form.name} onChange={set("name")} data-testid="register-name-input" className="rounded-sm h-11" />
                </div>
                <div className="grid gap-2">
                  <Label>Email</Label>
                  <Input required type="email" value={form.email} onChange={set("email")} data-testid="register-email-input" className="rounded-sm h-11" />
                </div>
                <div className="grid gap-2">
                  <Label>Mot de passe</Label>
                  <Input required type="password" minLength={6} value={form.password} onChange={set("password")} data-testid="register-password-input" className="rounded-sm h-11" />
                </div>
                <Button type="submit" disabled={busy} data-testid="register-submit-btn" className="rounded-sm h-11 hover:bg-orange-600 hover:text-white">
                  {busy ? "Création…" : "Créer mon compte gratuit"}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </div>
      </div>
    </div>
  );
}
