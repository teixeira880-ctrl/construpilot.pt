import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowLeft, Trash2, ShieldCheck, Mail, Loader2, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toast } from "sonner";

const APPS = ["ConstruPilot Obra", "ConstruPilot Colaborador", "ConstruPilot Particulares"];
const CONTACT_EMAIL = "info@construpilot.pt";
const UPDATED = { fr: "Juin 2026", en: "June 2026" };

const T = {
  fr: {
    over: "Aplicações móveis e web",
    title: "Eliminar a minha conta ConstruPilot",
    updated: (d) => `Última atualização: ${d}`,
    banner: "Eliminação definitiva · Nenhum dado vendido · Alojamento na UE",
    intro: `Esta página explica como pedir a eliminação da sua conta e dos seus dados nas aplicações ${APPS.join(", ")} e no serviço web ConstruPilot (editor: ConstruPilot).`,
    s1: "1. Eliminar a sua conta a partir da aplicação",
    s1b: [
      "Inicie sessão na sua conta (aplicação móvel ou site).",
      "Abra «A minha conta» (menu de perfil) → secção «Eliminar a minha conta».",
      "Introduza a sua palavra-passe e escreva ELIMINAR para confirmar.",
      "A eliminação é imediata e definitiva: nenhum período de espera, nenhum contacto comercial.",
    ],
    s1link: "Abrir a página A minha conta",
    s2: "2. Já não tem acesso à sua conta?",
    s2p: "Envie-nos um pedido com o endereço de e-mail da conta em causa. Verificamos a sua identidade e depois eliminamos a conta no prazo máximo de 30 dias (geralmente em 72 h úteis). Recebe uma confirmação por e-mail.",
    s3: "3. Dados eliminados",
    s3b: [
      "Conta e perfil: nome, e-mail, telefone, palavra-passe, fotografia, preferências, sessões e dispositivos.",
      "Conteúdos profissionais: obras, orçamentos, plantas, medições, fotografias de obra, documentos importados, mensagens e conversas.",
      "Contactos: clientes, subempreiteiros, fornecedores e colaboradores convidados por si.",
      "Histórico de utilização: notificações, pesquisas, registos de atividade, créditos e estatísticas ligados à conta.",
    ],
    s4: "4. Dados conservados (obrigações legais)",
    s4b: [
      "Faturas emitidas e documentos contabilísticos: conservados 10 anos (artigo 52.º do Código do IVA) fora do seu espaço, sem acesso para marketing.",
      "Comprovativos de faturação da subscrição conservados pelo nosso prestador de pagamentos (Stripe) de acordo com as suas obrigações legais.",
      "Registos técnicos de segurança anonimizados: 12 meses no máximo.",
      "Cópias de segurança cifradas: purgadas por rotação em 30 dias.",
    ],
    s5: "5. Consequências da eliminação",
    s5p: "A eliminação põe termo à sua subscrição em curso e não dá direito a reembolso dos períodos já pagos. Os seus colaboradores e clientes perdem o acesso aos espaços partilhados que tinha criado. A operação é irreversível: exporte os seus orçamentos, faturas e documentos antes de confirmar.",
    s6: "6. Contacte-nos",
    s6p: "Para qualquer questão relativa aos seus dados pessoais (acesso, retificação, portabilidade, eliminação):",
    form: "Pedido de eliminação de conta",
    fname: "Nome e apelido",
    femail: "E-mail da conta a eliminar",
    fmsg: "Precisões (opcional)",
    fmsgph: "Ex.: nome da empresa, último acesso, aplicação utilizada…",
    send: "Enviar o meu pedido de eliminação",
    sent: "Pedido enviado. Recebe um aviso de receção por e-mail; a eliminação é tratada no prazo máximo de 30 dias.",
    err: "Envio impossível. Escreva-nos diretamente para " + CONTACT_EMAIL,
    required: "Indique o seu nome e o e-mail da conta.",
    dataTitle: "Pedir a eliminação dos meus dados",
    dataIntro: `Esta página permite a qualquer utilizador das aplicações ${APPS.join(", ")} e do serviço web ConstruPilot pedir a eliminação dos seus dados pessoais, com ou sem eliminação da conta.`,
    dataChoice: "O que pretende eliminar?",
    dataOptA: "Toda a minha conta e todos os meus dados",
    dataOptB: "Apenas alguns dados (fotografias, obra, contactos, histórico…) mantendo a minha conta",
    dataWhich: "Dados a eliminar",
    dataWhichPh: "Ex.: fotografias da obra «Moradia Silva», os meus contactos de clientes, o histórico do assistente IA…",
    dataForm: "Pedido de eliminação de dados",
    dataSend: "Enviar o meu pedido de eliminação de dados",
    dataDelay: "Respondemos no prazo máximo de 30 dias (geralmente 72 h úteis), em conformidade com o RGPD (artigo 17.º — direito ao apagamento).",
    dataLink: "Pretende apenas eliminar alguns dados, sem fechar a sua conta?",
    accountLink: "Pretende eliminar toda a sua conta?",
  },
  en: {
    over: "Mobile & web apps",
    title: "Delete my ConstruPilot account",
    updated: (d) => `Last updated: ${d}`,
    banner: "Permanent deletion · No data sold · EU hosting",
    intro: `This page explains how to request the deletion of your account and data for the ${APPS.join(", ")} apps and the ConstruPilot web service (publisher: ConstruPilot).`,
    s1: "1. Delete your account from the app",
    s1b: [
      "Sign in to your account (mobile app or website).",
      "Open “My account” (profile menu) → “Delete my account” section.",
      "Enter your password then type SUPPRIMER to confirm.",
      "Deletion is immediate and permanent: no waiting period, no marketing follow-up.",
    ],
    s1link: "Open My account",
    s2: "2. Can't access your account anymore?",
    s2p: "Send us a request using the e-mail address of the account. We verify your identity and delete the account within 30 days at most (usually within 72 business hours). You receive an e-mail confirmation.",
    s3: "3. Data that is deleted",
    s3b: [
      "Account and profile: name, e-mail, phone, password, picture, preferences, sessions and devices.",
      "Professional content: projects, quotes, plans, take-offs, site photos, uploaded documents, messages and threads.",
      "Contacts: clients, subcontractors, suppliers and team members you invited.",
      "Usage history: notifications, searches, activity logs, credits and account statistics.",
    ],
    s4: "4. Data we must keep (legal obligations)",
    s4b: [
      "Issued invoices and accounting records: kept for 10 years (French Commercial Code, art. L.123-22), outside your workspace and never used for marketing.",
      "Subscription billing records kept by our payment provider (Stripe) under its own legal obligations.",
      "Anonymised technical security logs: 12 months maximum.",
      "Encrypted backups: purged by rotation within 30 days.",
    ],
    s5: "5. Consequences of deletion",
    s5p: "Deletion ends your current subscription and does not entitle you to a refund for periods already paid. Your team members and clients lose access to the shared spaces you created. The operation is irreversible: export your quotes, invoices and documents before confirming.",
    s6: "6. Contact us",
    s6p: "For any question about your personal data (access, rectification, portability, deletion):",
    form: "Account deletion request",
    fname: "Full name",
    femail: "E-mail of the account to delete",
    fmsg: "Details (optional)",
    fmsgph: "E.g. company name, last sign-in, app used…",
    send: "Send my deletion request",
    sent: "Request sent. You will receive an acknowledgement by e-mail; deletion is processed within 30 days at most.",
    err: "Sending failed. Please e-mail us directly at " + CONTACT_EMAIL,
    required: "Please provide your name and the account e-mail.",
    dataTitle: "Request deletion of my data",
    dataIntro: `This page lets any user of the ${APPS.join(", ")} apps and the ConstruPilot web service request the deletion of their personal data, with or without deleting the account.`,
    dataChoice: "What do you want deleted?",
    dataOptA: "My whole account and all my data",
    dataOptB: "Only some data (photos, a project, contacts, history…) while keeping my account",
    dataWhich: "Data to delete",
    dataWhichPh: "E.g. photos of the “Villa Dupont” project, my client contacts, the AI assistant history…",
    dataForm: "Data deletion request",
    dataSend: "Send my data deletion request",
    dataDelay: "We answer within 30 days at most (usually 72 business hours), in line with the GDPR (article 17 — right to erasure).",
    dataLink: "Only want some data removed, without closing your account?",
    accountLink: "Want to delete your whole account?",
  },
};

