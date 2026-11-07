// Auditoria de site (D3.3 / D3.5) : pessoas reais por trás do produto, a um clique do rodapé.
// Só factos confirmados pelo fundador. As fotografias ficam em /public/equipa/<id>.jpg quando existirem
// (enquanto não existirem, mostram-se as iniciais).
import { useState } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Linkedin, Mail } from "lucide-react";
import { SEO } from "@/components/SEO";
import { LandingLayout, LandingHeading } from "@/components/landing/LandingLayout";

const LINKEDIN = "https://www.linkedin.com/in/construpilot-construpilot-00189942a";
const TEAM = [
  { id: "martinho-araujo", name: "Martinho Araujo", role: "Cofundador · produto e motores técnicos",
    desc: "Responsável pela parte técnica: a plataforma e os motores de medição e orçamentação." },
  { id: "angelo-cunha", name: "Ângelo Cunha", role: "Cofundador · ConstruPilot Portugal",
    desc: "Responsável pelo ConstruPilot em Portugal e pela parte de negócio." },
  { id: "diana-araujo", name: "Diana Araújo", role: "Marketing e relação com clientes",
    desc: "Responsável pelo marketing e pela relação com os clientes." },
];

const initials = (n) => n.split(" ").map((w) => w[0]).slice(0, 2).join("");

function Person({ p }) {
  const [photo, setPhoto] = useState(true);
  return <article className="landing-about-person" data-testid={`about-${p.id}`}>
    {photo ? <img src={`/equipa/${p.id}.jpg`} alt={`Fotografia de ${p.name}`} width="72" height="72" onError={() => setPhoto(false)} />
      : <span className="landing-proof-avatar" aria-hidden="true">{initials(p.name)}</span>}
    <h3>{p.name}</h3><small>{p.role}</small><p>{p.desc}</p>
  </article>;
}

export default function About() {
  return <LandingLayout audience="pro">
    <SEO title="Sobre o ConstruPilot — a equipa por trás do produto" description="Quem construiu o ConstruPilot: uma equipa familiar, autofinanciada, que fala português, francês, inglês e espanhol. Contacto direto com os fundadores."
      canonical="/sobre" lang="pt"
      jsonLd={{"@context":"https://schema.org","@type":"AboutPage",name:"Sobre o ConstruPilot",mainEntity:{"@type":"Organization",name:"ConstruPilot",url:"https://construpilot.pt",email:"info@construpilot.pt",sameAs:[LINKEDIN],
        founder:TEAM.slice(0,2).map((t)=>({"@type":"Person",name:t.name,jobTitle:t.role}))}}} />
    <section className="landing-section landing-about" data-testid="about-page">
      <LandingHeading eyebrow="Quem somos" title="Pessoas reais por trás do ConstruPilot." />
      <div className="landing-about-story">
        <p>O ConstruPilot foi construído pelos próprios fundadores, Martinho Araujo e Ângelo Cunha: uma equipa familiar, autofinanciada, que trabalha em português, francês, inglês e espanhol.</p>
        <p>A plataforma está em fase beta em Portugal e em França, com patente registada (FR2611044).</p>
        <p>Vamos estar no Web Summit Lisboa, de 9 a 12 de novembro de 2026: venha falar connosco.</p>
      </div>
      <div className="landing-about-team">{TEAM.map((p) => <Person key={p.id} p={p} />)}</div>
      <div className="landing-proof-actions">
        <a href="mailto:info@construpilot.pt" className="landing-button landing-button-outline" data-testid="about-mail"><Mail size={16} />info@construpilot.pt</a>
        <a href={LINKEDIN} target="_blank" rel="noreferrer" className="landing-text-link" data-testid="about-linkedin"><Linkedin size={16} />ConstruPilot no LinkedIn</a>
        <Link to="/inscription" className="landing-button" data-testid="about-cta">Experimentar o ConstruPilot <ArrowRight size={17} /></Link>
      </div>
    </section>
  </LandingLayout>;
}
