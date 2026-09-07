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
  <LegalLayout title="Informações legais" updated="Junho 2026" testid="page-mentions-legales">
    <h2>1. Editor do site</h2>
    <p>
      O site e a aplicação <strong>{EDITOR}</strong> são editados por {EDITOR}.<br />
      Forma jurídica: [A COMPLETAR — ex. Lda./ENI]<br />
      Sede: [A COMPLETAR — morada]<br />
      NIPC: [A COMPLETAR] · NIF: [A COMPLETAR]<br />
      Diretor da publicação: [A COMPLETAR — nome]<br />
      Contacto: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>
    </p>

    <h2>2. Alojamento</h2>
    <p>
      A aplicação é alojada por Emergent (infraestrutura na nuvem). Os dados são armazenados
      em servidores localizados na União Europeia. Para qualquer questão relativa ao
      alojamento, contacta-nos em <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>

    <h2>3. Propriedade intelectual</h2>
    <p>
      Todos os conteúdos, marcas, logótipos, textos, interfaces e tecnologias presentes em
      {" "}{EDITOR} estão protegidos pelo direito da propriedade intelectual. Tecnologia protegida
      pela patente n.º FR261104. Qualquer reprodução ou representação, total ou parcial, sem
      autorização escrita, é proibida.
    </p>

    <h2>4. Responsabilidade</h2>
    <p>
      As estimativas, orçamentos e análises fornecidos pelo {EDITOR} têm caráter indicativo e
      não constituem qualquer compromisso contratual. O utilizador é o único responsável pelo
      uso que faz dos resultados produzidos.
    </p>

    <h2>5. Ligações e contacto</h2>
    <p>
      Ver também a nossa <Link to="/confidentialite">Política de privacidade</Link> e os nossos{" "}
      <Link to="/cgv">Termos gerais</Link>. Para qualquer reclamação:{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>
  </LegalLayout>
);

export const Confidentialite = () => (
  <LegalLayout title="Política de privacidade" updated="Junho 2026" testid="page-confidentialite">
    <p>
      O {EDITOR} atribui grande importância à proteção dos teus dados pessoais,
      em conformidade com o Regulamento Geral sobre a Proteção de Dados (RGPD) e a lei
      portuguesa da proteção de dados (Lei n.º 58/2019).
    </p>

    <h2>1. Responsável pelo tratamento</h2>
    <p>{EDITOR} — contacto: <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.</p>

    <h2>2. Dados recolhidos</h2>
    <p>
      Recolhemos: identidade e contactos (nome, email), dados de conta e
      autenticação, conteúdos criados (orçamentos, obras, fotos, documentos),
      informações da empresa (NIPC, NIF, logótipo) e dados técnicos (logs, dispositivo).
    </p>

    <h2>3. Finalidades</h2>
    <p>
      Fornecimento do serviço (estimativa, orçamentos, faturas, obras), gestão da conta e da
      subscrição, faturação, suporte, melhoria do serviço e segurança. Os pagamentos são
      processados pela Stripe; os emails pelo nosso prestador de envio.
    </p>

    <h2>4. Base legal e prazo</h2>
    <p>
      Execução do contrato, obrigações legais (faturação) e interesse legítimo. Os dados
      são conservados durante a relação contratual e depois arquivados de acordo com os
      prazos legais aplicáveis.
    </p>

    <h2>5. Partilha</h2>
    <p>
      Os teus dados nunca são vendidos. Podem ser transmitidos aos nossos subcontratantes
      técnicos (alojamento, pagamento Stripe, envio de emails) exclusivamente para o
      funcionamento do serviço.
    </p>

    <h2>6. Os teus direitos</h2>
    <p>
      Tens o direito de acesso, retificação, eliminação, portabilidade,
      limitação e oposição. Exerce-os em{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Podes apresentar reclamação à CNPD em caso de
      litígio (www.cnpd.pt).
    </p>

    <h2>7. Cookies</h2>
    <p>
      Utilizamos cookies estritamente necessários ao funcionamento (sessão,
      autenticação) e, quando aplicável, cookies de medição de audiência. Podes gerir as tuas
      preferências a partir do teu browser.
    </p>
  </LegalLayout>
);

export const CGV = () => (
  <LegalLayout title="Termos gerais de utilização e venda" updated="Junho 2026" testid="page-cgv">
    <h2>1. Objeto</h2>
    <p>
      Os presentes termos regem o acesso e a utilização da aplicação {EDITOR}, bem como
      as subscrições pagas propostas.
    </p>

    <h2>2. Conta</h2>
    <p>
      O utilizador compromete-se a fornecer informações exatas e a preservar a confidencialidade
      das suas credenciais. Cada conta é pessoal.
    </p>

    <h2>3. Subscrições e preços</h2>
    <p>
      O {EDITOR} disponibiliza funcionalidades gratuitas e subscrições pagas (Particular e
      Profissional). Os preços são indicados em euros, com IVA quando aplicável. O pagamento é feito
      por cartão via Stripe. A subscrição é renovada automaticamente e cancelável a qualquer momento;
      o cancelamento produz efeitos no fim do período em curso.
    </p>

    <h2>4. Direito de livre resolução</h2>
    <p>
      Para consumidores, aplica-se o direito de livre resolução de 14 dias, salvo renúncia
      expressa em caso de acesso imediato ao serviço digital. Contacto:{" "}
      <a href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
    </p>

    <h2>5. Disponibilidade e limitação de responsabilidade</h2>
    <p>
      O {EDITOR} envida todos os esforços para garantir a disponibilidade do serviço, sem poder assegurar
      um funcionamento ininterrupto. As estimativas e orçamentos têm caráter indicativo.
    </p>

    <h2>6. Dados pessoais</h2>
    <p>
      O tratamento de dados encontra-se descrito na nossa{" "}
      <Link to="/confidentialite">Política de privacidade</Link>.
    </p>

    <h2>7. Direito aplicável</h2>
    <p>
      Os presentes termos estão sujeitos ao direito português. Em caso de litígio, será procurada
      uma solução amigável antes de qualquer ação judicial.
    </p>
  </LegalLayout>
);