const Section = ({ title, children }) => (
  <section className="mt-8">
    <h2 className="font-display text-xl font-bold text-foreground mb-2">{title}</h2>
    <div className="space-y-3 text-[15px] leading-relaxed text-foreground/90">{children}</div>
  </section>
);

const Bullets = ({ items }) => (
  <ul className="space-y-1.5 pl-1">
    {items.map((it, i) => (
      <li key={i} className="flex gap-2">
        <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
        <span>{it}</span>
      </li>
    ))}
  </ul>
);

export default function DeleteAccountPage() {
  const { pathname } = useLocation();
  const dataMode = /donnees|data-deletion/.test(pathname);
  const [lang, setLang] = useState("fr");
  const [form, setForm] = useState({ name: "", email: "", message: "", which: "", website: "" });
  const [scope, setScope] = useState(dataMode ? "partial" : "account");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const t = T[lang];

  useEffect(() => {
    document.documentElement.lang = lang;
    const titles = {
      fr: dataMode ? "Eliminar os meus dados — ConstruPilot" : "Eliminar a minha conta — ConstruPilot",
      en: dataMode ? "Delete my data — ConstruPilot" : "Delete my account — ConstruPilot",
    };
    document.title = titles[lang];
  }, [lang, dataMode]);

  const submit = async (e) => {
    e.preventDefault();
    if (form.name.trim().length < 2 || !form.email.includes("@")) { toast.error(t.required); return; }
    const partial = scope === "partial";
    setBusy(true);
    try {
      await api.post("/help/contact", {
        name: form.name.trim(),
        email: form.email.trim(),
        subject: partial ? "Pedido de eliminação de dados (RGPD)"
                         : "Pedido de eliminação de conta (RGPD)",
        message: (partial
          ? `Pedido de eliminação de dados para a conta ${form.email.trim()} (conta mantida).\nDados visados: ${form.which.trim() || "non précisé"}.`
          : `Pedido de eliminação definitiva da conta ${form.email.trim()}.`)
          + `\n\n${form.message.trim() || "Sem precisões."}`,
        website: form.website,
      });
      setDone(true);
      toast.success(t.sent);
    } catch {
      toast.error(t.err);
    } finally { setBusy(false); }
  };

  return (
    <div className="max-w-3xl mx-auto px-6 py-14" data-testid="page-delete-account">
      <Link to="/" className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-primary transition-colors mb-6" data-testid="delete-account-back-link">
        <ArrowLeft className="h-4 w-4" /> {lang === "fr" ? "Voltar ao início" : "Back to home"}
      </Link>

      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <div className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-primary">
            <Trash2 className="h-3.5 w-3.5" /> {t.over}
          </div>
          <h1 className="font-display text-3xl sm:text-4xl font-bold text-foreground mt-2">{dataMode ? t.dataTitle : t.title}</h1>
          <p className="text-xs text-muted-foreground mt-2">{t.updated(UPDATED[lang])}</p>
        </div>
        <div className="flex rounded-full border border-border overflow-hidden text-sm">
          <button type="button" onClick={() => setLang("fr")} data-testid="delete-account-lang-fr"
            className={`px-4 py-1.5 transition-colors ${lang === "fr" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>Português</button>
          <button type="button" onClick={() => setLang("en")} data-testid="delete-account-lang-en"
            className={`px-4 py-1.5 transition-colors ${lang === "en" ? "bg-primary text-primary-foreground" : "hover:bg-muted"}`}>English</button>
        </div>
      </div>

      <div className="mt-6 flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-4 py-3 text-sm text-muted-foreground">
        <ShieldCheck className="h-4 w-4 text-primary shrink-0" /> {t.banner}
      </div>

      <p className="mt-6 text-[15px] leading-relaxed text-foreground/90" data-testid="delete-account-intro">{dataMode ? t.dataIntro : t.intro}</p>

      <Section title={t.s1}>
        <Bullets items={t.s1b} />
        <Button asChild variant="outline" className="rounded-sm gap-2 mt-1" data-testid="delete-account-app-link">
          <Link to="/compte">{t.s1link}</Link>
        </Button>
      </Section>

      <Section title={dataMode ? t.dataForm : t.s2}>
        <p id="demande">{dataMode ? t.dataDelay : t.s2p}</p>
        {done ? (
          <div className="rounded-lg border border-primary/30 bg-primary/5 p-4 flex gap-3 text-sm" data-testid="delete-account-form-done">
            <CheckCircle2 className="h-5 w-5 text-primary shrink-0" />
            <span>{t.sent}</span>
          </div>
        ) : (
          <form onSubmit={submit} className="surface rounded-md p-4 space-y-3" data-testid="delete-account-form">
            <p className="overline">{dataMode ? t.dataForm : t.form}</p>
            <input type="text" tabIndex={-1} autoComplete="off" className="hidden" value={form.website}
              onChange={(e) => setForm({ ...form, website: e.target.value })} />
            <fieldset className="grid gap-2 text-sm" data-testid="delete-account-scope">
              <legend className="text-xs text-muted-foreground mb-1">{t.dataChoice}</legend>
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="radio" name="scope" value="account" checked={scope === "account"}
                  onChange={() => setScope("account")} className="mt-1 accent-primary" data-testid="scope-account" />
                <span>{t.dataOptA}</span>
              </label>
              <label className="flex items-start gap-2 cursor-pointer">
                <input type="radio" name="scope" value="partial" checked={scope === "partial"}
                  onChange={() => setScope("partial")} className="mt-1 accent-primary" data-testid="scope-partial" />
                <span>{t.dataOptB}</span>
              </label>
            </fieldset>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="grid gap-1.5 text-xs text-muted-foreground">{t.fname}
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="rounded-sm h-10" required data-testid="delete-account-name" />
              </label>
              <label className="grid gap-1.5 text-xs text-muted-foreground">{t.femail}
                <Input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="rounded-sm h-10" required data-testid="delete-account-email" />
              </label>
            </div>
            {scope === "partial" && (
              <label className="grid gap-1.5 text-xs text-muted-foreground">{t.dataWhich}
                <Textarea value={form.which} onChange={(e) => setForm({ ...form, which: e.target.value })}
                  placeholder={t.dataWhichPh} rows={2} className="rounded-sm" data-testid="delete-account-which" />
              </label>
            )}
            <label className="grid gap-1.5 text-xs text-muted-foreground">{t.fmsg}
              <Textarea value={form.message} onChange={(e) => setForm({ ...form, message: e.target.value })}
                placeholder={t.fmsgph} rows={3} className="rounded-sm" data-testid="delete-account-message" />
            </label>
            <Button type="submit" className="rounded-sm gap-2" disabled={busy} data-testid="delete-account-submit">
              {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
              {scope === "partial" ? t.dataSend : t.send}
            </Button>
            <p className="text-[11px] text-muted-foreground">{dataMode ? "" : t.dataDelay}</p>
          </form>
        )}
        <p className="text-sm text-muted-foreground">
          {dataMode ? t.accountLink : t.dataLink}{" "}
          <Link className="text-primary underline"
            to={dataMode ? (lang === "fr" ? "/eliminar-conta" : "/delete-account")
                         : (lang === "fr" ? "/eliminar-dados" : "/data-deletion")}
            data-testid="delete-account-cross-link">
            {dataMode
              ? (lang === "fr" ? "construpilot.pt/suppression-compte" : "construpilot.pt/delete-account")
              : (lang === "fr" ? "construpilot.pt/suppression-donnees" : "construpilot.pt/data-deletion")}
          </Link>
        </p>
      </Section>

      <Section title={t.s3}><Bullets items={t.s3b} /></Section>
      <Section title={t.s4}><Bullets items={t.s4b} /></Section>
      <Section title={t.s5}><p>{t.s5p}</p></Section>
      <Section title={t.s6}>
        <p>
          {t.s6p}{" "}
          <a className="text-primary underline" href={`mailto:${CONTACT_EMAIL}`} data-testid="delete-account-mailto">{CONTACT_EMAIL}</a>
          {" · "}
          <Link className="text-primary underline" to="/privacy">{lang === "fr" ? "Política de privacidade" : "Privacy Policy"}</Link>
          {" · "}
          <Link className="text-primary underline" to="/aide">{lang === "fr" ? "Assistência" : "Support"}</Link>
        </p>
      </Section>
    </div>
  );
}
