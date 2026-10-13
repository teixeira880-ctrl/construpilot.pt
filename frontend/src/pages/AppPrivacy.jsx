import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ShieldCheck, Smartphone } from "lucide-react";

const CONTACT_EMAIL = "contact@construpilot.fr";
const UPDATED_FR = "Juin 2026";
const UPDATED_EN = "June 2026";

const APPS = [
  "ConstruPilot Obra",
  "ConstruPilot Colaborador",
  "ConstruPilot Particulares",
];

const PERMISSIONS = [
  {
    key: "camera",
    fr: ["Câmara", "Tirar fotografias de obra, digitalizar orçamentos e documentos. As fotografias só são enviadas para os nossos servidores quando as associa a uma obra ou a um documento."],
    en: ["Camera", "Take site photos, scan quotes and documents. Photos are uploaded to our servers only when you attach them to a project or a document."],
  },
  {
    key: "microphone",
    fr: ["Microfone", "Ditado por voz (orçamentos, reservas, mensagens). O excerto áudio é transmitido ao nosso prestador de transcrição (OpenAI Whisper) e depois eliminado; só o texto transcrito é conservado."],
    en: ["Microphone", "Voice dictation (quotes, punch-list items, messages). The audio clip is sent to our transcription provider (OpenAI Whisper) then deleted; only the transcribed text is stored."],
  },
  {
    key: "photos",
    fr: ["Fotografias / Ficheiros", "Importar plantas, PDF e imagens a partir do seu dispositivo. Nenhum acesso em segundo plano à sua galeria."],
    en: ["Photos / Files", "Import plans, PDFs and images from your device. No background access to your gallery."],
  },
  {
    key: "location",
    fr: ["Localização (opcional)", "Apenas se ativar o registo de presença geolocalizado ou a pesquisa de obras próximas. Nunca há seguimento em segundo plano."],
    en: ["Location (optional)", "Only if you enable geo-stamped time tracking or nearby-project search. Never tracked in the background."],
  },
  {
    key: "notifications",
    fr: ["Notificações", "Alertas sobre os seus orçamentos, mensagens de clientes e lembretes de obra. Desativáveis a qualquer momento."],
    en: ["Notifications", "Alerts about your quotes, client messages and project reminders. Can be disabled at any time."],
  },
];

const Section = ({ title, children }) => (
  <section className="mt-8">
    <h2 className="font-display text-xl font-bold text-foreground mb-2">{title}</h2>
    <div className="space-y-3 text-[15px] leading-relaxed text-foreground/90">{children}</div>
  </section>
);

