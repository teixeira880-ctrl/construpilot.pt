import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { ArrowRight, Sparkles, Camera, FileSearch, Wrench, Calculator, MessageSquare, Check, Play, ChevronDown } from "lucide-react";
import { SEO } from "@/components/SEO";
import { FeatureClips } from "@/components/FeatureClips";
import { useAuth } from "@/context/AuthContext";
import { api } from "@/lib/api";
import { LandingLayout, LandingHeading, LandingPricing, scrollToLanding } from "@/components/landing/LandingLayout";

const EXAMPLE = "Remodelar uma casa de banho de 8 m² com um duche de nível, azulejo e um móvel de lavatório.";
const CHIPS = ["Remodelação de casa de banho 8 m²", "Isolamento do sótão 60 m²", "Pintura T3 70 m²", "Cozinha equipada"];
const TOOLS = [
  { icon: Sparkles, tag: "Preparar", title: "Um projeto, passo a passo", desc: "Organize os trabalhos, os materiais e as etapas da sua remodelação.", to: "/smart-project" },
  { icon: FileSearch, tag: "Compreender", title: "Um olhar sobre os seus orçamentos", desc: "Compare os artigos e identifique os pontos a esclarecer com o seu profissional.", to: "/scanner-devis" },
  { icon: Camera, tag: "Explorar", title: "A sua divisão em imagens", desc: "Utilize uma fotografia para dar contexto e preparar as suas perguntas.", to: "/photo" },
  { icon: Wrench, tag: "Escolher", title: "Fazer sozinho ou delegar", desc: "Compare as opções consoante o seu orçamento, as suas competências e a obra.", to: "/diy" },
  { icon: Calculator, tag: "Calcular", title: "As quantidades certas", desc: "Estime as necessidades de tinta, azulejo ou isolamento a partir das suas medidas.", to: "/calculateurs" },
  { icon: MessageSquare, tag: "Ser acompanhado", title: "As suas perguntas sobre obras", desc: "Prepare as suas conversas e encontre explicações ao longo do projeto.", to: "/coach" },
];
const PLANS = [
  { name: "Grátis", price: "0 €", period: "vitalício", popular: false, tid: "plan-particulier-free-cta",
    desc: "Para explorar e fazer uma primeira estimativa.",
    features: ["3 estimativas expresso / mês", "Calculadoras de áreas e volumes", "Guia de preços médios por região"] },
  { name: "Passe Tranquilidade", price: "19 €", period: "/mois sans engagement", popular: true, tid: "plan-particulier-pass-cta",
    desc: "Acompanhamento completo durante todas as suas obras.",
    features: ["Estimativas e Smart Projects ilimitados", "Scanner de orçamentos ilimitado", "Análise de fotografias e deteção de riscos", "Coach IA travaux 24/7", "Contacto prioritário com profissionais"] },
];

