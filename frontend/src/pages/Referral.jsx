import { useEffect, useState } from "react";
import { toast } from "sonner";
import { Copy, Gift, Users, Sparkles, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api, eur } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SectionTitle, Stat } from "@/components/Bits";

export default function Referral() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.get("/referral/me").then(({ data }) => setData(data)).catch(() => {});
  }, [user]);

  if (!user) {
    return (
      <div className="surface p-10 text-center">
        <p className="font-display text-2xl font-bold mb-2">Connectez-vous pour votre lien de parrainage</p>
      </div>
    );
  }

  const shareUrl = `${window.location.origin}/inscription?ref=${data?.code || ""}`;

  const copy = async (val, label) => {
    try {
      await navigator.clipboard.writeText(val);
      setCopied(true);
      toast.success(`${label} copié`);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      toast.error("Cópia impossível");
    }
  };

  return (
    <div className="grid gap-10">
      <SectionTitle over="Parrainage ConstruPilot" title="Invitez, gagnez 5 € par filleul">
        Chaque personne qui s'inscrit avec votre code et réalise un premier paiement vous
        rapporte <b className="text-primary">5 € de crédit</b>. En échange, votre filleul
        bénéficie de <b className="text-primary">5 € de réduction</b> sur son premier achat.
      </SectionTitle>

      <div className="grid md:grid-cols-3 gap-6" data-testid="referral-stats">
        <Stat icon={Gift} label="Votre code" value={data?.code || "…"} suffix="" />
        <Stat icon={Users} label="Filleuls" value={data?.invited || 0} />
        <Stat icon={Sparkles} label="Crédit accumulé" value={eur(data?.credit_eur || 0)} />
      </div>

      <div className="surface p-6 grid gap-5">
        <div>
          <p className="overline mb-2">Votre lien à partager</p>
          <div className="flex flex-wrap gap-2">
            <Input readOnly value={shareUrl} data-testid="referral-share-url" className="rounded-sm font-mono text-xs" />
            <Button onClick={() => copy(shareUrl, "Lien")} data-testid="referral-copy-link" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              Copier
            </Button>
          </div>
        </div>
        <div>
          <p className="overline mb-2">Ou partagez directement votre code</p>
          <div className="flex items-center gap-3">
            <Badge className="rounded-sm bg-primary text-primary-foreground num text-lg py-2 px-4 tracking-wider" data-testid="referral-code">
              {data?.code || "…"}
            </Badge>
            <Button variant="outline" size="sm" onClick={() => copy(data?.code || "", "Code")} className="rounded-sm gap-2">
              <Copy className="h-3 w-3" /> Copier le code
            </Button>
          </div>
        </div>
      </div>

      <div className="surface p-6 grid gap-4">
        <p className="font-display font-bold text-lg">Comment ça marche</p>
        <ol className="grid gap-3 text-sm">
          <li className="flex gap-3">
            <span className="num h-6 w-6 rounded-full bg-primary/15 text-primary grid place-items-center text-xs font-bold shrink-0">1</span>
            <span>Partagez votre lien à vos proches en pleine rénovation.</span>
          </li>
          <li className="flex gap-3">
            <span className="num h-6 w-6 rounded-full bg-primary/15 text-primary grid place-items-center text-xs font-bold shrink-0">2</span>
            <span>Ils créent leur compte via votre lien et démarrent leur projet.</span>
          </li>
          <li className="flex gap-3">
            <span className="num h-6 w-6 rounded-full bg-primary/15 text-primary grid place-items-center text-xs font-bold shrink-0">3</span>
            <span>Dès leur premier paiement (Premium ou Project Pass), ils obtiennent 5 € de réduction et vous recevez 5 € de crédit ConstruPilot.</span>
          </li>
        </ol>
      </div>
    </div>
  );
}
