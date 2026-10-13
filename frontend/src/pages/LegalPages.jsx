import { Link } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

const CONTACT_EMAIL = "contact@construpilot.pt";
const EDITOR = "ConstruPilot";

const LegalLayout = ({ title, updated, testid, children }) => (
  <div className="max-w-3xl mx-auto px-6 py-14" data-testid={testid}>
    <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-6">
      <ArrowLeft className="h-4 w-4" /> Voltar ao início
    </Link>
    <h1 className="font-display text-3xl sm:text-4xl font-bold text-foreground">{title}</h1>
    <p className="text-xs text-muted-foreground mt-2">Última atualização: {updated}</p>
    <div className="prose prose-sm dark:prose-invert max-w-none mt-8 space-y-6 text-[15px] leading-relaxed text-foreground/90 [&_h2]:font-display [&_h2]:text-xl [&_h2]:font-bold [&_h2]:mt-8 [&_h2]:mb-2 [&_a]:text-primary">
      {children}
    </div>
  </div>
);

export const MentionsLegales = () => (
  <LegalLayout title="Informação legal" updated="Juin 2026" testid="page-mentions-legales">
    <h2>1. Editor do site</h2>
    <p>
      O site e a aplicação <strong>{EDITOR}</strong> são editados por {EDITOR}.<br />
      Forma jurídica: [A COMPLETAR — ex.: Lda./Unipessoal]<br />
      Sede: [A COMPLETAR — morada]<br />
      NIPC: [A COMPLETAR] · NIF intracomunitário: [A COMPLETAR]<br />
      Diretor da publicação: [A COMPLETAR — nome]<br />
      Contacto: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
    </p>

    <h2>2. Alojamento</h2>
    <p>
      A aplicação é alojada pela Emergent (infraestrutura cloud). Os dados são armazenados em servidores localizados na União Europeia. Para qualquer questão relativa ao alojamento, contacte-nos em <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>

    <h2>3. Propriedade intelectual</h2>
    <p>
      O conjunto dos conteúdos, marcas, logótipos, textos, interfaces e tecnologias presentes em
      {" "}{EDITOR} estão protegidos pelo direito da propriedade intelectual. Tecnologia protegida pela patente n.º FR2611044. É proibida qualquer reprodução ou representação, total ou parcial, sem autorização escrita.
    </p>

    <h2>4. Responsabilidade</h2>
    <p>
      As estimativas, orçamentações e análises fornecidas por {EDITOR} são dados a título indicativo e não constituem um compromisso contratual. O utilizador permanece o único responsável pela utilização que faz dos resultados produzidos.
    </p>

    <h2>5. Links e contacto</h2>
    <p>
      Ver também o nosso <Link to="/confidentialite">Política de privacidade</Link> e os nossos{" "}
      <Link to="/cgv">Condições gerais</Link>. Para qualquer reclamação:{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>
  </LegalLayout>
);

export const Confidentialite = () => (
  <LegalLayout title="Política de privacidade" updated="Juin 2026" testid="page-confidentialite">
    <p>
      {EDITOR} atribui grande importância à proteção dos seus dados pessoais, em conformidade com o Regulamento Geral de Proteção de Dados (RGPD) e a lei «Informática e Liberdades».
    </p>

    <h2>1. Responsável pelo tratamento</h2>
    <p>{EDITOR} — contacto: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</p>

    <h2>2. Dados recolhidos</h2>
    <p>
      Recolhemos: identidade e contactos (nome, e-mail), dados de conta e de autenticação, conteúdos que cria (orçamentos, obras, fotografias, documentos), informações da empresa (NIF, IVA, logótipo) e dados técnicos (registos, dispositivo).
    </p>

    <h2>3. Finalidades</h2>
    <p>
      Prestação do serviço (estimativa, orçamentos, faturas, obras), gestão da conta e da subscrição, faturação, suporte, melhoria do serviço e segurança. Os pagamentos são tratados pela Stripe; os e-mails pelo nosso prestador de envio.
    </p>

    <h2>4. Base legal e duração</h2>
    <p>
      Execução do contrato, obrigações legais (faturação), e interesse legítimo. Os dados são conservados durante a relação contratual e depois arquivados segundo os prazos legais aplicáveis.
    </p>

    <h2>5. Partilha</h2>
    <p>
      Os seus dados nunca são vendidos. Podem ser transmitidos aos nossos subcontratantes técnicos (alojamento, pagamento Stripe, envio de e-mails) estritamente para o funcionamento do serviço.
    </p>

    <h2>6. Os seus direitos</h2>
    <p>
      Dispõe de um direito de acesso, retificação, eliminação, portabilidade, limitação e oposição. Exerça-os em{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Pode contactar a CNPD em caso de litígio (www.cnpd.pt).
    </p>

    <h2>7. Cookies</h2>
    <p>
      Utilizamos cookies estritamente necessários ao funcionamento (sessão, autenticação) e, se for caso disso, cookies de medição de audiência. Pode gerir as suas preferências no seu navegador.
    </p>
  </LegalLayout>
);

export const CGV = () => (
  <LegalLayout title="Condições gerais de utilização e venda" updated="Juin 2026" testid="page-cgv">
    <h2>1. Objet</h2>
    <p>
      As presentes condições regem o acesso e utilização da aplicação {EDITOR}, bem como as subscrições pagas propostas.
    </p>

    <h2>2. Conta</h2>
    <p>
      O utilizador compromete-se a fornecer informações exatas e a preservar a confidencialidade dos seus identificadores. Cada conta é pessoal.
    </p>

    <h2>3. Subscrições e preços</h2>
    <p>
      {EDITOR} propõe funcionalidades gratuitas e subscrições pagas (Particular e Profissional). Os preços são indicados em euros, com IVA incluído se for caso disso. O pagamento é efetuado por cartão através da Stripe. A subscrição é renovada automaticamente e pode ser cancelada a qualquer momento; o cancelamento produz efeitos no fim do período em curso.
    </p>

    <h2>4. Direito de retratação</h2>
    <p>
      Para os consumidores, aplica-se o direito de retratação de 14 dias salvo renúncia expressa em caso de acesso imediato ao serviço digital. Contacto:{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>

    <h2>5. Disponibilidade e limitação de responsabilidade</h2>
    <p>
      {EDITOR} faz todos os esforços para assegurar a disponibilidade do serviço sem poder garanti-la de forma ininterrupta. As estimativas e orçamentos são fornecidos a título indicativo.
    </p>

    <h2>6. Dados pessoais</h2>
    <p>
      O tratamento dos dados está descrito na nossa{" "}
      <Link to="/confidentialite">Política de privacidade</Link>.
    </p>

    <h2>7. Direito aplicável</h2>
    <p>
      As presentes condições estão sujeitas ao direito francês. Em caso de litígio, será procurada uma solução amigável antes de qualquer ação judicial.
    </p>
  </LegalLayout>
);
