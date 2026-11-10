import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Play, Ruler, FileText, ReceiptText, Cuboid, FileSpreadsheet, Truck, Layers, Users, Check, ChevronDown } from "lucide-react";
import { SEO } from "@/components/SEO";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DemoShowcase } from "@/components/DemoShowcase";
import { FeatureClips } from "@/components/FeatureClips";
import { LandingLayout, LandingHeading, LandingPricing, scrollToLanding } from "@/components/landing/LandingLayout";
import { ProductPreview } from "@/components/landing/ProductPreview";
import { LandingProof } from "@/components/landing/LandingProof";
import { useOffer } from "@/components/OfferNotice";

const FEATURES = [
  { id: "metre", icon: Ruler, clip: "metre", tag: "Plantas e medições", title: "Meça a obra na planta, sem régua nem calculadora", desc: "Importe as suas plantas PDF, DWG ou DXF, calibre a escala e controle as suas áreas, comprimentos e volumes.", to: "/plan" },
  { id: "devis", icon: FileText, clip: "devis_editeur", tag: "Orçamentos à sua imagem", title: "Responda ao cliente com um orçamento assinado antes de ele contratar outro", desc: "Estruture os seus artigos, ajuste os seus preços e tenha os descontos, o IVA e os totais à mão.", to: "/devis-editeur" },
  { id: "factures", icon: ReceiptText, clip: "factures", tag: "Faturas e autos de medição", title: "Fature o que foi executado, auto a auto", desc: "Encontre os seus documentos, prepare os seus autos de medição e as suas exportações de faturação.", to: "/factures" },
  { id: "dpgf", icon: FileSpreadsheet, clip: "dpgf", tag: "Mapa de quantidades e caderno de encargos", title: "Responda ao concurso depressa, com quantidades que pode defender", desc: "Reúna as informações do processo para preparar uma orçamentação que pode verificar e completar.", to: "/dpgf" },
  { id: "escaliers", icon: Cuboid, clip: "escaliers", tag: "Escadas 3D", title: "Mostre ao cliente a escada antes de a construir", desc: "Explore a geometria da sua escada e consulte as suas dimensões numa vista interativa.", to: "/escaliers" },
  { id: "appro", icon: Truck, clip: null, tag: "Aprovisionamento", title: "Tenha os materiais na obra no dia certo, sem custos surpresa", desc: "Organize os materiais, as encomendas e os custos no processo da obra.", to: "/appro" },
  { id: "multiniveaux", icon: Layers, clip: "multiniveaux", tag: "Projetos multinível", title: "Some as quantidades de todos os pisos num só projeto", desc: "Encontre as plantas de cada piso e reúna as quantidades do seu projeto.", to: "/plan" },
  { id: "equipe", icon: Users, clip: null, tag: "A sua equipa, reunida", title: "Passe de trabalhador independente a pequena empresa sem perder o fio", desc: "Partilhe as informações úteis e organize os acessos dos seus colaboradores.", to: "/equipe" },
];

// Ofertas B2B 2026-11 (fonte: backend/engines/commercial_plans.py). Enterprise: sob contacto, sem preço.
const PLANS = [
  { name: "Solo", price: "99 €", period: "/mês + IVA", popular: false, tid: "plan-pro-artisan-cta",
    desc: "Arquitetos, engenheiros, medidores orçamentistas e técnicos independentes.",
    features: ["1 utilizador · 10 projetos ativos", "100 páginas técnicas processadas / mês", "Importação de PDF, DWG e DXF", "Medições, quantidades e orçamentos", "Exportação PDF e Excel"] },
  { name: "Professional", price: "249 €", period: "/mês + IVA", popular: true, tid: "plan-pro-business-cta",
    desc: "Gabinetes de arquitetura e engenharia, pequenas construtoras, empresas de especialidades.",
    features: ["5 utilizadores · 50 projetos ativos", "750 páginas técnicas processadas / mês", "Clientes, propostas e orçamentos com o seu logótipo", "Relatórios de custos e margens", "Suporte prioritário"] },
  { name: "Business", price: "599 €", period: "/mês + IVA", popular: false, tid: "plan-business-cta",
    desc: "Construtoras com várias equipas e múltiplas obras.",
    features: ["15 utilizadores · 200 projetos ativos", "3 000 páginas técnicas processadas / mês", "Custos previstos vs reais, orçamento vs execução", "Permissões por função e auditoria", "Onboarding assistido"] },
];

