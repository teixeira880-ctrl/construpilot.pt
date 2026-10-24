import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Play, Ruler, FileText, ReceiptText, Cuboid, FileSpreadsheet, Truck, Layers, Users, Check, ChevronDown } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DemoShowcase } from "@/components/DemoShowcase";
import { FeatureClips } from "@/components/FeatureClips";
import { LandingLayout, LandingHeading, LandingPricing, scrollToLanding } from "@/components/landing/LandingLayout";
import { ProductPreview } from "@/components/landing/ProductPreview";

const FEATURES = [
  { id: "metre", icon: Ruler, clip: "metre", tag: "Ler e medir", title: "Plantas e medições", desc: "Importe as suas plantas PDF, DWG ou DXF, calibre a escala e controle as suas áreas, comprimentos e volumes.", to: "/plan" },
  { id: "devis", icon: FileText, clip: "devis_editeur", tag: "Orçamentar e apresentar", title: "Orçamentos à sua imagem", desc: "Estruture os seus artigos, ajuste os seus preços e tenha os descontos, o IVA e os totais à mão.", to: "/devis-editeur" },
  { id: "factures", icon: ReceiptText, clip: "factures", tag: "Faturar e acompanhar", title: "Faturas e autos de medição", desc: "Encontre os seus documentos, prepare os seus autos de medição e as suas exportações de faturação.", to: "/factures" },
  { id: "dpgf", icon: FileSpreadsheet, clip: "dpgf", tag: "Organizar as peças", title: "Mapa de quantidades e caderno de encargos", desc: "Reúna as informações do processo para preparar uma orçamentação que pode verificar e completar.", to: "/dpgf" },
  { id: "escaliers", icon: Cuboid, clip: "escaliers", tag: "Estudar uma solução", title: "Escadas 3D", desc: "Explore a geometria da sua escada e consulte as suas dimensões numa vista interativa.", to: "/escaliers" },
  { id: "appro", icon: Truck, clip: null, tag: "Preparar a obra", title: "Aprovisionamento", desc: "Organize os materiais, as encomendas e os custos no processo da obra.", to: "/appro" },
  { id: "multiniveaux", icon: Layers, clip: "multiniveaux", tag: "Manter uma visão global", title: "Projetos multinível", desc: "Encontre as plantas de cada piso e reúna as quantidades do seu projeto.", to: "/plan" },
  { id: "equipe", icon: Users, clip: null, tag: "Trabalhar em conjunto", title: "A sua equipa, reunida", desc: "Partilhe as informações úteis e organize os acessos dos seus colaboradores.", to: "/equipe" },
];

const PLANS = [
  { name: "Pro Artesão", price: "149 €", period: "/mês + IVA", popular: false, tid: "plan-pro-artisan-cta",
    desc: "Profissionais independentes e pequenas equipas.",
    features: ["Medição em planta ilimitada", "Orçamentos e faturas eletrónicas", "Cálculo de escadas 3D (RGEU)", "Exportação PDF com o seu logótipo", "Suporte prioritário de construção"] },
  { name: "Pro Empresa", price: "249 €", period: "/mês + IVA", popular: true, tid: "plan-pro-business-cta",
    desc: "PME de construção, empreiteiros gerais, diretores de obra.",
    features: ["Tudo do Pro Artesão +", "Análise do caderno de encargos e importação do mapa de quantidades", "Projetos multinível e equipa", "Portal de subempreiteiros e aprovisionamento", "Acompanhamento na implementação"] },
];

const FAQ = [
  { q: "Como verificar as quantidades obtidas de uma planta?", a: "Calibre a escala, controle os elementos identificados e complete as informações em falta. A leitura da planta pode exigir correções: as quantidades devem ser verificadas antes de serem utilizadas num orçamento." },
  { q: "Posso utilizar os meus próprios preços?", a: "Pode preparar os seus orçamentos com os seus preços e o seu catálogo e depois ajustar os artigos, descontos e taxas de IVA no editor." },
  { q: "Pode ser utilizado no telemóvel?", a: "A plataforma abre no seu navegador. Pode consultar os seus processos e utilizar as funções adaptadas ao telemóvel; um ecrã grande continua a ser mais confortável para trabalhar em plantas detalhadas." },
];

