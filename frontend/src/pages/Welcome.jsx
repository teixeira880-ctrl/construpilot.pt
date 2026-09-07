import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Hammer, Ruler, FileText, ArrowRight, ArrowLeft, CheckCircle2, Rocket } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const STEPS = [
  {
    icon: Rocket,
    title: "Bem-vindo(a) ao ConstruPilot 🎉",
    text: "A tua conta está ativa — e 100% gratuita durante a fase de lançamento. Sejas particular ou profissional, veja como começar em poucos passos.",
  },
  {
    icon: Hammer,
    title: "1. Estima o custo da tua obra",
    text: "Particular ou profissional: descreve o teu projeto em linguagem natural («renovar uma casa de 90 m²») e obtém uma estimativa detalhada, rubrica a rubrica, ao instante.",
    cta: { label: "Estimar a minha obra", to: "/estimation" },
  },
  {
    icon: Ruler,
    title: "2. Mede uma planta e orçamenta",
    text: "Importa uma planta (PDF, foto ou DWG), deixa a IA detetar os compartimentos e as áreas, e obtém a medição automaticamente.",
    cta: { label: "Medir uma planta", to: "/plan" },
  },
  {
    icon: FileText,
    title: "3. Cria e envia um orçamento profissional",
    text: "Para profissionais: gera um orçamento com a tua imagem, adiciona um cliente, aplica os teus preços e envia por email — tudo num único sítio.",
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
          {step === 0 && user?.name ? `Bem-vindo(a), ${user.name.split(" ")[0]} 🎉` : s.title}
        </h1>
        <p className="mt-4 text-sm text-muted-foreground leading-relaxed">{s.text}</p>

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
            {step === 0 ? "Ignorar" : (<><ArrowLeft className="h-3 w-3" /> Anterior</>)}
          </button>

          {last ? (
            <Button className="rounded-lg gap-2 hover:bg-orange-600 hover:text-white"
                    onClick={() => nav("/dashboard")} data-testid="welcome-finish">
              <CheckCircle2 className="h-4 w-4" /> Ir para o painel
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
