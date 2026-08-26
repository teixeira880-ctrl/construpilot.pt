import { useNavigate, useSearchParams } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { BadgeCheck, FileText, Receipt, Layers, Users, ArrowRight, Lock } from "lucide-react";

const FEATURES = [
  { icon: FileText, label: "Devis illimités", desc: "Créez, envoyez et faites signer vos devis en ligne." },
  { icon: Receipt, label: "Factures & Factur-X", desc: "Facturez vos clients et suivez les paiements." },
  { icon: Layers, label: "Situations de travaux", desc: "Avancement de chantier et facturation progressive." },
  { icon: Users, label: "Espace Entreprise & RH", desc: "Équipe, pointage, catalogue de prix, clients (CRM)." },
];

export default function ProUpsell() {
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const analyse = sp.get("feature") === "analyse";
  return (
    <div className="max-w-3xl mx-auto px-4 py-12" data-testid="pro-upsell-page">
      <Card className="p-8 sm:p-10 text-center relative overflow-hidden">
        <div className="absolute inset-x-0 top-0 h-1.5 bg-primary" />
        <div className="mx-auto h-16 w-16 rounded-full bg-primary/10 grid place-items-center mb-5">
          <Lock className="h-8 w-8 text-primary" />
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold">
          {analyse ? "Fonction réservée aux abonnés" : "Fonction réservée aux professionnels"}
        </h1>
        <p className="text-muted-foreground mt-3 max-w-xl mx-auto">
          {analyse
            ? "L'analyse de devis est incluse dans nos abonnements. Souscrivez un forfait (particulier ou pro) pour vérifier vos devis reçus et détecter les écarts de prix."
            : (<>Cette section (devis, factures, chantiers, entreprise…) est réservée aux comptes <b>Pro</b> et <b>Pro Business</b>. En tant que particulier, vous gardez l'accès à l'estimateur de travaux et à vos devis reçus.</>)}
        </p>

        <div className="grid sm:grid-cols-2 gap-3 mt-8 text-left">
          {FEATURES.map((f, i) => (
            <div key={i} className="flex items-start gap-3 border border-border rounded-lg p-4" data-testid={`pro-feature-${i}`}>
              <span className="h-9 w-9 rounded-md bg-primary/10 grid place-items-center shrink-0">
                <f.icon className="h-5 w-5 text-primary" />
              </span>
              <div>
                <p className="font-semibold text-sm">{f.label}</p>
                <p className="text-xs text-muted-foreground">{f.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center mt-8">
          <Button size="lg" className="gap-2" onClick={() => nav("/tarifs")} data-testid="pro-upsell-upgrade">
            <BadgeCheck className="h-5 w-5" /> Passer en compte Pro <ArrowRight className="h-4 w-4" />
          </Button>
          <Button size="lg" variant="outline" onClick={() => nav("/dashboard")} data-testid="pro-upsell-back">
            Retour au tableau de bord
          </Button>
        </div>
      </Card>
    </div>
  );
}