export default function LandingPro() {
  const navigate = useNavigate();
  const [preview, setPreview] = useState(null);
  const [videosOpen, setVideosOpen] = useState(false);
  useEffect(() => { try { if (localStorage.getItem("construpilot_audience") === "particulier") navigate("/particulares", { replace: true }); } catch {} }, [navigate]);
  const showDemo = () => { setVideosOpen(true); scrollToLanding("landing-demo"); };
  return <LandingLayout audience="pro">
    <SEO title="ConstruPilot Pro — Medições, orçamentos e acompanhamento de obra" description="Reúna as suas plantas, medições, orçamentos e faturas num espaço de trabalho de construção pensado para profissionais e empresas. Descubra o ConstruPilot Pro."
      canonical="/" keywords="software orçamentos construção, medição em planta, orçamentação construção, gestão de obra"
      jsonLd={{"@context":"https://schema.org","@type":"SoftwareApplication",name:"ConstruPilot Pro",applicationCategory:"BusinessApplication",operatingSystem:"Web",offers:[{"@type":"Offer",name:"Pro Artesão",price:"149",priceCurrency:"EUR"},{"@type":"Offer",name:"Pro Empresa",price:"249",priceCurrency:"EUR"}]}} />
    <section className="landing-hero landing-section" data-testid="pro-hero">
      <div className="landing-hero-copy"><p className="landing-eyebrow"><span className="pt-flag-dot" aria-hidden="true" />FEITO PARA OS PROFISSIONAIS DA CONSTRUÇÃO EM PORTUGAL E SEUS CLIENTES</p>
        <h1>O futuro não se espera, constrói-se<br /><em>Ambição, liderança e inovação</em></h1>
        <p className="landing-hero-description">Da primeira planta ao acompanhamento da obra, encontre as suas medições, orçamentos e documentos num espaço de trabalho pensado para o terreno.</p>
        <div className="landing-hero-actions"><Link to="/inscription" className="landing-button" data-testid="pro-hero-primary-cta">Experimentar o ConstruPilot <ArrowRight size={18} /></Link><button type="button" className="landing-button landing-button-outline" onClick={showDemo} data-testid="pro-hero-secondary-cta"><Play size={16} />Ver a demonstração</button></div>
        <p className="landing-hero-note">Experiência de 7 dias · Cartão obrigatório · Sem fidelização após a experiência</p>
        <div className="landing-hero-proof"><span><Check size={15} />Plantas e medições</span><span><Check size={15} />Orçamentos e faturas</span><span><Check size={15} />Processos de obra</span></div>
      </div>
      <ProductPreview />
    </section>
    <div className="azulejo-band" aria-hidden="true" />
    <div className="landing-ribbon"><span>Menos dispersão.</span><strong>Mais espaço para a sua profissão.</strong><span>No escritório como na obra.</span></div>
    <section className="landing-section" id="landing-how"><LandingHeading eyebrow="Uma continuidade, do início ao fim" title="A sua obra avança. As suas informações também." />
      <div className="landing-steps">{[{title:"Reúna",desc:"As plantas, as peças do processo e os pedidos do cliente.",icon:Ruler},{title:"Prepare",desc:"Quantidades controladas e um orçamento construído artigo a artigo.",icon:FileText},{title:"Faça a gestão",desc:"Os documentos, as próximas ações e as conversas da equipa.",icon:Users}].map((s,i)=><article key={s.title}><div><span>0{i+1}</span><s.icon size={23} /></div><h3>{s.title}</h3><p>{s.desc}</p></article>)}</div>
    </section>
    <section className="landing-section" id="landing-tools" data-testid="pro-features"><LandingHeading eyebrow="A sua caixa de ferramentas" title="Tudo se encontra. Tudo se acompanha.">As funções essenciais ficam perto; as ferramentas especializadas estão lá quando precisa delas.</LandingHeading>
      <div className="landing-feature-grid">{FEATURES.map(f=><button type="button" key={f.id} className="landing-feature-card" onClick={()=>setPreview(f)} data-testid={`pro-feature-${f.id}`}><span className="landing-feature-icon"><f.icon size={23} /></span><small>{f.tag}</small><h3>{f.title}</h3><p>{f.desc}</p><span className="landing-card-link">Descobrir <ArrowRight size={17} /></span></button>)}</div>
      <Link to="/comparatif" className="landing-text-link" data-testid="pro-hero-comparatif-cta">Comparar as soluções para a construção <ArrowRight size={16} /></Link>
    </section>
    <section className="landing-section landing-video-section" id="landing-demo"><details open={videosOpen} onToggle={e=>setVideosOpen(e.currentTarget.open)} data-testid="landing-videos"><summary><span><small>VER NA PRÁTICA</small><strong>Descubra as ferramentas em ação.</strong></span><span className="landing-video-play"><Play size={21} /></span></summary>{videosOpen&&<div><DemoShowcase /><FeatureClips title="As funções Pro, em vídeo" subtitle="Percorra as demonstrações das ferramentas que lhe interessam." keys={["metre","devis_editeur","escaliers","factures","dpgf","multiniveaux"]} /></div>}</details></section>
    <LandingPricing plans={PLANS} pro />
    <section className="landing-section landing-faq"><LandingHeading eyebrow="As suas perguntas" title="Algumas referências antes de começar." />{FAQ.map(f=><details key={f.q}><summary>{f.q}<ChevronDown size={18} /></summary><p>{f.a}</p></details>)}</section>
    <section className="landing-section"><div className="landing-final"><p className="landing-eyebrow">CONSTRUPILOT PRO</p><h2>Uma obra bem preparada<br />começa aqui.</h2><Link to="/inscription" className="landing-button landing-button-ivory" data-testid="pro-bottom-cta">Descobrir o meu espaço Pro <ArrowRight size={18} /></Link><Link to="/particulares" className="landing-audience-link" onClick={()=>{try{localStorage.setItem("construpilot_audience","particulier");}catch{}}}>Está a remodelar a sua habitação? Descubra o espaço Particulares.</Link></div></section>
    <Dialog open={!!preview} onOpenChange={open=>!open&&setPreview(null)}><DialogContent className="landing-feature-dialog" data-testid="pro-feature-preview">{preview&&<><DialogHeader><DialogTitle>{preview.title}</DialogTitle><DialogDescription>{preview.desc}</DialogDescription></DialogHeader>{preview.clip?null:<p>Encontre os detalhes das funções e dos níveis de acesso nas nossas ofertas.</p>}<div className="landing-dialog-actions"><Link to="/inscription" className="landing-button" data-testid="pro-feature-preview-cta">Experimentar o ConstruPilot <ArrowRight size={17} /></Link><Link to={preview.to} className="landing-button landing-button-outline" data-testid="pro-feature-preview-open">Abrir a ferramenta</Link></div></>}</DialogContent></Dialog>
  </LandingLayout>;
}
