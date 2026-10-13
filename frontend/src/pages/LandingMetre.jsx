import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { motion } from "framer-motion";
import {
  ArrowRight, FileText, Mic, Ruler, Receipt, CheckCircle2, Quote, ShieldCheck, Sparkles,
  Clock, TrendingUp, Upload,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";

const ROOMS = [
  ["Sala", 24], ["Cozinha", 11], ["Ch. 1", 14], ["Ch. 2", 12], ["Ch. 3", 11], ["WC", 5], ["Entrada", 8], ["WC", 2],
];
const LOTS = [
  ["Demolição e remoção", 3640, 34], ["Pladur e isolamento", 9860, 31], ["Eletricidade", 7420, 28],
  ["Canalização", 6980, 27], ["Azulejo e mosaico", 5760, 33], ["Carpintaria interior", 8340, 30],
  ["Pintura", 9120, 36], ["Pavimentos", 7480, 29], ["Acabamentos e limpeza", 3880, 22],
];
const TOTAL = LOTS.reduce((a, l) => a + l[1], 0);
const MARGE = Math.round(LOTS.reduce((a, l) => a + l[1] * l[2] / 100, 0));
const eur = (n) => n.toLocaleString("pt-PT") + " €";

const FAQ = [
  ["ConstruPilot está adaptado às empresas gerais de renovação?",
    "Sim. Uma obra completa é estruturada por capítulos (demolição, estuques, eletricidade, canalização, revestimentos cerâmicos, carpintarias, pintura, pavimentos, acabamentos…) com os seus artigos, quantidades e subtotais. Um orçamento de 70 linhas em 9 capítulos é um caso normal."],
  ["Posso utilizar os meus próprios trabalhos e os meus próprios preços?",
    "Sim. Começa com o nosso catálogo (artigos com preços ajustados por nível) e depois o ConstruPilot orçamenta com os seus: cada linha validada é guardada na sua biblioteca privada e é esse preço que é retomado no orçamento seguinte."],
  ["ConstruPilot pode recuperar os meus antigos orçamentos?",
    "Sim. Carregue os seus antigos orçamentos em PDF (Tolteck, Obat, Batappli, Excel, Word…): a IA extrai os trabalhos, unidades e preços para reconstruir a sua biblioteca. Não começa do zero."],
  ["Lê as minhas plantas, as minhas fotos e o processo do arquiteto?",
    "Sim. Uma planta PDF, digitalizada ou fotografada, fotografias da visita, uma nota de voz e o mapa de quantidades: o ConstruPilot extrai as divisões, as áreas (paredes desenvolvidas, vãos deduzidos, rodapés) e os artigos. Verifica cada quantidade antes de entrar no orçamento."],
  ["Calcula a minha margem?",
    "Sim, antes da assinatura. Cada linha tem o seu custo de produção (mão de obra + materiais). O ConstruPilot apresenta a margem previsional capítulo a capítulo enquanto orçamenta e assinala os artigos orçamentados com prejuízo."],
  ["Substitui o meu software de faturação?",
    "Sim. O orçamento assinado passa a fatura de adiantamento, autos de medição e fatura final sem reintrodução, com nota de crédito se necessário. Faturação eletrónica conforme, exportação PDF/CSV para o seu contabilista certificado."],
  ["Decide o preço no meu lugar?",
    "Não. Mantém o controlo das quantidades, dos trabalhos, dos preços e do orçamento final. Nada é enviado ao cliente sem a sua validação."],
];

const fade = (d = 0) => ({ initial: { opacity: 0, y: 18 }, whileInView: { opacity: 1, y: 0 }, viewport: { once: true, margin: "-60px" }, transition: { duration: 0.55, delay: d } });

function Step({ n, icon: Icon, title, text, children, delay }) {
  return (
    <motion.div {...fade(delay)} className="grid lg:grid-cols-[1fr_1.15fr] gap-8 items-center" data-testid={`metre-step-${n}`}>
      <div>
        <span className="num text-primary text-sm font-bold">0{n}</span>
        <h3 className="font-display text-2xl md:text-3xl font-bold mt-1 flex items-center gap-3"><Icon className="h-6 w-6 text-primary" /> {title}</h3>
        <p className="text-muted-foreground mt-3 text-base leading-relaxed">{text}</p>
      </div>
      <div className="surface rounded-xl p-5 shadow-2xl border border-border/60">{children}</div>
    </motion.div>
  );
}

function Counter({ to, suffix = "" }) {
  const [v, setV] = useState(0);
  useEffect(() => {
    let raf; const t0 = performance.now();
    const tick = (t) => { const p = Math.min(1, (t - t0) / 1100); setV(Math.round(to * (1 - Math.pow(1 - p, 3)))); if (p < 1) raf = requestAnimationFrame(tick); };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [to]);
  return <span className="num">{v.toLocaleString("pt-PT")}{suffix}</span>;
}

export default function LandingMetre() {
  return (
    <div className="min-h-screen bg-background text-foreground" data-testid="landing-metre">
      <SEO title="Medições IA — da planta ao orçamento com os seus preços | ConstruPilot"
           description="Deposite planta, fotos, nota de voz ou mapa de quantidades: ConstruPilot mede cada divisão, orçamenta por especialidades aos seus preços e mostra a sua margem antes da assinatura. Teste gratuito, sem compromisso."
           canonical="/metre" />
      <Nav />

      {/* HERO */}
      <section className="relative overflow-hidden">
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(ellipse_at_top_left,hsl(var(--primary)/0.18),transparent_55%)]" />
        <div className="mx-auto max-w-6xl px-5 lg:px-8 pt-16 pb-14 grid lg:grid-cols-[1.1fr_1fr] gap-10 items-center">
          <motion.div initial={{ opacity: 0, x: -20 }} animate={{ opacity: 1, x: 0 }} transition={{ duration: 0.6 }}>
            <p className="overline text-primary">Medições IA · Empresas de renovação</p>
            <h1 className="font-display text-4xl sm:text-5xl lg:text-6xl font-extrabold leading-[1.05] mt-3">
              Deixe a IA gerir o seu <span className="text-primary">medições</span>, mantenha os seus preços.
            </h1>
            <p className="text-base md:text-lg text-muted-foreground mt-5 max-w-xl">
              Uma planta, algumas fotos, uma nota de voz ou o mapa de quantidades do arquiteto: ConstruPilot levanta cada divisão, orçamenta por especialidades aos seus preços e mostra-lhe a margem <b>avant</b> de enviar o orçamento.
            </p>
            <div className="flex flex-wrap gap-3 mt-7">
              <Button asChild size="lg" className="rounded-full gap-2 h-12 px-6" data-testid="metre-cta-start">
                <Link to="/inscription?signup=1&plan=pro">Iniciar o teste gratuito <ArrowRight className="h-4 w-4" /></Link>
              </Button>
              <Button asChild size="lg" variant="outline" className="rounded-full h-12 px-6" data-testid="metre-cta-demo">
                <Link to="/plan">Ver em ação</Link>
              </Button>
            </div>
            <p className="text-xs text-muted-foreground mt-3 flex items-center gap-2"><ShieldCheck className="h-3.5 w-3.5" /> Teste gratuito · Sem compromisso · Alojado em França</p>
          </motion.div>

          <motion.figure initial={{ opacity: 0, scale: 0.96 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6, delay: 0.15 }}
                         className="relative" data-testid="metre-hero-video">
            <div className="absolute -inset-4 bg-primary/15 blur-3xl rounded-[2.5rem]" aria-hidden="true" />
            <div className="relative rounded-2xl border border-border bg-black shadow-2xl overflow-hidden aspect-video">
              <video className="h-full w-full object-cover" src="/docs/ConstruPilot_Demo_Courte_16x9.mp4"
                     autoPlay muted loop controls playsInline preload="metadata" data-testid="metre-video-player" />
            </div>
            <figcaption className="mt-3 text-xs text-muted-foreground text-center">Demonstração em 2 min: estimativa, planta → medições, orçamento, assinatura, aprovisionamento, Radar, rentabilidade.</figcaption>
          </motion.figure>
        </div>
      </section>

      <section className="bg-secondary/30 border-y border-border/60">
        <div className="mx-auto max-w-6xl px-5 lg:px-8 py-12">
          <figure className="surface rounded-2xl p-6 border border-border/60 shadow-2xl relative max-w-2xl mx-auto" data-testid="metre-testimonial">
            <Quote className="h-8 w-8 text-primary/40 absolute -top-3 -left-3 rotate-180" />
            <h2 className="font-display text-base md:text-lg font-bold">Como o Fabrice recuperou <span className="text-primary">até 5 horas por semana</span>.</h2>
            <p className="text-sm text-muted-foreground mt-3 leading-relaxed">
              « Um processo de consulta, as medições levavam-nos dois dias. Hoje depositamos o processo, as quantidades saem sozinhas, os nossos preços aplicam-se em cima, e resta-me a verificação. Respondemos a tudo. »
            </p>
            <div className="flex items-center gap-3 mt-5">
              <span className="h-10 w-10 rounded-full bg-primary/15 grid place-items-center font-display font-bold text-primary">FB</span>
              <div><p className="text-sm font-bold">Fabrice B.</p><p className="text-xs text-muted-foreground">Empresa geral · Renovação interior · 11 funcionários</p></div>
            </div>
            <p className="text-[10px] text-muted-foreground mt-3">Testemunho ilustrativo</p>
          </figure>
        </div>
      </section>

      {/* 3 ÉTAPES */}
      <section className="mx-auto max-w-6xl px-5 lg:px-8 py-16 space-y-20" data-testid="metre-steps">
        <motion.div {...fade()} className="max-w-2xl">
          <p className="overline text-primary">Como funciona</p>
          <h2 className="font-display text-3xl md:text-4xl font-bold mt-2">Automatizar o orçamento de toda uma obra com IA</h2>
        </motion.div>

        <Step n={1} icon={Upload} title="Deposita a obra" delay={0}
              text="A planta, as fotografias da visita, a descrição, uma nota de voz ditada na obra, o mapa de quantidades. Nenhum formulário para preencher.">
          <div className="text-xs space-y-2">
            <div className="flex items-center justify-between"><span className="font-bold">Obra · Apartamento T4 · Lyon 6ᵉ</span><span className="text-primary flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5" /> Recebido</span></div>
            {[["Plan-T4-architecte.pdf · 1/50", FileText], ["Nota de voz · 1:12 · «T4 para refazer completamente…»", Mic], ["DPGF arquiteto · 9 lotes · 61 artigos", Receipt]].map(([l, I], i) => (
              <motion.div key={l} initial={{ opacity: 0, x: -10 }} whileInView={{ opacity: 1, x: 0 }} viewport={{ once: true }} transition={{ delay: 0.2 + i * 0.15 }}
                          className="flex items-center gap-2 rounded-md bg-secondary/40 px-3 py-2"><I className="h-4 w-4 text-primary" /> {l}</motion.div>
            ))}
            <div className="flex gap-1.5 pt-1">{["Sala", "Cozinha", "WC"].map((p) => <span key={p} className="h-12 flex-1 rounded-md bg-primary/10 grid place-items-center text-[10px] text-muted-foreground">{p}</span>)}</div>
          </div>
        </Step>

        <Step n={2} icon={Ruler} title="ConstruPilot mede a obra" delay={0.05}
              text="Cada divisão identificada na planta, paredes desenvolvidas, vãos deduzidos, rodapés contados. Resultado: 8 divisões, 87 m² de pavimento.">
          <div className="text-xs">
            <div className="flex items-center justify-between mb-2"><span className="font-bold">Medições · 8 divisões levantadas</span><span className="text-primary">Calculado</span></div>
            <div className="grid grid-cols-4 gap-1.5">
              {ROOMS.map(([n, s], i) => (
                <motion.div key={n} initial={{ opacity: 0, scale: 0.9 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true }} transition={{ delay: 0.1 + i * 0.06 }}
                            className="rounded-md border border-primary/30 bg-primary/5 p-2 text-center"><p className="text-[10px] uppercase text-muted-foreground">{n}</p><p className="num font-bold">{s} m²</p></motion.div>
              ))}
            </div>
            <div className="grid grid-cols-4 gap-2 mt-3">
              {[["Pavimento", 87, " m²"], ["Paredes desenvolvidas", 237, " m²"], ["Tetos", 87, " m²"], ["Rodapés", 63, " ml"]].map(([l, v, u]) => (
                <div key={l} className="rounded-md bg-secondary/40 p-2"><p className="text-[10px] text-muted-foreground">{l}</p><p className="font-bold text-sm"><Counter to={v} suffix={u} /></p></div>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground mt-2">Pé-direito 2,50 m · vãos deduzidos · reportado em cada trabalho</p>
          </div>
        </Step>

        <Step n={3} icon={Receipt} title="Relê, envia" delay={0.05}
              text="O orçamento espera por si em rascunho, orçamentado aos seus preços, com a margem capítulo a capítulo e os artigos com prejuízo assinalados. O cliente assina online.">
          <div className="text-xs">
            <div className="flex items-center justify-between mb-2"><span className="font-bold">Orçamento D-2026-0112 · rascunho</span><span className="text-primary">Os seus preços</span></div>
            <ul className="divide-y divide-border/50">
              {LOTS.map(([l, v, m], i) => (
                <motion.li key={l} initial={{ opacity: 0 }} whileInView={{ opacity: 1 }} viewport={{ once: true }} transition={{ delay: 0.1 + i * 0.05 }} className="flex items-center justify-between py-1.5">
                  <span><span className="num text-muted-foreground mr-2">{i + 1}</span>{l}</span>
                  <span className="flex items-center gap-2"><span className={`num text-[10px] px-1.5 rounded-sm ${m < 25 ? "bg-amber-500/10 text-amber-600" : "bg-emerald-500/10 text-emerald-600"}`}>{m} %</span><b className="num">{eur(v)}</b></span>
                </motion.li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-border mt-2 pt-2"><span className="text-muted-foreground">Total s/ IVA · 9 lotes · 74 linhas</span><b className="num text-base text-primary">{eur(TOTAL)}</b></div>
            <div className="flex items-center justify-between text-emerald-600"><span className="flex items-center gap-1"><TrendingUp className="h-3.5 w-3.5" /> Margem previsional</span><b className="num">{Math.round(MARGE / TOTAL * 100)} % · {eur(MARGE)}</b></div>
          </div>
        </Step>

        <motion.div {...fade()} className="text-center">
          <p className="font-display text-2xl md:text-3xl font-bold">Deixe <span className="text-primary">a IA gerir as suas medições</span>, e concentre-se nos seus clientes.</p>
          <Button asChild size="lg" className="rounded-full gap-2 h-12 px-7 mt-5" data-testid="metre-cta-mid"><Link to="/inscription?signup=1&plan=pro">Ver em ação <ArrowRight className="h-4 w-4" /></Link></Button>
          <p className="text-xs text-muted-foreground mt-2">Teste gratuito · Sem compromisso</p>
        </motion.div>
      </section>

      {/* PREUVE + PRICING */}
      <section className="bg-secondary/30 border-y border-border/60">
        <div className="mx-auto max-w-6xl px-5 lg:px-8 py-16 grid lg:grid-cols-2 gap-10 items-start">
          <motion.div {...fade()}>
            <p className="overline text-primary">O que dizem as empresas</p>
            <blockquote className="font-display text-xl md:text-2xl font-bold mt-3 leading-snug" data-testid="metre-quote">
              « As medições levavam-nos dois dias. Então escolhíamos os processos. Hoje respondemos a tudo, e isso faz <span className="text-primary">cinco horas de escritório a menos por semana</span>. »
            </blockquote>
            <p className="text-sm text-muted-foreground mt-3">Pascal M. · Empresa geral de construção · Villeurbanne · testemunho ilustrativo</p>
            <div className="grid grid-cols-3 gap-3 mt-8">
              {[[Clock, "5 h", "ganhas / semana"], [Sparkles, "30 s", "para um orçamento rascunho"], [TrendingUp, "especialidade por especialidade", "margem visível antes da assinatura"]].map(([I, b, s]) => (
                <div key={s} className="surface rounded-xl p-4"><I className="h-4 w-4 text-primary" /><p className="font-display font-bold text-lg mt-2">{b}</p><p className="text-[11px] text-muted-foreground">{s}</p></div>
              ))}
            </div>
          </motion.div>

          <motion.div {...fade(0.1)} className="surface rounded-2xl p-7 border border-primary/30 shadow-2xl relative overflow-hidden" data-testid="metre-pricing">
            <div className="absolute -top-16 -right-16 h-40 w-40 rounded-full bg-primary/15 blur-2xl" />
            <p className="overline text-primary">As medições IA, com Pro</p>
            <h3 className="font-display text-2xl font-bold mt-1">Para orçamentar também o que lhe enviam: uma planta, um mapa de trabalhos, uma nota de voz.</h3>
            <p className="mt-4"><span className="num text-4xl font-extrabold">149 €</span> <span className="text-sm text-muted-foreground">s/ IVA / mês · sem compromisso · 7 dias de teste</span></p>
            <p className="text-xs text-muted-foreground">Pro Business (equipas, multi-utilizadores): 249 € s/ IVA / mês</p>
            <ul className="text-sm space-y-2 mt-5">
              {["Orçamentos e faturas ilimitados (sinal, autos de medição, saldo, Factur-X)", "Medições IA: o plano torna-se superfícies e trabalhos", "Fotos, vídeos, notas de voz e cotas dos seus planos lidos pela IA", "DPGF recebida lida e orçamentada aos seus preços", "Margem previsional por especialidade + alerta «a perder»", "Recuperação da sua biblioteca a partir dos seus antigos orçamentos PDF", "Obras, clientes, reforços, assinatura online"].map((f) => (
                <li key={f} className="flex items-start gap-2"><CheckCircle2 className="h-4 w-4 text-primary mt-0.5 shrink-0" /> {f}</li>
              ))}
            </ul>
            <Button asChild size="lg" className="rounded-full w-full mt-6 h-12" data-testid="metre-cta-pricing"><Link to="/inscription?signup=1&plan=pro">Iniciar o teste gratuito</Link></Button>
            <p className="text-center text-xs text-muted-foreground mt-2"><Link to="/tarifs" className="underline underline-offset-2">Ver todas as tarifas</Link></p>
          </motion.div>
        </div>
      </section>

      {/* FAQ */}
      <section className="mx-auto max-w-3xl px-5 lg:px-8 py-16" data-testid="metre-faq">
        <motion.div {...fade()}>
          <p className="overline text-primary">Perguntas frequentes</p>
          <h2 className="font-display text-3xl md:text-4xl font-bold mt-2 mb-6">Tudo o que quer saber antes de testar.</h2>
        </motion.div>
        <Accordion type="single" collapsible className="w-full">
          {FAQ.map(([q, a], i) => (
            <AccordionItem key={q} value={`q${i}`} data-testid={`metre-faq-${i}`}>
              <AccordionTrigger className="text-left font-display font-bold">{q}</AccordionTrigger>
              <AccordionContent className="text-muted-foreground leading-relaxed">{a}</AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </section>

      <Footer />
    </div>
  );
}
