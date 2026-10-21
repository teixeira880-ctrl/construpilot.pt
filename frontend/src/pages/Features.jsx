import { Link } from "react-router-dom";
import {
  Calculator, Sparkles, Camera, FileText, Search, MessageSquare, ShieldCheck,
  Ruler, Home as HomeIcon, HardHat, Layers, Building2, Droplets, Waves,
  Truck, PenTool, FileSignature, CreditCard, CalendarRange, Users, Boxes,
  Cuboid, ArrowRight, CheckCircle2, Smartphone, Download, PlayCircle,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Nav, Footer } from "@/components/Nav";
import { SEO } from "@/components/SEO";
import { FeatureClips } from "@/components/FeatureClips";
import HelpChatbot from "@/components/HelpChatbot";

const PARTICULIER = [
  { icon: Calculator, title: "Estimador de obras", desc: "Orçamentação instantânea materiais + mão de obra, por tipo de projeto." },
  { icon: Sparkles, title: "Smart Project", desc: "Descreva «renovar casa de banho 8 m²» → especialidades, materiais e orçamento gerados pela IA." },
  { icon: Camera, title: "Análise de fotografia", desc: "Envie uma foto de uma divisão ou de um defeito, a IA propõe pistas." },
  { icon: FileText, title: "Scanner de orçamentos", desc: "Importe um orçamento PDF: a IA explica-o e verifica os montantes." },
  { icon: Ruler, title: "Calculadoras", desc: "Superfícies, volumes, quantidades (pintura, azulejo, betão…)." },
  { icon: Search, title: "Pesquisa de preços", desc: "Ordens de grandeza de preços de materiais e prestações." },
  { icon: MessageSquare, title: "Coach IA obras", desc: "Um assistente que responde às suas questões de obra, em português." },
  { icon: CalendarRange, title: "Planeamento das fases", desc: "Visualize a ordem das etapas da sua obra." },
  { icon: ShieldCheck, title: "Segurança em primeiro lugar", desc: "Gás, eletricidade, paredes estruturais: a app orienta sempre para um profissional." },
];

const PRO = [
  { icon: Cuboid, title: "Análise de plantas DWG/DXF/PDF", desc: "Renderização fiel (cotas, textos) e medições exatas: paredes, pavimentos, escadas, vigas, pilares." },
  { icon: Building2, title: "Medições betão & estrutura", desc: "Quantidades betão e orçamento detalhado por especialidade, margens e sinal." },
  { icon: HardHat, title: "Ferragem / Aço", desc: "Extração das varões HA e malha → relação e quantidades encomendáveis." },
  { icon: Droplets, title: "Impermeabilização", desc: "Cobertura plana: mapa por camada → rolos, bidões, painéis." },
  { icon: Layers, title: "Cobertura", desc: "Telhas/ardósias/chapa, tela, ripas, cumeeira, rincões, caleiras." },
  { icon: Waves, title: "VRD / Redes", desc: "EP, EU, AEP, telecom, gás + medições das valas (escavação, areia, aterro, reposição)." },
  { icon: Boxes, title: "Biblioteca de preços DPGF", desc: "Importe o seu Excel/BPU para sobrepor os preços da IA." },
  { icon: Truck, title: "Aprovisionamento & fornecedores", desc: "Orçamentação, marcação na planta, exportação CSV e nota de encomenda por e-mail." },
  { icon: FileSignature, title: "Orçamentos assináveis online", desc: "Os seus clientes aceitam e assinam o orçamento à distância." },
  { icon: CreditCard, title: "Sinal Stripe", desc: "Cobre 30 % de sinal à assinatura do orçamento." },
  { icon: Users, title: "Equipa & portal Pro", desc: "Colaboradores, funções, portal dedicado e gestão de projetos." },
  { icon: Smartphone, title: "Aplicação móvel (PWA)", desc: "Instale ConstruPilot no telemóvel para a obra." },
];

const Card = ({ icon: Icon, title, desc, tid }) => (
  <div className="surface p-5 rounded-lg hover:border-primary/50 transition-colors" data-testid={tid}>
    <div className="h-10 w-10 rounded-md bg-primary/10 flex items-center justify-center mb-3">
      <Icon className="h-5 w-5 text-primary" />
    </div>
    <h3 className="font-bold text-base mb-1">{title}</h3>
    <p className="text-sm text-muted-foreground">{desc}</p>
  </div>
);

