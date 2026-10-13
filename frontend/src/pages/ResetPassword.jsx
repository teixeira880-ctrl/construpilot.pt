import { useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { ArrowLeft, KeyRound, MailCheck, ShieldCheck } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

export default function ResetPassword() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [busy, setBusy] = useState(false);

  const askReset = async (e) => {
    e.preventDefault();
    setBusy(true);
    try {
      await api.post("/auth/forgot-password", { email });
      setSent(true);
    } catch {
      toast.error("Pedido impossível — tente novamente");
    } finally { setBusy(false); }
  };

  const doReset = async (e) => {
    e.preventDefault();
    if (pwd.length < 8) return toast.error("Palavra-passe: 8 caracteres mínimo");
    if (pwd !== confirm) return toast.error("A confirmação não corresponde");
    setBusy(true);
    try {
      await api.post("/auth/reset-password", { token, new_password: pwd });
      toast.success("Palavra-passe reinicializada — inicie sessão");
      navigate("/login");
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error(typeof d === "string" ? d : "Reinício impossível");
    } finally { setBusy(false); }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6" data-testid="reset-password-page">
      <div className="w-full max-w-md">
        <Link to="/login" className="text-xs text-muted-foreground hover:text-primary flex items-center gap-1 mb-8"
              data-testid="back-login-link">
          <ArrowLeft className="h-3 w-3" /> Voltar ao início de sessão
        </Link>

        {token ? (
          <form onSubmit={doReset} className="surface p-6 space-y-4" data-testid="reset-form">
            <h1 className="font-display text-2xl font-bold flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-primary" /> Nova palavra-passe
            </h1>
            <div className="grid gap-1.5">
              <Label htmlFor="rp-pwd" className="text-xs">Nova palavra-passe (8 caracteres mín.)</Label>
              <Input id="rp-pwd" type="password" value={pwd} required minLength={8}
                     onChange={(e) => setPwd(e.target.value)}
                     data-testid="reset-new-password-input" className="rounded-sm h-11" />
            </div>
            <div className="grid gap-1.5">
              <Label htmlFor="rp-conf" className="text-xs">Confirmer</Label>
              <Input id="rp-conf" type="password" value={confirm} required
                     onChange={(e) => setConfirm(e.target.value)}
                     data-testid="reset-confirm-password-input" className="rounded-sm h-11" />
            </div>
            <Button type="submit" disabled={busy} className="rounded-sm w-full h-11 gap-2"
                    data-testid="reset-submit-btn">
              <ShieldCheck className="h-4 w-4" /> {busy ? "…" : "Reiniciar a minha palavra-passe"}
            </Button>
            <p className="text-[10px] text-muted-foreground">
              Todas as suas sessões serão desconectadas por segurança.
            </p>
          </form>
        ) : sent ? (
          <div className="surface p-6 space-y-3 text-center" data-testid="reset-email-sent">
            <MailCheck className="h-10 w-10 text-primary mx-auto" />
            <h1 className="font-display text-xl font-bold">Email enviado</h1>
            <p className="text-sm text-muted-foreground">
              Se existir uma conta para <b>{email}</b>, receberá um link de redefinição válido por 1 hora. Não se esqueça de verificar o spam.
            </p>
          </div>
        ) : (
          <form onSubmit={askReset} className="surface p-6 space-y-4" data-testid="forgot-form">
            <h1 className="font-display text-2xl font-bold flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-primary" /> Palavra-passe esquecida
            </h1>
            <p className="text-sm text-muted-foreground">
              Indique o seu email: enviaremos um link seguro para escolher uma nova palavra-passe.
            </p>
            <div className="grid gap-1.5">
              <Label htmlFor="rp-email" className="text-xs">Email da sua conta</Label>
              <Input id="rp-email" type="email" value={email} required
                     onChange={(e) => setEmail(e.target.value)}
                     data-testid="forgot-email-input" className="rounded-sm h-11" />
            </div>
            <Button type="submit" disabled={busy} className="rounded-sm w-full h-11"
                    data-testid="forgot-submit-btn">
              {busy ? "…" : "Enviar-me o link de reinicialização"}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