const FrenchPolicy = () => (
  <div data-testid="app-privacy-fr">
    <p>
      A presente política de privacidade aplica-se às aplicações móveis{" "}
      <strong>{APPS.join(", ")}</strong> (iOS e Android), bem como ao serviço web ConstruPilot, editados pela ConstruPilot. É estabelecida em conformidade com o Regulamento Geral sobre a Proteção de Dados (RGPD), a Lei n.º 58/2019 e os requisitos da App Store da Apple e do Google Play.
    </p>

    <Section title="1. Responsável pelo tratamento">
      <p>
        ConstruPilot — contact :{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Qualquer pedido relativo aos seus dados é tratado em 30 dias.
      </p>
    </Section>

    <Section title="2. Dados que recolhemos">
      <ul className="list-disc pl-5 space-y-1">
        <li><strong>Identidade e contacto</strong> : nome, e-mail, telefone (opcional).</li>
        <li><strong>Conta e autenticação</strong> : palavra-passe cifrada, token de sessão.</li>
        <li><strong>Dados profissionais</strong> : denominação social, NIF/NIPC, IVA, logótipo, dados bancários de faturação se indicados.</li>
        <li><strong>Conteúdos que cria</strong> : orçamentos, faturas, obras, fotografias, plantas, notas de voz, mensagens trocadas com os seus clientes.</li>
        <li><strong>Dados técnicos</strong> : tipo de dispositivo, versão da app, registos de erros, endereço IP.</li>
        <li><strong>Pagamento</strong> : tratado exclusivamente pela Stripe. Não guardamos nenhum número de cartão.</li>
      </ul>
      <p>
        Não recolhemos nenhum dado sensível (saúde, origem, opiniões) e não utilizamos nenhum rastreador publicitário de terceiros. Nenhum dado é vendido.
      </p>
    </Section>

    <Section title="3. Autorizações pedidas pela aplicação">
      <div className="space-y-3">
        {PERMISSIONS.map((p) => (
          <div key={p.key} className="rounded-lg border border-border p-3">
            <p className="font-semibold text-foreground">{p.fr[0]}</p>
            <p className="text-sm text-muted-foreground mt-0.5">{p.fr[1]}</p>
          </div>
        ))}
      </div>
      <p className="text-sm">
        Cada autorização é pedida no momento da utilização e pode ser recusada ou revogada nas definições do seu telemóvel, sem bloquear as outras funções da app.
      </p>
    </Section>

    <Section title="4. Finalidades e fundamentos jurídicos">
      <p>
        Execução do contrato (prestação do serviço, gestão da conta e da subscrição), obrigações legais (faturação, contabilidade), interesse legítimo (segurança, prevenção da fraude, melhoria do serviço) e consentimento para as funcionalidades opcionais (localização, notificações).
      </p>
    </Section>

    <Section title="5. Inteligência artificial">
      <p>
        Algumas funções (Assistente Construção, estimativa, transcrição de voz, análise de fotografias) enviam o conteúdo estritamente necessário aos nossos prestadores de IA (OpenAI, Anthropic, Google). Estes conteúdos não são utilizados para treinar os seus modelos. Os resultados produzidos pela IA são indicativos e não constituem um compromisso contratual.
      </p>
    </Section>

    <Section title="6. Subcontratantes">
      <ul className="list-disc pl-5 space-y-1">
        <li>Alojamento e armazenamento de ficheiros: infraestrutura cloud Emergent (UE).</li>
        <li>Pagamento: Stripe.</li>
        <li>IA e transcrição: OpenAI, Anthropic, Google.</li>
        <li>E-mails transacionais: o nosso prestador de envio.</li>
      </ul>
    </Section>

    <Section title="7. Prazo de conservação">
      <p>
        Os dados da conta são conservados durante toda a relação contratual. Após a eliminação da conta, são apagados no prazo de 30 dias, com exceção das peças contabilísticas (faturas), conservadas 10 anos nos termos da lei.
      </p>
    </Section>

    <Section title="8. Eliminação da conta e dos dados">
      <p>
        Pode eliminar a sua conta diretamente na aplicação (A minha conta → Eliminar a minha conta) ou escrevendo para{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}?subject=Suppression%20de%20compte`}>{CONTACT_EMAIL}</a>. A eliminação implica o apagamento das suas obras, documentos, fotografias e mensagens. Procedimento detalhado:{" "}
        <Link className="text-primary underline" to="/suppression-compte" data-testid="privacy-delete-link">construpilot.pt/suppression-compte</Link>.
      </p>
    </Section>

    <Section title="9. Os seus direitos">
      <p>
        Acesso, retificação, apagamento, portabilidade, limitação e oposição. Exerça-os através de{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. Pode apresentar reclamação junto da CNPD (www.cnpd.pt).
      </p>
    </Section>

    <Section title="10. Crianças">
      <p>
        As aplicações ConstruPilot destinam-se a adultos e profissionais. Não se dirigem a crianças com menos de 16 anos e não recolhemos conscientemente os seus dados.
      </p>
    </Section>

    <Section title="11. Segurança">
      <p>
        Cifragem das comunicações (HTTPS/TLS), palavras-passe com hash, cookies de sessão HttpOnly, separação estrita dos dados entre empresas e acessos de convidados limitados apenas aos elementos explicitamente partilhados pelo profissional.
      </p>
    </Section>

    <Section title="12. Alterações">
      <p>
        Qualquer alteração desta política será publicada nesta página com uma nova data de atualização. Para qualquer questão:{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}
        · Assistance : <Link className="text-primary underline" to="/aide">página de ajuda</Link>.
      </p>
    </Section>
  </div>
);

const EnglishPolicy = () => (
  <div data-testid="app-privacy-en">
    <p>
      This privacy policy applies to the mobile applications{" "}
      <strong>{APPS.join(", ")}</strong> (iOS and Android) and to the ConstruPilot web service,
      published by ConstruPilot. It complies with the EU General Data Protection Regulation
      (GDPR) and with Apple App Store and Google Play requirements.
    </p>

    <Section title="1. Data controller">
      <p>
        ConstruPilot — contact:{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>.
        Any request regarding your data is handled within 30 days.
      </p>
    </Section>

    <Section title="2. Data we collect">
      <ul className="list-disc pl-5 space-y-1">
        <li><strong>Identity and contact</strong>: name, email, phone (optional).</li>
        <li><strong>Account and authentication</strong>: hashed password, session token.</li>
        <li><strong>Business data</strong>: company name, registration and VAT numbers, logo, billing details if provided.</li>
        <li><strong>Content you create</strong>: quotes, invoices, projects, photos, plans, voice notes, messages exchanged with your clients.</li>
        <li><strong>Technical data</strong>: device type, app version, crash logs, IP address.</li>
        <li><strong>Payments</strong>: processed exclusively by Stripe. We never store card numbers.</li>
      </ul>
      <p>
        We collect no sensitive data (health, ethnicity, opinions) and use no third-party advertising trackers. Your data is never sold.
      </p>
    </Section>

    <Section title="3. Permissions requested by the app">
      <div className="space-y-3">
        {PERMISSIONS.map((p) => (
          <div key={p.key} className="rounded-lg border border-border p-3">
            <p className="font-semibold text-foreground">{p.en[0]}</p>
            <p className="text-sm text-muted-foreground mt-0.5">{p.en[1]}</p>
          </div>
        ))}
      </div>
      <p className="text-sm">
        Each permission is requested at the time of use and can be denied or revoked in your
        phone settings without blocking other app features.
      </p>
    </Section>

    <Section title="4. Purposes and legal bases">
      <p>
        Performance of the contract (service delivery, account and subscription management), legal obligations (invoicing, accounting), legitimate interest (security, fraud prevention, service improvement) and consent for optional features (location, notifications).
      </p>
    </Section>

    <Section title="5. Artificial intelligence">
      <p>
        Some features (construction assistant, cost estimation, voice transcription, photo
        analysis) send only the necessary content to our AI providers (OpenAI, Anthropic,
        Google). This content is not used to train their models. AI outputs are indicative and
        do not constitute a contractual commitment.
      </p>
    </Section>

    <Section title="6. Processors">
      <ul className="list-disc pl-5 space-y-1">
        <li>Hosting and file storage: Emergent cloud infrastructure (EU).</li>
        <li>Payments: Stripe.</li>
        <li>AI and transcription: OpenAI, Anthropic, Google.</li>
        <li>Transactional emails: our email delivery provider.</li>
      </ul>
    </Section>

    <Section title="7. Retention">
      <p>
        Account data is kept for the duration of the contractual relationship. After account
        deletion it is erased within 30 days, except accounting records (invoices) kept for 10
        years as required by law.
      </p>
    </Section>

    <Section title="8. Account and data deletion">
      <p>
        You can delete your account directly in the app (My account → Delete my account) or by
        writing to{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}?subject=Account%20deletion`}>{CONTACT_EMAIL}</a>. Deletion erases your projects, documents, photos and messages. Full procedure:{" "}
        <Link className="text-primary underline" to="/delete-account" data-testid="privacy-delete-link-en">construpilot.pt/delete-account</Link>.
      </p>
    </Section>

    <Section title="9. Your rights">
      <p>
        Access, rectification, erasure, portability, restriction and objection. Exercise them at{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>. You may lodge a complaint with the Portuguese data protection authority (CNPD, www.cnpd.pt).
      </p>
    </Section>

    <Section title="10. Children">
      <p>
        ConstruPilot apps are intended for adults and professionals. They are not directed at
        children under 16 and we do not knowingly collect their data.
      </p>
    </Section>

    <Section title="11. Security">
      <p>
        Encrypted transport (HTTPS/TLS), hashed passwords, HttpOnly session cookies, strict data
        isolation between companies, and guest access limited to what the professional
        explicitly shares.
      </p>
    </Section>

    <Section title="12. Changes">
      <p>
        Any change to this policy will be published on this page with a new update date. Questions:{" "}
        <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`}>{CONTACT_EMAIL}</a>{" "}
        · Support: <Link className="text-primary underline" to="/aide">help page</Link>.
      </p>
    </Section>
  </div>
);

export default function AppPrivacy() {
  const [lang, setLang] = useState("fr");
  useEffect(() => { document.documentElement.lang = lang === "en" ? "en" : "pt-PT"; }, [lang]);

  return (
    <div className="max-w-3xl mx-auto px-6 py-14" data-testid="page-app-privacy">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-6"
        data-testid="app-privacy-back-link"
      >
        <ArrowLeft className="h-4 w-4" /> {lang === "fr" ? "Voltar ao início" : "Back to home"}
      </Link>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <Smartphone className="h-3.5 w-3.5" />
            {lang === "fr" ? "Aplicações móveis e web" : "Mobile & web apps"}
          </div>
          <h1 className="font-display text-3xl sm:text-4xl font-bold text-foreground mt-2">
            {lang === "fr" ? "Política de privacidade" : "Privacy Policy"}
          </h1>
          <p className="text-xs text-muted-foreground mt-2">
            {lang === "fr"
              ? `Última atualização: ${UPDATED_FR}`
              : `Last updated: ${UPDATED_EN}`}
          </p>
        </div>

        <div className="flex rounded-full border border-border overflow-hidden text-sm">
          <button
            type="button"
            onClick={() => setLang("fr")}
            data-testid="app-privacy-lang-fr"
            className={`px-4 py-1.5 transition-colors ${lang === "fr" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >
            Português
          </button>
          <button
            type="button"
            onClick={() => setLang("en")}
            data-testid="app-privacy-lang-en"
            className={`px-4 py-1.5 transition-colors ${lang === "en" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}
          >
            English
          </button>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        <ShieldCheck className="h-4 w-4 text-primary shrink-0" />
        {lang === "fr"
          ? "Nenhum dado vendido · Nenhum rastreador publicitário · Alojamento na UE"
          : "No data sold · No ad trackers · EU hosting"}
      </div>

      {lang === "fr" ? <FrenchPolicy /> : <EnglishPolicy />}
    </div>
  );
}
