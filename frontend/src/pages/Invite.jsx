import { useEffect, useState } from "react";
import { toast } from "sonner";
import { MessageCircle, Facebook, Mail, Send, Copy, Sparkles, Users, Gift, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SectionTitle } from "@/components/Bits";

const SHARE_TEXT = (code) =>
  `Acabei de testar o ConstruPilot para estimar as minhas obras 🛠️\n\n` +
  `Com o meu código de referência ${code}, recebes 5 € de oferta na tua primeira compra 👇`;

export default function Invite() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [emails, setEmails] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.get("/referral/me").then(({ data }) => setData(data)).catch(() => {});
  }, [user]);

  if (!user) return <div className="surface p-10 text-center">Ligue-se para convidar amigos.</div>;

  const code = data?.code || "…";
  const link = `${window.location.origin}/inscription?ref=${code}`;
  const text = SHARE_TEXT(code);

  const copy = async (v, label = "Ligação") => {
    try { await navigator.clipboard.writeText(v); setCopied(true); setTimeout(() => setCopied(false), 1500); toast.success(label + " copiado"); }
    catch { toast.error("Cópia impossível"); }
  };

  const share = (channel) => {
    const encoded = encodeURIComponent(text + "\n" + link);
    const urls = {
      whatsapp: `https://wa.me/?text=${encoded}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(link)}&quote=${encodeURIComponent(text)}`,
      twitter: `https://twitter.com/intent/tweet?text=${encoded}`,
      email: `mailto:?subject=${encodeURIComponent("Descobre ConstruPilot")}&body=${encoded}`,
      sms: `sms:?&body=${encoded}`,
    };
    window.open(urls[channel], "_blank", "noopener");
  };

  const sendEmails = async () => {
    const list = emails.split(/[,;\s]+/).filter((e) => /@/.test(e));
    if (!list.length) return toast.error("Adicione pelo menos um e-mail");
    setBusy(true);
    // Utilise mailto: en fallback simple (envoi par l'utilisateur)
    const body = encodeURIComponent(text + "\n\n" + link);
    window.open(`mailto:${list.join(",")}?subject=${encodeURIComponent("Descobre ConstruPilot — 5 € oferecidos")}&body=${body}`, "_blank");
    setBusy(false);
    setEmails("");
    toast.success("E-mail do cliente aberto");
  };

  return (
    <div className="grid gap-10">
      <SectionTitle over="Recomendação ConstruPilot" title="Convide, ganhe 5 € por indicado convertido">
        Envie a sua ligação a um amigo em plena renovação. Ele obtém <b className="text-primary">5 € de desconto</b> na sua primeira compra, recupera <b className="text-primary">5 € de crédito</b> ConstruPilot desde a sua conversão.
      </SectionTitle>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2"><Gift className="h-5 w-5 text-primary" /><p className="overline">O seu código</p></div>
          <div className="flex items-center gap-2">
            <Badge className="rounded-sm bg-primary text-primary-foreground num tracking-widest text-lg py-2 px-4" data-testid="invite-code">{code}</Badge>
            <Button size="sm" variant="outline" onClick={() => copy(code, "Código")} className="rounded-sm gap-1"><Copy className="h-3 w-3" /></Button>
          </div>
        </div>
        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2"><Users className="h-5 w-5 text-primary" /><p className="overline">Afilhados convidados</p></div>
          <p className="num font-display text-3xl font-extrabold">{data?.invited || 0}</p>
        </div>
        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-primary" /><p className="overline">Crédito acumulado</p></div>
          <p className="num font-display text-3xl font-extrabold text-primary">{data?.credit_eur?.toFixed(2) || "0.00"} €</p>
        </div>
      </div>

      <div className="surface p-6 grid gap-4" data-testid="invite-share-card">
        <p className="overline">Partilhar nas minhas redes</p>
        <div className="border border-border rounded-sm p-4 bg-secondary/30">
          <p className="text-sm whitespace-pre-line">{text}</p>
          <p className="text-xs text-primary mt-3 font-mono truncate">{link}</p>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          <Button variant="outline" onClick={() => share("whatsapp")} data-testid="share-whatsapp" className="rounded-sm gap-2 border-emerald-500/40 text-emerald-600 hover:bg-emerald-500 hover:text-white">
            <MessageCircle className="h-4 w-4" /> WhatsApp
          </Button>
          <Button variant="outline" onClick={() => share("facebook")} data-testid="share-facebook" className="rounded-sm gap-2 border-blue-500/40 text-blue-600 hover:bg-blue-500 hover:text-white">
            <Facebook className="h-4 w-4" /> Facebook
          </Button>
          <Button variant="outline" onClick={() => share("twitter")} data-testid="share-twitter" className="rounded-sm gap-2">
            <Send className="h-4 w-4" /> X
          </Button>
          <Button variant="outline" onClick={() => share("email")} data-testid="share-email" className="rounded-sm gap-2">
            <Mail className="h-4 w-4" /> Email
          </Button>
          <Button variant="outline" onClick={() => copy(link, "Ligação")} data-testid="share-copy" className="rounded-sm gap-2">
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} Copiar
          </Button>
        </div>
      </div>

      <div className="surface p-6 grid gap-4">
        <p className="overline">Enviar por email aos meus contactos</p>
        <div className="flex flex-wrap gap-2">
          <Input value={emails} onChange={(e) => setEmails(e.target.value)}
                 placeholder="maria@exemplo.pt, paulo@exemplo.pt, sofia@…"
                 data-testid="invite-emails" className="rounded-sm flex-1 min-w-[280px]" />
          <Button onClick={sendEmails} disabled={busy} data-testid="invite-send-emails" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Send className="h-4 w-4" /> Enviar
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Abre o seu cliente de e-mail com a mensagem pré-preenchida. Separe os endereços por vírgulas.</p>
      </div>
    </div>
  );
}
