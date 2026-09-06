import { Link } from "react-router-dom";
import { useState } from "react";
import {
  ArrowRight, ScanLine, Cuboid, FileText, Bot, Globe2, ShieldCheck,
  TrendingUp, Target, Rocket, PieChart, Mail, CheckCircle2, Building2, Download,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { toast } from "sonner";

const CONTACT = "info@construpilot.pt";
const DECK_PDF = `${process.env.REACT_APP_BACKEND_URL}/api/investors/pitch-deck.pdf`;

const DeckDownloadDialog = ({ open, onOpenChange }) => {
  const [form, setForm] = useState({ name: "", email: "", fund: "", note: "" });
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  const submit = async (e) => {
    e.preventDefault();
    if (!form.email) return;
    setBusy(true);
    try {
      await api.post("/investors/deck-request", form);
      window.open(DECK_PDF, "_blank", "noopener,noreferrer");
      toast.success("Obrigado! O pitch deck abre num novo separador.");
      onOpenChange(false);
      setForm({ name: "", email: "", fund: "", note: "" });
    } catch {
      // Não bloqueia o acesso ao deck se o registo falhar
      window.open(DECK_PDF, "_blank", "noopener,noreferrer");
      onOpenChange(false);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="deck-download-dialog">
        <DialogHeader>
          <DialogTitle>Receber o pitch deck</DialogTitle>
          <DialogDescription>
            Deixe-nos os seus contactos — o PDF abre logo de seguida.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="deck-name">Nome</Label>
            <Input id="deck-name" value={form.name} onChange={set("name")}
                   placeholder="O seu nome" data-testid="deck-form-name" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="deck-email">E-mail *</Label>
            <Input id="deck-email" type="email" required value={form.email} onChange={set("email")}
                   placeholder="voce@fundo.com" data-testid="deck-form-email" />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="deck-fund">Fundo / empresa</Label>
            <Input id="deck-fund" value={form.fund} onChange={set("fund")}
                   placeholder="Ex.: Urban Ventures" data-testid="deck-form-fund" />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={busy} className="rounded-full gap-2" data-testid="deck-form-submit">
              <Download className="h-4 w-4" /> {busy ? "…" : "Descarregar o PDF"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

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
  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="investors-page">
      <DeckDownloadDialog open={deckOpen} onOpenChange={setDeckOpen} />
      {/* Header */}
      <header className="sticky top-0 z-40 border-b border-border bg-background/85 backdrop-blur">
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 h-16 flex items-center justify-between">
          <Link to="/" className="font-display font-bold text-lg">Constru<span className="text-primary">Pilot</span></Link>
          <div className="flex items-center gap-2">
            <Button size="sm" variant="outline" className="rounded-full gap-2" data-testid="deck-download-top"
                    onClick={() => setDeckOpen(true)}>
              <Download className="h-4 w-4" /> Pitch deck PDF
            </Button>
            <Button asChild size="sm" className="rounded-full gap-2" data-testid="deck-contact-top">
              <a href={`mailto:${CONTACT}?subject=Investimento ConstruPilot`}><Mail className="h-4 w-4" /> Contactar</a>
            </Button>
          </div>
        </div>
      </header>

      {/* HERO */}
      <section className="relative overflow-hidden border-b border-border">
        <div className="absolute -top-24 left-1/2 -translate-x-1/2 h-72 w-[70%] bg-primary/20 blur-3xl rounded-full pointer-events-none" />
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-24 lg:py-32 text-center relative">
          <span className="overline">Dossiê investidores · 2026</span>
          <h1 className="mt-5 font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
            A IA que transforma uma planta<br className="hidden sm:block" /> em orçamento detalhado, em segundos.
          </h1>
          <p className="mt-6 text-base sm:text-lg text-muted-foreground max-w-2xl mx-auto">
            O ConstruPilot digitaliza todo o ciclo da construção: análise IA das plantas, medições de betão e aço,
            maquete 3D e orçamento automático — numa só plataforma.
          </p>
          <div className="mt-9 flex flex-wrap gap-3 justify-center">
            <Button asChild size="lg" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-contact">
              <a href={`mailto:${CONTACT}?subject=Investimento ConstruPilot`}><Mail className="h-5 w-5" /> Falar com a equipa</a>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-demo">
              <Link to="/">Ver demo <ArrowRight className="h-5 w-5" /></Link>
            </Button>
            <Button size="lg" variant="ghost" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-download"
                    onClick={() => setDeckOpen(true)}>
              <Download className="h-5 w-5" /> Descarregar pitch deck (PDF)
            </Button>
          </div>
        </div>
      </section>

      {/* 01 PROBLEMA */}
      <Slide n={1} kicker="O problema" dark
             title="Orçamentar uma obra continua lento, manual e propenso a erros.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={FileText} title="Horas perdidas" text="Uma medição manual a partir de um plano leva horas e atrasa o envio dos orçamentos." />
          <Card icon={Target} title="Margens que fogem" text="Erros de quantidades, esquecimento de rubricas, preços desactualizados: a rentabilidade cai." />
          <Card icon={Building2} title="Ferramentas fragmentadas" text="Medições, orçamentos, 3D, facturação e obra vivem em softwares separados." />
        </div>
      </Slide>

      {/* 02 SOLUÇÃO */}
      <Slide n={2} kicker="A solução"
             title="Uma plataforma única, da planta ao orçamento assinado — impulsionada por IA.">
        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
          <Card icon={ScanLine} title="Análise IA da planta" text="Detecção de paredes, pilares, vigas e sapatas + medições de betão e aço automáticas." />
          <Card icon={FileText} title="Orçamento instantâneo" text="A partir de um plano, descrição ou vídeo. Orçamentação automática via biblioteca de preços." />
          <Card icon={Cuboid} title="Maquete 3D" text="Visualização dos volumes detectados, exportação PNG anexada ao orçamento do cliente." />
          <Card icon={Bot} title="Assistente IA" text="Correcção do plano em linguagem natural, margem e preço de venda estimados." />
        </div>
      </Slide>

      {/* 03 MERCADO */}
      <Slide n={3} kicker="O mercado" dark
             title="Um sector imenso, ainda pouco digitalizado.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Stat v="+30 Md€" l="mercado da construção em Portugal (por ano)" />
          <Stat v="~120 000" l="empresas de construção em Portugal" />
          <Stat v="< 30%" l="equipadas com uma verdadeira ferramenta de orçamentação" />
        </div>
        <p className="mt-6 text-sm text-muted-foreground max-w-3xl">
          Tendências fortes em 2026: obrigatoriedade da e-fatura AT, escassez de mão de obra
          (necessidade de produtividade) e adopção rápida da IA. Alvo: profissionais, PMEs de construção
          e gabinetes de projecto.
        </p>
      </Slide>

      {/* 04 DIFERENCIAÇÃO */}
      <Slide n={4} kicker="A nossa vantagem"
             title="A única ferramenta que liga IA da planta, medições de betão, 3D e orçamento.">
        <ul className="grid sm:grid-cols-2 gap-4 max-w-3xl">
          {[
            "IA da planta → medição de betão + aço (única de ponta a ponta)",
            "Orçamento a partir de um vídeo (voz + fotos) — inédito no mercado",
            "Maquete 3D gerada automaticamente a partir das medições",
            "ERP integrado: facturas, autos de medição, RH, acompanhamento de obra",
            "Multi-idioma (7 línguas) + Landing B2C particulares",
            "Conformidade SAF-T / e-fatura AT já implementada",
          ].map((t) => (
            <li key={t} className="flex items-start gap-3 text-sm">
              <CheckCircle2 className="h-5 w-5 text-primary shrink-0 mt-0.5" /><span>{t}</span>
            </li>
          ))}
        </ul>
      </Slide>

      {/* 05 MODELO DE NEGÓCIO */}
      <Slide n={5} kicker="Modelo de negócio" dark
             title="SaaS por subscrição, receitas recorrentes e escaláveis.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={TrendingUp} title="Subscrição SaaS" text="Planos mensais por utilizador (profissional → PME), upgrades por módulos." />
          <Card icon={PieChart} title="Opções à la carte" text="Créditos de IA, módulo Empresa (RBAC/RH/obra), geração de documentos." />
          <Card icon={Globe2} title="Expansão" text="Mercado ibérico depois Europa do Sul (já multilíngue) e B2C particulares." />
        </div>
      </Slide>

      {/* 06 PORQUÊ AGORA */}
      <Slide n={6} kicker="Porquê agora"
             title="O produto certo, no momento certo.">
        <div className="grid sm:grid-cols-3 gap-5">
          <Card icon={Rocket} title="IA madura" text="Os modelos de visão permitem finalmente ler plantas de forma fiável." />
          <Card icon={ShieldCheck} title="Regulamentação" text="O SAF-T e a e-fatura AT obrigam o sector à digitalização integral." />
          <Card icon={TrendingUp} title="Produto já avançado" text="Plataforma completa e funcional, pronta a escalar." />
        </div>
      </Slide>

      {/* 07 A OPORTUNIDADE */}
      <section className="border-b border-border bg-gradient-to-br from-primary/15 via-card to-secondary">
        <div className="mx-auto max-w-[1200px] px-6 lg:px-10 py-24 text-center">
          <span className="overline">A oportunidade</span>
          <h2 className="mt-5 font-display text-3xl sm:text-4xl lg:text-5xl font-bold tracking-tight">
            Estamos a levantar capital para acelerar.
          </h2>
          <div className="mt-10 grid sm:grid-cols-3 gap-5 max-w-3xl mx-auto text-left">
            <Card icon={Rocket} title="Produto & IA" text="Reforçar a detecção (IFC/BIM), a 3D e a automatização da orçamentação." />
            <Card icon={TrendingUp} title="Go-to-market" text="Aquisição de profissionais/PMEs, parcerias com fornecedores e federações do sector." />
            <Card icon={Building2} title="Equipa" text="Recrutamentos em produto, IA e comercial para escalar." />
          </div>
          <div className="mt-10 flex flex-wrap gap-3 justify-center">
            <Button asChild size="lg" className="rounded-full h-13 px-8 gap-2" data-testid="deck-cta-final">
              <a href={`mailto:${CONTACT}?subject=Investimento ConstruPilot&body=Olá, gostaria de saber mais sobre a oportunidade de investimento na ConstruPilot.`}>
                <Mail className="h-5 w-5" /> Pedir o dossiê completo
              </a>
            </Button>
            <Button asChild size="lg" variant="outline" className="rounded-full h-13 px-8 gap-2">
              <Link to="/">Explorar o produto <ArrowRight className="h-5 w-5" /></Link>
            </Button>
          </div>
          <p className="mt-6 text-xs text-muted-foreground">Contacto: {CONTACT}</p>
        </div>
      </section>

      <footer className="mx-auto max-w-[1200px] px-6 lg:px-10 py-10 text-center text-xs text-muted-foreground">
        © {new Date().getFullYear()} ConstruPilot — Documento confidencial destinado a investidores.
      </footer>
    </div>
  );
}
