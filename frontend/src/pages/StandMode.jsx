import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Hammer, LayoutDashboard, MessageSquare, Sparkles, FileText, RotateCcw, ArrowRight, WifiOff, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { isDemoActive } from "@/lib/demoInterceptor";
import { isStandMode, resetStand, startStand, stopStand } from "@/lib/standMode";

const QUESTIONS = [
  "Qual é o custo estimado da Moradia Martins?",
  "Como é tratado o cálculo sísmico?",
  "Quais são as paredes portantes?",
  "Que IVA se aplica à obra?",
];

const ask = (q) => `/assistant?q=${encodeURIComponent(q)}`;

const STEPS = [
  { n: 1, icon: LayoutDashboard, title: "O projeto", to: "/dashboard",
    say: "Uma moradia T3 de 150 m² em Lisboa: a estimativa (188 962 € sem IVA) sai do motor de preços, não da IA." },
  { n: 2, icon: MessageSquare, title: "Assistente de Obra", to: ask(QUESTIONS[0]),
    say: "Pergunte em linguagem corrente: custo, sismo, paredes, IVA, licenciamento. Respostas tiradas do processo.",
    extra: QUESTIONS.slice(1) },
  { n: 3, icon: Sparkles, title: "Programa IA de opções", to: "/missions",
    say: "13 opções que o profissional escolhe: térmica, estrutura, pré-certificado, mapa de quantidades…" },
  { n: 4, icon: FileText, title: "Processo de estudo completo", href: "/demo-assets/Dossier_BET_Moradia_Martins.pdf",
    say: "Memória de cálculo, 15 desenhos de execução, medições e orçamento — pronto para o visto do engenheiro.",
    files: [["Nota de cálculo sísmica", "Nota_calculo_sismica_Moradia_Martins.pdf"],
            ["Orçamento (Excel)", "Orcamento_Moradia_Martins.xlsx"],
            ["Projeto de arquitetura", "Projeto_arquitetura_Moradia_Martins_DEMO.pdf"]] },
];

/** Página /stand — guia de 3 minutos para o stand do Web Summit, em modo offline. */
export default function StandMode() {
  const { demoLogin } = useAuth();
  const navigate = useNavigate();
  const [busy, setBusy] = useState(false);
  const active = isStandMode() && isDemoActive();

  const start = async () => {
    if (busy) return;
    setBusy(true);
    startStand();
    try { await demoLogin("pro"); } catch { /* o interceptor offline responde sempre */ }
    window.location.assign("/stand");
  };

  const leave = () => { stopStand(); navigate("/demo/entrar"); };

  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="stand-page">
      <header className="border-b border-border">
        <div className="mx-auto max-w-5xl px-5 py-4 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2"><Hammer className="h-5 w-5 text-primary" /><span className="font-display font-bold">ConstruPilot</span></Link>
          <span className="text-xs uppercase tracking-widest text-muted-foreground">Web Summit 2026 · Lisboa</span>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-5 py-10">
        <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">Demonstração em 3 minutos</h1>
        <p className="mt-3 text-base text-muted-foreground max-w-2xl">
          Da planta ao processo de estudo pronto a assinar. Funciona sem internet: dados fictícios da Moradia Martins, nada é enviado.
        </p>

        {!active && (
          <div className="mt-8 rounded-md border border-primary/30 bg-primary/5 p-6" data-testid="stand-start-block">
            <div className="flex items-start gap-3">
              <WifiOff className="h-5 w-5 text-primary mt-1" />
              <div>
                <p className="font-display font-semibold">Preparar este ecrã para o stand</p>
                <p className="mt-1 text-sm text-muted-foreground">Ativa a demo offline do profissional. Entre visitantes, use « Recomeçar » — a demo também recomeça sozinha após 3 minutos sem utilização.</p>
                <Button className="mt-4 rounded-sm" onClick={start} disabled={busy} data-testid="stand-start-btn">
                  {busy ? "A preparar…" : "Começar a demonstração"} <ArrowRight className="ml-2 h-4 w-4" />
                </Button>
              </div>
            </div>
          </div>
        )}

        {active && (
          <>
            <ol className="mt-8 grid gap-4 sm:grid-cols-2" data-testid="stand-steps">
              {STEPS.map((s) => {
                const Icon = s.icon;
                const body = (
                  <>
                    <div className="flex items-center gap-3">
                      <span className="flex h-9 w-9 items-center justify-center rounded-full bg-primary text-primary-foreground font-bold">{s.n}</span>
                      <Icon className="h-5 w-5 text-primary" />
                      <h2 className="font-display text-lg font-semibold">{s.title}</h2>
                    </div>
                    <p className="mt-3 text-sm text-muted-foreground">{s.say}</p>
                    <div className="mt-4 inline-flex items-center text-sm font-medium text-primary">Abrir <ArrowRight className="ml-2 h-4 w-4" /></div>
                  </>
                );
                const cls = "block rounded-md border border-border bg-card p-6 transition hover:border-primary hover:shadow-md";
                return (
                  <li key={s.n} className="flex flex-col gap-2" data-testid={`stand-step-${s.n}`}>
                    {s.href
                      ? <a href={s.href} target="_blank" rel="noreferrer" className={cls}>{body}</a>
                      : <Link to={s.to} className={cls}>{body}</Link>}
                    {s.extra && (
                      <div className="flex flex-wrap gap-2">
                        {s.extra.map((q) => <Link key={q} to={ask(q)} className="text-xs rounded-full border border-border px-3 py-1 hover:border-primary">{q}</Link>)}
                      </div>
                    )}
                    {s.files && (
                      <div className="flex flex-wrap gap-2">
                        {s.files.map(([label, f]) => (
                          <a key={f} href={`/demo-assets/${f}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-xs rounded-full border border-border px-3 py-1 hover:border-primary">
                            <Download className="h-3 w-3" /> {label}
                          </a>
                        ))}
                      </div>
                    )}
                  </li>
                );
              })}
            </ol>
            <div className="mt-8 flex flex-wrap gap-3">
              <Button variant="outline" className="rounded-sm" onClick={resetStand} data-testid="stand-reset-btn">
                <RotateCcw className="h-4 w-4 mr-2" /> Recomeçar para o próximo visitante
              </Button>
              <Button variant="ghost" className="rounded-sm text-muted-foreground" onClick={leave} data-testid="stand-leave-btn">Sair do modo stand</Button>
            </div>
          </>
        )}
      </main>
    </div>
  );
}
