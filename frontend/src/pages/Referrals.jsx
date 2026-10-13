import { useEffect, useState } from "react";
import { Gift, Copy, Check, Users, TrendingUp, Share2, Mail } from "lucide-react";
import { toast } from "sonner";
import { SEO } from "@/components/SEO";
import { SectionTitle } from "@/components/Bits";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";

export default function Referrals() {
  const [data, setData] = useState(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(true);

  useEffect(() => {
    api.get("/referrals/me")
      .then(({ data }) => setData(data))
      .catch(() => toast.error("Impossible de charger votre parrainage"))
      .finally(() => setBusy(false));
  }, []);

  const copy = () => {
    if (!data?.share_url) return;
    navigator.clipboard.writeText(data.share_url);
    setCopied(true);
    toast.success("Lien copié !");
    setTimeout(() => setCopied(false), 2000);
  };

  const shareWhatsapp = () => {
    if (!data?.share_url) return;
    const text = `Salut ! J'utilise ConstruPilot pour chiffrer mes chantiers en 30 s. Essaie avec mon lien : ${data.share_url}`;
    window.open(`https://wa.me/?text=${encodeURIComponent(text)}`, "_blank");
  };

  const shareEmail = () => {
    if (!data?.share_url) return;
    const body = `Bonjour,\n\nJe pense que ConstruPilot pourrait vous intéresser — c'est un assistant IA pour chiffrer des travaux et générer des devis en 30 secondes.\n\nEssayez avec mon lien de parrainage :\n${data.share_url}\n\nÀ bientôt.`;
    window.location.href = `mailto:?subject=${encodeURIComponent("Découvrez ConstruPilot")}&body=${encodeURIComponent(body)}`;
  };

  if (busy) return <div className="grid gap-10"><SectionTitle title="Chargement…" /></div>;
  if (!data) return <div className="grid gap-10"><SectionTitle title="Erreur de chargement" /></div>;

  const progress = Math.min(100, (data.bonus_days_earned / data.bonus_days_cap) * 100);
  const monthsEarned = Math.floor(data.bonus_days_earned / 30);

  return (
    <div className="grid gap-10">
      <SEO
        title="Parrainage — 30 jours Pro offerts par filleul"
        description="Invitez vos confrères artisans sur ConstruPilot et gagnez 30 jours Pro gratuits pour chaque inscription, jusqu'à 12 mois d'abonnement offert."
        keywords="parrainage ConstruPilot, invitation ami, filleul, référent, mois Pro offert, programme récompense"
        canonical="/parrainage"
      />
      <SectionTitle as="h1" over="Programme de parrainage"
        title={`Parrainez vos confrères, gagnez ${data.bonus_days_cap / 30} mois Pro`}>
        <span>
          Pour chaque artisan que vous invitez, nous vous offrons{" "}
          <b className="text-primary">30 jours Pro gratuits</b> (plafond{" "}
          {data.bonus_days_cap} jours = {data.bonus_days_cap / 30} mois).
        </span>
      </SectionTitle>

      {/* Card 1 : Share code */}
      <section className="surface p-6 lg:p-8 grid gap-4 border-primary/40" data-testid="referral-code-card">
        <div className="flex items-center gap-3">
          <span className="h-10 w-10 grid place-items-center rounded-sm bg-primary/15 text-primary">
            <Gift className="h-5 w-5" />
          </span>
          <div>
            <p className="overline">Votre lien de parrainage</p>
            <p className="font-display font-bold text-xl mt-1" data-testid="referral-code">
              {data.code}
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2">
          <input
            readOnly
            value={data.share_url}
            data-testid="referral-share-input"
            className="rounded-sm border border-border bg-background px-3 h-11 text-sm font-mono"
          />
          <Button onClick={copy} data-testid="referral-copy-btn"
                  className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white h-11">
            {copied ? <><Check className="h-4 w-4" /> Copié</> : <><Copy className="h-4 w-4" /> Copier</>}
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-2 mt-2">
          <Button variant="outline" onClick={shareWhatsapp} data-testid="referral-share-whatsapp"
                  className="rounded-sm gap-2 h-11">
            <Share2 className="h-4 w-4" /> WhatsApp
          </Button>
          <Button variant="outline" onClick={shareEmail} data-testid="referral-share-email"
                  className="rounded-sm gap-2 h-11">
            <Mail className="h-4 w-4" /> Email
          </Button>
        </div>
      </section>

      {/* Card 2 : Stats */}
      <section className="grid md:grid-cols-3 gap-4" data-testid="referral-stats">
        <StatBig icon={Users} value={data.total_referrals} label="Filleuls inscrits"
                 testid="referral-stat-count" />
        <StatBig icon={TrendingUp} value={`${data.bonus_days_earned} jours`}
                 label={`${monthsEarned} mois Pro offert${monthsEarned > 1 ? "s" : ""}`}
                 testid="referral-stat-days" />
        <StatBig icon={Gift} value={`${data.bonus_days_cap - data.bonus_days_earned} jours`}
                 label="Restants au plafond" testid="referral-stat-remaining" />
      </section>

      {/* Progress bar */}
      <section className="surface p-6">
        <div className="flex justify-between items-baseline mb-3">
          <p className="overline">Progression vers 12 mois offerts</p>
          <p className="num text-primary font-bold">
            {data.bonus_days_earned} / {data.bonus_days_cap} j
          </p>
        </div>
        <div className="h-3 bg-secondary rounded-sm overflow-hidden">
          <div className="h-full bg-primary transition-all duration-700"
               style={{ width: `${progress}%` }}
               data-testid="referral-progress-bar" />
        </div>
      </section>

      {/* Recent referrals */}
      {data.recent_referrals?.length > 0 && (
        <section className="surface p-6" data-testid="referral-list">
          <p className="overline mb-4">Vos filleuls récents</p>
          <div className="grid gap-2">
            {data.recent_referrals.map((r, i) => (
              <div key={i} className="flex items-center justify-between py-2 border-b border-border last:border-0"
                   data-testid={`referral-row-${i}`}>
                <div>
                  <p className="font-bold text-sm">{r.name || "Filleul"}</p>
                  <p className="text-[11px] text-muted-foreground">{r.email_masked}</p>
                </div>
                <span className="text-[10px] text-muted-foreground num">
                  {r.joined_at ? new Date(r.joined_at).toLocaleDateString("fr-FR") : "—"}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* How it works */}
      <section className="surface p-6" data-testid="referral-howitworks">
        <p className="overline mb-4">Comment ça marche</p>
        <ol className="grid gap-3 text-sm">
          <li className="flex gap-3">
            <span className="h-6 w-6 shrink-0 grid place-items-center bg-primary text-white text-xs font-bold rounded-sm">1</span>
            Copiez votre lien unique ci-dessus et partagez-le avec vos confrères artisans.
          </li>
          <li className="flex gap-3">
            <span className="h-6 w-6 shrink-0 grid place-items-center bg-primary text-white text-xs font-bold rounded-sm">2</span>
            Chaque personne qui s'inscrit via votre lien vous crédite automatiquement de{" "}
            <b>+30 jours Pro</b>.
          </li>
          <li className="flex gap-3">
            <span className="h-6 w-6 shrink-0 grid place-items-center bg-primary text-white text-xs font-bold rounded-sm">3</span>
            Jusqu'à <b>12 mois d'abonnement Pro offerts</b> (plafond 360 jours).
          </li>
        </ol>
      </section>
    </div>
  );
}

function StatBig({ icon: Icon, value, label, testid }) {
  return (
    <div className="surface p-5 flex items-center gap-4" data-testid={testid}>
      <span className="h-12 w-12 grid place-items-center rounded-sm bg-primary/15 text-primary">
        <Icon className="h-5 w-5" />
      </span>
      <div>
        <p className="num font-display text-2xl font-extrabold leading-none">{value}</p>
        <p className="text-[10px] uppercase tracking-widest text-muted-foreground mt-1">
          {label}
        </p>
      </div>
    </div>
  );
}
