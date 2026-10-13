import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Hammer, Ruler, FileText, ArrowRight, ArrowLeft, CheckCircle2, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { OfferNotice } from "@/components/OfferNotice";

const STEPS = [
  {
    icon: Rocket,
    title: "Bem-vindo ao ConstruPilot 🎉",
    text: "A sua conta está ativa. Seja particular ou profissional, eis como começar em poucos passos.",
    offer: true,
  },
  {
    icon: Hammer,
    title: "1. Estime o custo dos seus trabalhos",
    text: "Particular ou profissional: descreva o seu projeto em linguagem natural («renovar uma casa de 90 m²») e obtenha uma estimativa detalhada, item por item, instantaneamente.",
    cta: { label: "Estimar a minha obra", to: "/estimation" },
  },
  {
    icon: Ruler,
    title: "2. Meça uma planta e orçamente",
    text: "Importe uma planta (PDF, foto ou DWG), deixe a IA detetar as divisões e as superfícies, depois obtenha as medições automaticamente.",
    cta: { label: "Editor de plantas", to: "/plan" },
  },
  {
    icon: FileText,
    title: "3. Crie e envie um orçamento profissional",
    text: "Para os profissionais: gere um orçamento com a sua imagem, adicione um cliente, aplique os seus preços e envie-o por email — tudo a partir de um único local.",
    cta: { label: "Criar um orçamento", to: "/devis-editeur" },
  },
];

export default function Welcome() {
  const nav = useNavigate();
  const { user } = useAuth();
  const [step, setStep] = useState(0);

  // Ne montrer le parcours qu'une seule fois : on retire le flag dès l'arrivée
  useEffect(() => { sessionStorage.removeItem("construpilot_new_signup"); }, []);

  const s = STEPS[step];
  const last = step === STEPS.length - 1;
  const Icon = s.icon;

  return (
    <div className="min-h-[80vh] flex items-center justify-center px-5 py-12" data-testid="welcome-page">
      <div className="w-full max-w-lg surface p-8 lg:p-10 text-center">
        {/* progression */}
        <div className="flex items-center justify-center gap-2 mb-8" data-testid="welcome-progress">
          {STEPS.map((_, i) => (
            <span key={i}
                  className={`h-1.5 rounded-full transition-all ${i === step ? "w-8 bg-primary" : i < step ? "w-4 bg-primary/50" : "w-4 bg-border"}`} />
          ))}
        </div>

        <div className="mx-auto mb-6 h-14 w-14 rounded-2xl bg-primary/10 flex items-center justify-center">
          <Icon className="h-7 w-7 text-primary" />
        </div>

        <h1 className="font-display text-2xl lg:text-3xl font-bold tracking-tight" data-testid="welcome-title">
          {step === 0 && user?.name ? `Bem-vindo, ${user.name.split(" ")[0]} 🎉` : s.title}
        </h1>
        <p className="mt-4 text-sm text-muted-foreground leading-relaxed">{s.text}</p>
        {s.offer && <OfferNotice className="mt-4 text-left" />}

        {s.cta && (
          <Button variant="outline" className="mt-6 rounded-lg gap-2"
                  onClick={() => nav(s.cta.to)} data-testid="welcome-step-cta">
            {s.cta.label} <ArrowRight className="h-4 w-4" />
          </Button>
        )}

        <div className="mt-10 flex items-center justify-between gap-3">
          <button
            onClick={() => (step === 0 ? nav("/dashboard") : setStep((v) => v - 1))}
            className="text-sm text-muted-foreground hover:text-foreground inline-flex items-center gap-1"
            data-testid="welcome-back">
            {step === 0 ? "Passar" : (<><ArrowLeft className="h-3 w-3" /> Anterior</>)}
          </button>

          {last ? (
            <Button className="rounded-lg gap-2 hover:bg-orange-600 hover:text-white"
                    onClick={() => nav("/dashboard")} data-testid="welcome-finish">
              <CheckCircle2 className="h-4 w-4" /> Ir para o painel de controlo
            </Button>
          ) : (
            <Button className="rounded-lg gap-2 hover:bg-orange-600 hover:text-white"
                    onClick={() => setStep((v) => v + 1)} data-testid="welcome-next">
              Seguinte <ArrowRight className="h-4 w-4" />
            </Button>
          )}
        </div>
      </div>
    </div>
  );
}
