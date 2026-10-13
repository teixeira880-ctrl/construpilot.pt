import { useState } from "react";
import { Mail, Loader2, Check } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useI18n } from "@/context/I18nContext";
import { toast } from "sonner";

export default function NewsletterForm({ source = "blog", compact = false }) {
  const { lang } = useI18n();
  const isPT = lang === "pt";
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    if (!email.trim()) return;
    setBusy(true);
    try {
      const { data } = await api.post("/newsletter/subscribe", { email: email.trim(), lang: isPT ? "pt" : "fr", source });
      setDone(true);
      toast.success(data.already ? (isPT ? "Já está subscrito" : "Já tem subscrição") : (isPT ? "Subscrição confirmada" : "Inscrição confirmada — até breve!"));
    } catch (err) {
      toast.error(err?.response?.data?.detail || (isPT ? "Erro na subscrição" : "Inscrição impossível"));
    } finally { setBusy(false); }
  };

  return (
    <div className={`surface border-primary/30 ${compact ? "p-4" : "p-6"} rounded-md`} data-testid="newsletter-form">
      <div className="flex items-start gap-3">
        <span className="h-9 w-9 rounded-full bg-primary/15 grid place-items-center shrink-0"><Mail className="h-4 w-4 text-primary" /></span>
        <div className="flex-1">
          <p className="font-display font-bold">{isPT ? "Receba os novos guias por email" : "Receba os novos guias por e-mail"}</p>
          <p className="text-xs text-muted-foreground mt-0.5">
            {isPT ? "Preços, métodos, IVA, orçamentos — um email por artigo, sem spam." : "Preços de obras, métodos, IVA, orçamentos — um e-mail por novo artigo, zero spam."}
          </p>
          {done ? (
            <p className="mt-3 text-sm text-emerald-600 flex items-center gap-1" data-testid="newsletter-done"><Check className="h-4 w-4" /> {isPT ? "Obrigado! Verifique a sua caixa de entrada." : "Obrigado! Verifique a sua caixa de entrada."}</p>
          ) : (
            <form onSubmit={submit} className="mt-3 flex gap-2 flex-wrap">
              <Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="voce@empresa.pt"
                     className="h-10 flex-1 min-w-[200px] rounded-sm" data-testid="newsletter-email" />
              <Button type="submit" disabled={busy} className="rounded-sm gap-2 h-10" data-testid="newsletter-submit">
                {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />} {isPT ? "Subscrever" : "Subscrever"}
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
