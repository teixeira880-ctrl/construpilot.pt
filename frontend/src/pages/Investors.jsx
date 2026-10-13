import { Link } from "react-router-dom";
import { useState } from "react";
import {
  ArrowRight, ScanLine, Cuboid, FileText, Bot, Globe2, ShieldCheck,
  TrendingUp, Target, Rocket, PieChart, Mail, CheckCircle2, Building2, Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { DeckDownloadDialog } from "@/components/investors/DeckDownloadDialog";
import { PitchDeckPreview } from "@/components/investors/PitchDeckPreview";

const CONTACT = "info@construpilot.fr";

const Slide = ({ n, kicker, title, children, dark }) => (
  <section data-testid={`deck-slide-${n}`}
           className={`relative border-b border-border ${dark ? "bg-secondary/30" : "bg-background"}`}>
    <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-20 lg:py-28">
      <div className="flex items-center gap-3 mb-5">
        <span className="num text-xs font-bold text-primary/70">{String(n).padStart(2, "0")}</span>
        <span className="overline">{kicker}</span>
      </div>
      <h2 className="font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight max-w-4xl">{title}</h2>
      <div className="mt-8">{children}</div>
    </div>
  </section>
);

const Card = ({ icon: Icon, title, text }) => (
  <div className="rounded-2xl border border-border bg-card p-6">
    <span className="h-11 w-11 rounded-xl bg-primary/10 border border-primary/20 grid place-items-center mb-4">
      <Icon className="h-5 w-5 text-primary" />
    </span>
    <h3 className="font-semibold text-lg">{title}</h3>
    <p className="mt-2 text-sm text-muted-foreground leading-relaxed">{text}</p>
  </div>
);

const Stat = ({ v, l }) => (
  <div className="rounded-2xl border border-border bg-card p-6 text-center">
    <p className="num text-4xl font-extrabold text-primary">{v}</p>
    <p className="mt-2 text-xs text-muted-foreground">{l}</p>
  </div>
);

export default function Investors() {
  const [deckOpen, setDeckOpen] = useState(false);
  const [deckFormat, setDeckFormat] = useState("pdf");
  const openDeck = (format = "pdf") => { setDeckFormat(format); setDeckOpen(true); };
  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="investors-page">
      <DeckDownloadDialog open={deckOpen} onOpenChange={setDeckOpen} format={deckFormat} />
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto max-w-[1200px] px-4 sm:px-6 lg:px-10 min-h-16 py-3 flex flex-wrap gap-3 items-center justify-between">
          <Link to="/" data-testid="deck-home-link" className="font-display font-bold text-lg">Constru<span className="text-primary">Pilot</span></Link>
          <div className="flex flex-wrap items-center gap-2">
            <Button size="sm" variant="outline" className="rounded-full gap-2" data-testid="deck-download-top"
                    onClick={() => openDeck()}>
              <Download className="h-4 w-4" /> Pitch deck PDF
            </Button>
            <Button asChild size="sm" className="rounded-full gap-2" data-testid="deck-contact-top">
              <a href={`mailto:${CONTACT}?subject=Investissement ConstruPilot`}><Mail className="h-4 w-4" /> Contacter</a>
            </Button>
          </div>
        </div>
      </header>

      <PitchDeckPreview onDownload={openDeck} />

      {/* HERO */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 h-72 w-[70%] bg-primary/20 blur-3xl rounded-full pointer-events-none" />
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-24 lg:py-32 text-center relative">
          <span className="overline">Dossier investisseurs · 2026</span>
          <h1 className="mt-5 font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
            A IA que transforma uma planta<br className="hidden sm:block" /> em orçamento, em segundos.
          </h1>
          <p className="mt-6 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto">
            ConstruPilot digitaliza todo o ciclo da construção: análise IA das plantas, medições betão & aço, maqueta 3D e orçamento automático — numa única plataforma.
          </p>
          <div className="mt-9 flex flex-wrap gap-3 justify-center">
            <Button asChild size="lg" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-contact">
              <a href={`mailto:${CONTACT}?subject=Investissement ConstruPilot`}><Mail className="h-5 w-5" /> Falar com a equipa</a>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-demo">
              <Link to="/">Ver a demonstração <ArrowRight className="h-5 w-5" /></Link>
            </Button>
            <Button size="lg" variant="ghost" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-download"
                    onClick={() => openDeck()}>
              <Download className="h-5 w-5" /> Descarregar o pitch deck (PDF)
            </Button>
          </div>
        </div>
      </section>

      {/* 01 PROBLÈME */}
      <Slide n={1} kicker="O problema" dark
             title="Orçamentar uma obra continua lento, manual e fonte de erros.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={FileText} title="Horas perdidas" text="Uma medição manual a partir de uma planta demora horas e atrasa o envio dos orçamentos." />
          <Card icon={Target} title="Margens que escapam" text="Erros de quantidades, artigos esquecidos, preços desatualizados: a rentabilidade desgasta-se." />
          <Card icon={Building2} title="Ferramentas compartimentadas" text="Medição, orçamento, 3D, faturação e obra vivem em softwares separados." />
        </div>
      </Slide>

      {/* 02 SOLUTION */}
      <Slide n={2} kicker="A solução"
             title="Uma plataforma única, da planta ao orçamento assinado — impulsionada por IA.">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <Card icon={ScanLine} title="Análise IA da planta" text="Deteção de paredes, pilares, vigas, sapatas + medição de betão e aços automáticas." />
          <Card icon={FileText} title="Orçamento instantâneo" text="A partir de uma planta, de uma descrição ou de um vídeo. Orçamentação automática através da biblioteca de preços." />
          <Card icon={Cuboid} title="Maquette 3D" text="Visualização dos volumes detetados, exportação PNG anexada ao orçamento do cliente." />
          <Card icon={Bot} title="Assistant IA" text="Correção da planta em linguagem natural, margem e preço de venda estimados." />
        </div>
      </Slide>

      {/* 03 MARCHÉ */}
      <Slide n={3} kicker="O mercado" dark
             title="Um setor enorme, ainda pouco digitalizado.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Stat v="+500 Md€" l="mercado da construção em Portugal (por ano)" />
          <Stat v="~600 000" l="empresas de construção em Portugal" />
          <Stat v="< 30%" l="equipadas com uma verdadeira ferramenta de orçamentação" />
        </div>
        <p className="mt-6 text-sm text-muted-foreground max-w-3xl">
          Tendências promissoras 2026: obrigatoriedade de fatura eletrónica, escassez de mão de obra (necessidade de produtividade) e adoção rápida da IA. Alvo: artesãos, PME da construção e gabinetes de projeto.
        </p>
      </Slide>

      {/* 04 DIFFÉRENCIATION */}
      <Slide n={4} kicker="A nossa vantagem"
             title="A única ferramenta que liga IA de planta, medições de betão, 3D e orçamento.">
        <ul className="grid sm:grid-cols-2 gap-4 max-w-3xl">
          {[
            "IA de planta → medições betão + aços (único ponta a ponta)",
            "Orçamento a partir de vídeo (voz + fotos) — inédito no mercado",
            "Maquete 3D gerada automaticamente a partir das medições",
            "ERP integrado: faturas, autos de medição, RH, acompanhamento de obra",
            "Multilingue (7 langues) + Landing B2C particuliers",
            "Conformidade fatura eletrónica (Factur-X) já implementada",
          ].map((t) => (
            <li key={t} className="flex items-start gap-3 text-sm">
              <CheckCircle2 className="h-5 w-5 text-primary shrink-0 mt-0.5" /><span>{t}</span>
            </li>
          ))}
        </ul>
      </Slide>

      {/* 05 MODÈLE ÉCONOMIQUE */}
      <Slide n={5} kicker="Modelo económico" dark
             title="SaaS por subscrição, receitas recorrentes e escaláveis.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={TrendingUp} title="Abonnement SaaS" text="Planos mensais por utilizador (profissional → PME), subida de gama por módulos." />
          <Card icon={PieChart} title="Opções ao valor" text="Créditos IA, módulo Empresa (RBAC/RH/obra), geração de documentos." />
          <Card icon={Globe2} title="Expansion" text="Mercado lusófono e depois Europa do Sul (já multilingue), e B2C particulares." />
        </div>
      </Slide>

      {/* 06 POURQUOI MAINTENANT */}
      <Slide n={6} kicker="Pourquoi maintenant"
             title="O produto certo, no momento certo.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={Rocket} title="IA mature" text="Os modelos de visão permitem finalmente ler plantas de forma fiável." />
          <Card icon={ShieldCheck} title="Regulamentação" text="A faturação eletrónica leva todo o setor a equipar-se em 2026-2027." />
          <Card icon={TrendingUp} title="Produto já avançado" text="Plataforma completa e funcional, pronta a crescer." />
        </div>
      </Slide>

      {/* 07 L'ASK */}
      <section className="border-b border-border bg-gradient-to-br from-primary/15 via-card to-secondary">
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-24 text-center">
          <span className="overline">A oportunidade</span>
          <h2 className="mt-5 font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
            Estamos a angariar fundos para acelerar.
          </h2>
          <div className="mt-10 grid sm:grid-cols-3 gap-5 max-w-3xl mx-auto text-left">
            <Card icon={Rocket} title="Produit & IA" text="Reforçar a deteção (IFC/BIM), o 3D e a automatização da orçamentação." />
            <Card icon={TrendingUp} title="Go-to-market" text="Aquisição de profissionais/PME, parcerias com fornecedores e associações do setor." />
            <Card icon={Building2} title="Equipa" text="Recrutamentos de produto, IA e comercial para crescer." />
          </div>
          <div className="mt-10 flex flex-wrap gap-3 justify-center">
            <Button asChild size="lg" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-final">
              <a href={`mailto:${CONTACT}?subject=Investissement ConstruPilot&body=Bonjour, je souhaite en savoir plus sur l'opportunité d'investissement dans ConstruPilot.`}>
                <Mail className="h-5 w-5" /> Solicitar o dossiê completo
              </a>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full h-13 px-8 gap-2" data-testid="deck-explore-product">
              <Link to="/">Explorar o produto <ArrowRight className="h-5 w-5" /></Link>
            </Button>
          </div>
          <p className="mt-6 text-xs text-muted-foreground">Contact : {CONTACT}</p>
        </div>
      </section>

      <footer className="mx-auto max-w-[1200px] px-6 lg:px-10 py-10 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} ConstruPilot — Documento confidencial destinado aos investidores.
      </footer>
    </div>
  );
}
