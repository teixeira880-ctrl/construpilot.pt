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
  `Je viens de tester ConstruPilot pour estimer mes travaux 🛠️\n\n` +
  `Avec mon code parrainage ${code}, tu obtiens 5 € offerts sur ton premier achat 👇`;

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

  if (!user) return <div className="surface p-10 text-center">Connectez-vous pour inviter des amis.</div>;

  const code = data?.code || "…";
  const link = `${window.location.origin}/inscription?ref=${code}`;
  const text = SHARE_TEXT(code);

  const copy = async (v, label = "Lien") => {
    try { await navigator.clipboard.writeText(v); setCopied(true); setTimeout(() => setCopied(false), 1500); toast.success(label + " copié"); }
    catch { toast.error("Cópia impossível"); }
  };

  const share = (channel) => {
    const encoded = encodeURIComponent(text + "\n" + link);
    const urls = {
      whatsapp: `https://wa.me/?text=${encoded}`,
      facebook: `https://www.facebook.com/sharer/sharer.php?u=${encodeURIComponent(link)}&quote=${encodeURIComponent(text)}`,
      twitter: `https://twitter.com/intent/tweet?text=${encoded}`,
      email: `mailto:?subject=${encodeURIComponent("Découvre ConstruPilot")}&body=${encoded}`,
      sms: `sms:?&body=${encoded}`,
    };
    window.open(urls[channel], "_blank", "noopener");
  };

  const sendEmails = async () => {
    const list = emails.split(/[,;\s]+/).filter((e) => /@/.test(e));
    if (!list.length) return toast.error("Ajoutez au moins un email");
    setBusy(true);
    // Utilise mailto: en fallback simple (envoi par l'utilisateur)
    const body = encodeURIComponent(text + "\n\n" + link);
    window.open(`mailto:${list.join(",")}?subject=${encodeURIComponent("Découvre ConstruPilot — 5 € offerts")}&body=${body}`, "_blank");
    setBusy(false);
    setEmails("");
    toast.success("Client email ouvert");
  };

  return (
    <div className="grid gap-10">
      <SectionTitle over="Parrainage ConstruPilot" title="Invitez, gagnez 5 € par filleul converti">
        Envoyez votre lien à un ami en pleine rénovation. Il obtient <b className="text-primary">5 € de réduction</b> sur son premier achat, vous récupérez <b className="text-primary">5 € de crédit</b> ConstruPilot dès sa conversion.
      </SectionTitle>

      <div className="grid md:grid-cols-3 gap-6">
        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2"><Gift className="h-5 w-5 text-primary" /><p className="overline">Votre code</p></div>
          <div className="flex items-center gap-2">
            <Badge className="rounded-sm bg-primary text-primary-foreground num tracking-widest text-lg py-2 px-4" data-testid="invite-code">{code}</Badge>
            <Button size="sm" variant="outline" onClick={() => copy(code, "Code")} className="rounded-sm gap-1"><Copy className="h-3 w-3" /></Button>
          </div>
        </div>
        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2"><Users className="h-5 w-5 text-primary" /><p className="overline">Filleuls invités</p></div>
          <p className="num font-display text-3xl font-extrabold">{data?.invited || 0}</p>
        </div>
        <div className="surface p-6 grid gap-3">
          <div className="flex items-center gap-2"><Sparkles className="h-5 w-5 text-primary" /><p className="overline">Crédit accumulé</p></div>
          <p className="num font-display text-3xl font-extrabold text-primary">{data?.credit_eur?.toFixed(2) || "0.00"} €</p>
        </div>
      </div>

      <div className="surface p-6 grid gap-4" data-testid="invite-share-card">
        <p className="overline">Partager sur mes réseaux</p>
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
          <Button variant="outline" onClick={() => copy(link, "Lien")} data-testid="share-copy" className="rounded-sm gap-2">
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />} Copier
          </Button>
        </div>
      </div>

      <div className="surface p-6 grid gap-4">
        <p className="overline">Envoyer par email à mes contacts</p>
        <div className="flex flex-wrap gap-2">
          <Input value={emails} onChange={(e) => setEmails(e.target.value)}
                 placeholder="marie@example.com, paul@example.com, sophie@…"
                 data-testid="invite-emails" className="rounded-sm flex-1 min-w-[280px]" />
          <Button onClick={sendEmails} disabled={busy} data-testid="invite-send-emails" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
            <Send className="h-4 w-4" /> Envoyer
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">Ouvre votre client de messagerie avec le message pré-rempli. Séparez les adresses par des virgules.</p>
      </div>
    </div>
  );
}