const FAQ = [
  { q: "Como verificar as quantidades obtidas de uma planta?", a: "Calibre a escala, controle os elementos identificados e complete as informações em falta. A leitura da planta pode exigir correções: as quantidades devem ser verificadas antes de serem utilizadas num orçamento." },
  { q: "Posso utilizar os meus próprios preços?", a: "Pode preparar os seus orçamentos com os seus preços e o seu catálogo e depois ajustar os artigos, descontos e taxas de IVA no editor." },
  { q: "Os meus dados são exportáveis?", a: "Sim. Os seus orçamentos e faturas descarregam-se em PDF e os mapas de quantidades e as medições em Excel, a qualquer momento. Pode também pedir a exportação completa dos seus dados (direito de portabilidade) para info@construpilot.pt." },
  { q: "O que acontece às minhas obras se cancelar?", a: "As suas obras e os seus documentos não são apagados quando cancela: deixa apenas de ter acesso às funções pagas e pode continuar a consultar e a descarregar os seus ficheiros. Se quiser que tudo seja apagado, elimina a conta e todos os dados na página construpilot.pt/eliminar-conta." },
  { q: "Pode ser utilizado no telemóvel?", a: "A plataforma abre no seu navegador. Pode consultar os seus processos e utilizar as funções adaptadas ao telemóvel; um ecrã grande continua a ser mais confortável para trabalhar em plantas detalhadas." },
];