export default function LandingParticuliers() {
  const navigate = useNavigate();
  const { user, loading } = useAuth();
  const [name,setName]=useState("");const [email,setEmail]=useState("");const [description,setDescription]=useState("");
  const [error,setError]=useState("");const [videosOpen,setVideosOpen]=useState(false);
  useEffect(()=>{try{const sp=new URLSearchParams(window.location.search);["utm_source","utm_medium","utm_campaign"].forEach(k=>{const v=sp.get(k);if(v)sessionStorage.setItem(`construpilot_${k}`,v);});}catch{}},[]);
  const launch = e => {
    e.preventDefault();if(loading)return;setError("");
    const text=description.trim()||EXAMPLE,mail=email.trim();let leadPayload;
    try {
      sessionStorage.setItem("estimator_prefill",JSON.stringify({description:text,_raw:text}));
      if(mail)sessionStorage.setItem("construpilot_lead_email",mail);
      if(name.trim())sessionStorage.setItem("construpilot_lead_name",name.trim());
      leadPayload={name:name.trim(),email:mail,description:text,source:sessionStorage.getItem("construpilot_utm_source")||"landing-particuliers",utm_source:sessionStorage.getItem("construpilot_utm_source")||"",utm_medium:sessionStorage.getItem("construpilot_utm_medium")||"",utm_campaign:sessionStorage.getItem("construpilot_utm_campaign")||""};
      if(!user)sessionStorage.setItem("construpilot_pending_lead",JSON.stringify(leadPayload));
    } catch { setError("O seu navegador não conseguiu guardar o projeto. Autorize o armazenamento para este site e tente novamente.");return; }
    if(user){if(mail)api.post("/leads",leadPayload).catch(()=>{});navigate("/estimation");}
    else navigate(`/inscription?email=${encodeURIComponent(mail)}&signup=1`);
  };
  return <LandingLayout audience="particulier">
    <SEO title="ConstruPilot — Prepare o seu projeto de remodelação" description="Estime o orçamento das suas obras, compreenda os seus orçamentos e prepare as etapas da sua remodelação com o ConstruPilot para particulares." canonical="/particuliers" keywords="estimativa obras, orçamento remodelação, comparar orçamentos"
      jsonLd={{"@context":"https://schema.org","@type":"WebApplication",name:"ConstruPilot para particulares",applicationCategory:"UtilitiesApplication",operatingSystem:"Web",offers:[{"@type":"Offer",name:"Grátis",price:"0",priceCurrency:"EUR"},{"@type":"Offer",name:"Passe Tranquilidade",price:"19",priceCurrency:"EUR"}]}} />
    <section className="landing-hero landing-section" data-testid="particuliers-hero">
      <div className="landing-hero-copy"><p className="landing-eyebrow"><span />PARA A SUA CASA, O SEU APARTAMENTO</p><h1>Os seus desejos ganham forma.<br /><em>O seu projeto também.</em></h1>
        <p className="landing-hero-description">Um orçamento a preparar, uma proposta a compreender, obras a organizar. Avance com referências claras, do primeiro desejo às próximas etapas.</p>
        <div className="landing-hero-actions"><button type="button" className="landing-button" onClick={()=>scrollToLanding("landing-estimator",true)}>Preparar o meu projeto <ArrowRight size={18} /></button><Link to="/scanner-devis" className="landing-text-link" data-testid="particuliers-hero-secondary-cta">Já tenho um orçamento <ArrowRight size={17} /></Link></div>
        <div className="landing-hero-proof"><span><Check size={15} />Grátis para começar</span><span><Check size={15} />Sem cartão bancário</span></div>
        <p className="landing-hero-note">Uma estimativa dá uma ordem de grandeza. O seu profissional confirma os trabalhos e o preço final.</p>
      </div>
      <form className="landing-estimator" id="landing-estimator" data-testid="particuliers-form" onSubmit={launch}>
        <div className="landing-form-heading"><span className="landing-feature-icon"><Sparkles size={23} /></span><span><small>O SEU PONTO DE PARTIDA</small><h2>E se falássemos das suas obras?</h2></span></div>
        <label htmlFor="landing-description">Descreva o seu projeto</label><textarea id="landing-description" rows={4} value={description} onChange={e=>setDescription(e.target.value)} placeholder={EXAMPLE} data-testid="particuliers-description" />
        <div className="landing-project-chips" aria-label="Exemplos de projetos">{CHIPS.map((c,i)=><button type="button" key={c} onClick={()=>setDescription(c)} aria-pressed={description===c} data-testid={`part-chip-${c.slice(0,6)}`}>{["Casa de banho","Isolamento","Pintura","Cozinha"][i]}</button>)}</div>
        <div className="landing-contact-fields"><div><label htmlFor="landing-name">Nome <span>(opcional)</span></label><input id="landing-name" autoComplete="given-name" value={name} onChange={e=>setName(e.target.value)} placeholder="O seu primeiro nome" data-testid="particuliers-name" /></div><div><label htmlFor="landing-email">E-mail <span>(opcional)</span></label><input id="landing-email" autoComplete="email" type="email" value={email} onChange={e=>setEmail(e.target.value)} placeholder="vous@exemple.fr" data-testid="particuliers-email" /></div></div>
        {error&&<p role="alert" className="landing-form-error">{error}</p>}
        <button type="submit" className="landing-button" disabled={loading} data-testid="particuliers-hero-primary-cta">{loading?"A carregar…":"Estimar o meu projeto"}<ArrowRight size={18} /></button><p className="landing-form-note">{user?"O seu projeto espera por si no estimador.":"Crie depois a sua conta para encontrar o seu projeto."}</p>
      </form>
    </section>
    <div className="landing-ribbon"><span>A sua ideia.</span><strong>Referências para avançar.</strong><span>Um projeto à sua medida.</span></div>
    <section className="landing-section" id="landing-how" data-testid="particuliers-steps"><LandingHeading eyebrow="Simples, desde o início" title="Uma pergunta de cada vez. Um projeto mais claro." />
      <div className="landing-steps">{[{title:"Conte-nos o seu projeto",desc:"A divisão, a área e o que pretende mudar.",icon:MessageSquare},{title:"Explore o seu orçamento",desc:"Uma estimativa para comparar os artigos e as suas prioridades.",icon:Calculator},{title:"Prepare o que se segue",desc:"As suas perguntas ao profissional, os seus orçamentos e as próximas etapas.",icon:FileSearch}].map((s,i)=><article key={s.title}><div><span>0{i+1}</span><s.icon size={23} /></div><h3>{s.title}</h3><p>{s.desc}</p></article>)}</div>
    </section>
    <section className="landing-section" id="landing-tools" data-testid="particuliers-tools"><LandingHeading eyebrow="Em cada etapa, a ferramenta certa" title="Menos perguntas em aberto.">Compreender, comparar, calcular: encontre as ferramentas úteis no mesmo lugar.</LandingHeading><div className="landing-feature-grid landing-feature-grid-home">{TOOLS.map(t=><Link key={t.to} to={t.to} className="landing-feature-card" data-testid={`particulier-tool-${t.to.slice(1)}`}><span className="landing-feature-icon"><t.icon size={23} /></span><small>{t.tag}</small><h3>{t.title}</h3><p>{t.desc}</p><span className="landing-card-link">Descobrir <ArrowRight size={17} /></span></Link>)}</div></section>
    <section className="landing-section landing-video-section" id="landing-demo"><details open={videosOpen} onToggle={e=>setVideosOpen(e.currentTarget.open)} data-testid="landing-videos"><summary><span><small>EM POUCAS IMAGENS</small><strong>Descubra o que pode fazer.</strong></span><span className="landing-video-play"><Play size={21} /></span></summary>{videosOpen&&<FeatureClips title="As suas ferramentas, em vídeo" subtitle="Descubra a estimativa e as calculadoras em situação real." keys={["estimation","calculateurs"]} />}</details></section>
    <LandingPricing plans={PLANS} />
    <section className="landing-section landing-faq"><LandingHeading eyebrow="Bom saber" title="Referências, desde o início." />{[{q:"A estimativa substitui um orçamento de um profissional?",a:"Não. Permite preparar um orçamento a partir das informações dadas. O estado real da habitação, os materiais escolhidos e a visita de um profissional podem fazer variar o montante."},{q:"Posso começar sem conhecer todas as dimensões?",a:"Descreva o que sabe e indique as informações em falta. Poderá completar o projeto à medida que avança."},{q:"Posso utilizar o ConstruPilot no meu telemóvel?",a:"Sim, a partir do seu navegador: prepare o seu projeto, consulte as ferramentas e encontre as suas informações."}].map(f=><details key={f.q}><summary>{f.q}<ChevronDown size={18} /></summary><p>{f.a}</p></details>)}</section>
    <section className="landing-section"><div className="landing-final"><p className="landing-eyebrow">UM PROJETO À SUA MEDIDA</p><h2>A próxima etapa?<br />Falemos da sua.</h2><button type="button" className="landing-button landing-button-ivory" onClick={()=>scrollToLanding("landing-estimator",true)} data-testid="particuliers-cta-final">Preparar as minhas obras <ArrowRight size={18} /></button><Link to="/" className="landing-audience-link" onClick={()=>{try{localStorage.setItem("construpilot_audience","pro");}catch{}}}>É profissional da construção? Descubra o espaço Pro.</Link></div></section>
  </LandingLayout>;
}