export default function Features() {
  return (
    <div className="min-h-screen bg-background">
      <SEO title="Funcionalidades" description="Todas as funcionalidades ConstruPilot para particulares e profissionais da construção: estimativa IA, análise de plantas DWG, medições, orçamento, aprovisionamento." canonical="/fonctionnalites" />
      <Nav />

      <section className="max-w-6xl mx-auto px-4 pt-16 pb-10 text-center">
        <span className="overline text-primary">Funcionalidades</span>
        <h1 className="mt-3 font-display text-4xl sm:text-5xl lg:text-6xl font-bold tracking-tight">
          Todo o ConstruPilot, <span className="text-primary">num relance</span>
        </h1>
        <p className="mt-5 text-base text-muted-foreground max-w-2xl mx-auto">
          Ferramentas simples para particulares, uma suite técnica poderosa para profissionais da construção. Estimativa, plantas, medições, orçamentos e aprovisionamento — impulsionados por IA.
        </p>
        <div className="mt-8 flex flex-wrap gap-3 justify-center">
          <Link to="/login"><Button className="rounded-sm gap-2 h-11" data-testid="features-cta-start">Começar gratuitamente <ArrowRight className="h-4 w-4" /></Button></Link>
          <Link to="/tarifs"><Button variant="outline" className="rounded-sm h-11" data-testid="features-cta-pricing">Ver as tarifas</Button></Link>
        </div>
      </section>

      <FeatureClips />

      <section className="max-w-6xl mx-auto px-4 py-10">
        <div className="flex items-center gap-3 mb-6">
          <HomeIcon className="h-6 w-6 text-primary" />
          <h2 className="font-display text-2xl font-bold">Para particulares</h2>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="features-particulier">
          {PARTICULIER.map((f, i) => <Card key={i} {...f} tid={`feature-part-${i}`} />)}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 py-10">
        <div className="flex items-center gap-3 mb-2">
          <HardHat className="h-6 w-6 text-primary" />
          <h2 className="font-display text-2xl font-bold">Para profissionais</h2>
          <span className="text-[10px] font-bold uppercase bg-primary/10 text-primary px-2 py-0.5 rounded-full">Oferta Pro</span>
        </div>
        <p className="text-sm text-muted-foreground mb-6">Medições exatas a partir das suas plantas, abastecimento da obra e orçamentos profissionais.</p>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4" data-testid="features-pro">
          {PRO.map((f, i) => <Card key={i} {...f} tid={`feature-pro-${i}`} />)}
        </div>
      </section>

      <section className="max-w-6xl mx-auto px-4 py-10" data-testid="features-downloads">
        <div className="surface p-6 rounded-xl">
          <h2 className="font-display text-xl font-bold flex items-center gap-2"><Download className="h-5 w-5 text-primary" /> Todas as funcionalidades em PDF e PowerPoint</h2>
          <p className="mt-2 text-sm text-muted-foreground">Brochura comercial (1 oferta por página) e catálogo exaustivo — Particulares, Premium, Pro, Pro Business, Blog & SEO, Radar Chantiers, API. Em francês.</p>
          <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {[
              ["Brochura (PDF)", "/docs/ConstruPilot_Brochure_Fonctionnalites.pdf", "features-dl-brochure-pdf"],
              ["Brochura (PowerPoint)", "/docs/ConstruPilot_Brochure_Fonctionnalites.pptx", "features-dl-brochure-pptx"],
              ["Catálogo completo (PDF)", "/docs/ConstruPilot_Catalogue_Complet.pdf", "features-dl-catalogue-pdf"],
              ["Catálogo completo (PowerPoint)", "/docs/ConstruPilot_Catalogue_Complet.pptx", "features-dl-catalogue-pptx"],
            ].map(([label, href, tid]) => (
              <a key={tid} href={href} download data-testid={tid}
                 className="flex items-center gap-2 rounded-sm border border-border px-3 py-2.5 text-sm hover:bg-primary/5 transition-colors">
                <FileText className="h-4 w-4 text-primary shrink-0" />{label}
              </a>
            ))}
          </div>
          <div className="mt-4 grid sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="features-videos">
            {[
              ["Vídeo demonstração curto 16:9 (2 min)", "/docs/ConstruPilot_Demo_Courte_16x9.mp4", "features-video-short-169"],
              ["Vídeo demonstração curto 9:16 (reels)", "/docs/ConstruPilot_Demo_Courte_9x16.mp4", "features-video-short-916"],
              ["Vídeo demonstração completo 16:9 (4 min)", "/docs/ConstruPilot_Demo_Complete_16x9.mp4", "features-video-full-169"],
              ["Vídeo demonstração completa 9:16", "/docs/ConstruPilot_Demo_Complete_9x16.mp4", "features-video-full-916"],
              ["Vídeo demo curta PT 16:9", "/docs/ConstruPilot_Demo_Curta_PT_16x9.mp4", "features-video-pt-short-169"],
              ["Vídeo demo curta PT 9:16", "/docs/ConstruPilot_Demo_Curta_PT_9x16.mp4", "features-video-pt-short-916"],
              ["Vídeo demo completa PT 16:9", "/docs/ConstruPilot_Demo_Completa_PT_16x9.mp4", "features-video-pt-full-169"],
            ].map(([label, href, tid]) => (
              <a key={tid} href={href} target="_blank" rel="noreferrer" data-testid={tid}
                 className="flex items-center gap-2 rounded-sm border border-border px-3 py-2.5 text-sm hover:bg-primary/5 transition-colors">
                <PlayCircle className="h-4 w-4 text-primary shrink-0" />{label}
              </a>
            ))}
          </div>
        </div>
      </section>

      <section className="max-w-4xl mx-auto px-4 py-14 text-center">
        <div className="surface p-8 rounded-xl">
          <PenTool className="h-8 w-8 text-primary mx-auto" />
          <h2 className="mt-4 font-display text-2xl font-bold">Pronto para estimar a sua primeira obra?</h2>
          <p className="mt-3 text-sm text-muted-foreground max-w-xl mx-auto">Crie uma conta em 30 segundos, ou teste com uma conta demo. Nenhum cartão bancário necessário para começar.</p>
          <div className="mt-6 flex flex-wrap gap-3 justify-center">
            <Link to="/login"><Button className="rounded-sm gap-2 h-11" data-testid="features-cta-bottom">Criar a minha conta <ArrowRight className="h-4 w-4" /></Button></Link>
          </div>
          <div className="mt-6 flex flex-wrap gap-4 justify-center text-xs text-muted-foreground">
            {["Sem compromisso", "Contas de demonstração disponíveis", "Suporte em português"].map((t, i) => (
              <span key={i} className="flex items-center gap-1"><CheckCircle2 className="h-3.5 w-3.5 text-primary" />{t}</span>
            ))}
          </div>
        </div>
      </section>

      <Footer />
      <HelpChatbot />
    </div>
  );
}