export default function LandingPro() {
  const navigate = useNavigate();
  const offer = useOffer();
  const offerNote = !offer ? "" : offer.free_promo
    ? "Fase de lançamento · acesso completo grátis · sem cartão"
    : offer.trial_days ? `Experiência de ${offer.trial_days} dias · cartão pedido, sem débito antes do fim da experiência · sem fidelização` : "Sem fidelização";
  const [preview, setPreview] = useState(null);
  const [videosOpen, setVideosOpen] = useState(false);
  useEffect(() => { try { if (localStorage.getItem("construpilot_audience") === "particulier") navigate("/particulares", { replace: true }); } catch {} }, [navigate]);
  const showDemo = () => { setVideosOpen(true); scrollToLanding("landing-demo"); };
  return <LandingLayout audience="pro">
    <SEO title="ConstruPilot Pro — Medições, orçamentos e acompanhamento de obra" description="Reúna as suas plantas, medições, orçamentos e faturas num espaço de trabalho de construção pensado para profissionais e empresas. Descubra o ConstruPilot Pro."
      canonical="/" keywords="software orçamentos construção, medição em planta, orçamentação construção, gestão de obra"
      jsonLd={{"@context":"https://schema.org","@graph":[{"@type":"SoftwareApplication",name:"ConstruPilot Pro",applicationCategory:"BusinessApplication",operatingSystem:"Web",offers:[{"@type":"Offer",name:"Solo",price:"99",priceCurrency:"EUR"},{"@type":"Offer",name:"Professional",price:"249",priceCurrency:"EUR"},{"@type":"Offer",name:"Business",price:"599",priceCurrency:"EUR"}]},{"@type":"FAQPage",mainEntity:FAQ.map(f=>({"@type":"Question",name:f.q,acceptedAnswer:{"@type":"Answer",text:f.a}}))}]}} />
    <section className="landing-hero landing-section" data-testid="pro-hero">
      <div className="landing-hero-copy"><p className="landing-eyebrow"><span className="pt-flag-dot" aria-hidden="true" />FEITO PARA OS PROFISSIONAIS DA CONSTRUÇÃO EM PORTUGAL E SEUS CLIENTES</p>
        <h1>Medições e orçamentos de obras,<br /><em>da planta ao acompanhamento</em></h1>
        <p className="landing-hero-pain" data-testid="pro-hero-pain">Chega de medir à mão e repetir orçamentos em folhas de cálculo.</p>
        <p className="landing-hero-description">Da primeira planta ao acompanhamento da obra, encontre as suas medições, orçamentos e documentos num espaço de trabalho pensado para o terreno.</p>
        <div className="landing-hero-actions"><Link to="/inscription" className="landing-button" data-testid="pro-hero-primary-cta">Experimentar o ConstruPilot <ArrowRight size={18} /></Link><a href="#landing-demo" className="landing-button landing-button-outline" onClick={e=>{e.preventDefault();showDemo();}} data-testid="pro-hero-secondary-cta"><Play size={16} />Ver a demonstração em vídeo</a></div>
        <p className="landing-hero-note">{offerNote}{offerNote ? " · " : ""}<Link to="/confidentialite" data-testid="pro-hero-privacy">Os seus dados e a privacidade</Link></p>
        <div className="landing-hero-proof"><span><Check size={15} />Plantas e medições</span><span><Check size={15} />Orçamentos e faturas</span><span><Check size={15} />Processos de obra</span></div>
      </div>
      <ProductPreview />
    </section>
    <div className="azulejo-band" aria-hidden="true" />
    <div className="landing-ribbon"><span>Menos dispersão.</span><strong>O futuro não se espera, constrói-se.</strong><span>No escritório como na obra.</span></div>
    <section className="landing-section" id="landing-how"><LandingHeading eyebrow="Uma continuidade, do início ao fim" title="A sua obra avança. As suas informações também." />
      <div className="landing-steps">{[{title:"Responda ao concurso depressa",desc:"As plantas, as peças do processo e o pedido do cliente no mesmo sítio, para orçamentar no próprio dia.",icon:Ruler},{title:"Confie nas quantidades",desc:"Medições controladas na planta e um orçamento construído artigo a artigo, sem refazer as contas à mão.",icon:FileText},{title:"Responda ao cliente primeiro",desc:"Os documentos, as próximas ações e as conversas da equipa à mão, para não perder a obra por responder tarde.",icon:Users}].map((s,i)=><article key={s.title}><div><span>0{i+1}</span><s.icon size={23} /></div><h3>{s.title}</h3><p>{s.desc}</p></article>)}</div>
    </section>
    <section className="landing-section" id="landing-tools" data-testid="pro-features"><LandingHeading eyebrow="A sua caixa de ferramentas" title="Tudo se encontra. Tudo se acompanha.">As funções essenciais ficam perto; as ferramentas especializadas estão lá quando precisa delas.</LandingHeading>
      <div className="landing-feature-grid">{FEATURES.map(f=><button type="button" key={f.id} className="landing-feature-card" onClick={()=>setPreview(f)} data-testid={`pro-feature-${f.id}`}><span className="landing-feature-icon"><f.icon size={23} /></span><small>{f.tag}</small><h3>{f.title}</h3><p>{f.desc}</p><span className="landing-card-link">Descobrir <ArrowRight size={17} /></span></button>)}</div>
      <Link to="/comparatif" className="landing-text-link" data-testid="pro-hero-comparatif-cta">Comparar as soluções para a construção <ArrowRight size={16} /></Link>
      <Link to="/connect" className="landing-text-link" data-testid="pro-connect-cta">Qual é o seu maior desafio na construção? Veja como o ConstruPilot ajuda, em 3 minutos <ArrowRight size={16} /></Link>
    </section>
    <section className="landing-section landing-video-section" id="landing-demo"><details open={videosOpen} onToggle={e=>setVideosOpen(e.currentTarget.open)} data-testid="landing-videos"><summary><span><small>VER NA PRÁTICA</small><strong>Descubra as ferramentas em ação.</strong></span><span className="landing-video-play"><Play size={21} /></span></summary>{videosOpen&&<div><DemoShowcase /><FeatureClips title="As funções Pro, em vídeo" subtitle="Percorra as demonstrações das ferramentas que lhe interessam." keys={["metre","devis_editeur","escaliers","factures","dpgf","multiniveaux"]} /></div>}</details></section>
    <LandingPricing plans={PLANS} pro />
    <LandingProof />
    <section className="landing-section landing-faq"><LandingHeading eyebrow="As suas perguntas" title="Algumas referências antes de começar." />{FAQ.map(f=><details key={f.q}><summary>{f.q}<ChevronDown size={18} /></summary><p>{f.a}</p></details>)}</section>
    <section className="landing-section"><div className="landing-final"><p className="landing-eyebrow">CONSTRUPILOT PRO</p><h2>Uma obra bem preparada<br />começa aqui.</h2><Link to="/inscription" className="landing-button landing-button-ivory" data-testid="pro-bottom-cta">Descobrir o meu espaço Pro <ArrowRight size={18} /></Link><Link to="/particulares" className="landing-audience-link" onClick={()=>{try{localStorage.setItem("construpilot_audience","particulier");}catch{}}}>Está a remodelar a sua habitação? Descubra o espaço Particulares.</Link></div></section>
    <Dialog open={!!preview} onOpenChange={open=>!open&&setPreview(null)}><DialogContent className="landing-feature-dialog" data-testid="pro-feature-preview">{preview&&<><DialogHeader><DialogTitle>{preview.title}</DialogTitle><DialogDescription>{preview.desc}</DialogDescription></DialogHeader>{preview.clip?null:<p>Encontre os detalhes das funções e dos níveis de acesso nas nossas ofertas.</p>}<div className="landing-dialog-actions"><Link to="/inscription" className="landing-button" data-testid="pro-feature-preview-cta">Experimentar o ConstruPilot <ArrowRight size={17} /></Link><Link to={preview.to} className="landing-button landing-button-outline" data-testid="pro-feature-preview-open">Abrir a ferramenta</Link></div></>}</DialogContent></Dialog>
  </LandingLayout>;
}
