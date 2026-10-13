import { useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { LifeBuoy, Bot, KeyRound, Mail, MessageCircle, ChevronDown, Send, FileText, Smartphone, Mic, ShieldCheck, Euro, Ruler } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { SEO } from "@/components/SEO";

const FAQ = [
  { icon: FileText, q: "Como criar um orçamento rapidamente?", a: "A partir de «Criar um orçamento» ou do Assistente Construção: descreva os trabalhos (ou dite-os), a IA propõe linhas orçamentadas que valida. Cada preço indica a sua proveniência (biblioteca, o seu catálogo, introdução manual). O orçamento converte-se em fatura num clique; um orçamento assinado fica bloqueado e qualquer alteração cria uma revisão." },
  { icon: Euro, q: "As minhas faturas cumprem a faturação eletrónica?", a: "Sim: as faturas são emitidas em formato estruturado (EN 16931) com validação automática. Indique NIF, IVA e morada em A minha conta → Identidade profissional para que o controlo seja aprovado." },
  { icon: Ruler, q: "Posso importar uma planta DWG, Revit ou PDF?", a: "Sim, no «Editor de plantas» (PDF/imagens, medição rastreável) e na «Análise de plantas Pro» (DWG, RVT, IFC via Autodesk: quantidades por elemento, exportação Excel). Cada quantidade conserva a sua fonte; em caso de desacordo entre leituras IA, o resultado é marcado «a verificar», nunca inventado." },
  { icon: KeyRound, q: "Como acede o meu cliente ou o meu subempreiteiro ao seu espaço?", a: "A partir da ficha da obra → Partilha e convidados → Convidar. O convidado recebe uma ligação (14 dias) e depois inicia sessão em /espace com o identificador da obra (CP-XXXX-XXXX) e um código recebido por e-mail. Só vê esta obra e apenas o que publicar: avanço, fotografias, mensagens, comunicação de problemas." },
  { icon: Mic, q: "O ditado por voz não funciona", a: "Autorize o microfone no seu navegador (ícone do cadeado → Microfone). O ditado está disponível nas notas de orçamento, nos relatórios, nas reservas e nas mensagens do portal. No iPhone, utilize o Safari ou a aplicação ConstruPilot." },
  { icon: Smartphone, q: "Existem aplicações móveis?", a: "Sim: ConstruPilot Obra (profissionais), ConstruPilot Colaborador (equipas: registo de horas, relatórios) e ConstruPilot Particulares, em Android e iPhone. O site também pode ser instalado no ecrã inicial com notificações." },
  { icon: Euro, q: "Quais são os preços e como cancelar?", a: "Particulares: gratuito. Profissionais: Premium 19 €, Pro 149 €, Pro Business 249 € s/ IVA/mês, sem fidelização. Gestão e cancelamento num clique em Preços e subscrição → portal de faturação." },
  { icon: ShieldCheck, q: "Onde estão os meus dados e como os exportar?", a: "Dados alojados na Europa, documentos bloqueados com carimbo temporal (hash SHA-256), fotografias e ficheiros em armazenamento de objetos cifrado. Exportação dos seus documentos em PDF/Excel a partir de cada módulo; pedido de exportação completa ou de eliminação através do formulário abaixo." },
  { icon: KeyRound, q: "Palavra-passe esquecida ou código não recebido", a: "Utilize «Palavra-passe esquecida» na página de início de sessão. Para os códigos (2FA, espaço do convidado), verifique o spam: o remetente é construpilot.pt. O código é válido durante 10 minutos." },
];

function FaqItem({ item, open, onToggle, i }) {
  const I = item.icon;
  return (
    <div className="border-b border-border last:border-0">
      <button type="button" onClick={onToggle} aria-expanded={open} className="w-full flex items-center gap-3 py-4 text-left" data-testid={`faq-q-${i}`}>
        <span className="h-8 w-8 rounded-sm bg-primary/10 text-primary grid place-items-center shrink-0"><I className="h-4 w-4" /></span>
        <span className="font-semibold text-sm flex-1">{item.q}</span>
        <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && <p className="text-sm text-muted-foreground pb-4 ps-11 leading-relaxed" data-testid={`faq-a-${i}`}>{item.a}</p>}
    </div>
  );
}

function ContactForm() {
  const { user } = useAuth();
  const [form, setForm] = useState({ name: user?.name || "", email: user?.email || "", subject: "", message: "", website: "" });
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(null);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async (e) => {
    e.preventDefault(); setBusy(true);
    try { const { data } = await api.post("/help/contact", form); setDone(data); }
    catch (err) { toast.error(err?.response?.status === 429 ? "Demasiados pedidos: tente novamente dentro de uma hora." : err?.response?.data?.detail?.[0]?.msg || err?.response?.data?.detail || "Envio impossível"); }
    finally { setBusy(false); }
  };
  if (done) return (
    <div className="surface p-6 grid gap-2" data-testid="help-contact-done">
      <p className="font-display font-bold">Pedido registado — referência <span className="font-mono text-primary" data-testid="help-ticket-id">{done.ticket_id}</span></p>
      <p className="text-sm text-muted-foreground">{done.email_status === "sent" ? "Foi-lhe enviado um aviso de receção por e-mail. Resposta em 1 dia útil." : "O seu pedido foi registado, mas não foi possível enviar o e-mail de confirmação: responder-lhe-emos diretamente para o endereço indicado."}</p>
    </div>
  );
  return (
    <form onSubmit={submit} className="surface p-6 grid gap-3" data-testid="help-contact-form">
      <div className="grid sm:grid-cols-2 gap-3">
        <Input required minLength={2} value={form.name} onChange={set("name")} placeholder="O seu nome *" data-testid="help-name" />
        <Input required type="email" value={form.email} onChange={set("email")} placeholder="O seu e-mail *" data-testid="help-email" />
      </div>
      <Input required minLength={3} value={form.subject} onChange={set("subject")} placeholder="Assunto * (ex.: Fatura eletrónica recusada)" data-testid="help-subject" />
      <Textarea required minLength={10} rows={5} value={form.message} onChange={set("message")} placeholder="Descreva a sua pergunta ou o problema encontrado (página, mensagem de erro, o que esperava)…" className="resize-none" data-testid="help-message" />
      <input type="text" value={form.website} onChange={set("website")} className="hidden" tabIndex={-1} autoComplete="off" aria-hidden="true" />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">Resposta por e-mail em 1 dia útil · <a href="mailto:info@construpilot.pt" className="text-primary hover:underline">info@construpilot.pt</a></p>
        <Button type="submit" disabled={busy} className="gap-2" data-testid="help-submit"><Send className="h-4 w-4" /> {busy ? "A enviar…" : "Enviar o meu pedido"}</Button>
      </div>
    </form>
  );
}

export default function Help() {
  const { user } = useAuth();
  const [open, setOpen] = useState(0);
  const openChat = () => window.dispatchEvent(new CustomEvent("cp:open-help"));
  const links = [
    { icon: MessageCircle, title: "Assistente online", desc: "Resposta imediata às perguntas sobre a utilização do ConstruPilot.", action: <Button size="sm" onClick={openChat} data-testid="help-open-chat">Abrir o chat</Button> },
    { icon: Bot, title: "Assistente Construção (IA especializada)", desc: "Orçamentos, regulamentação, leitura de plantas, processo de obra — para profissionais com sessão iniciada.", action: <Button size="sm" variant="outline" asChild data-testid="help-open-assistant"><Link to={user ? "/assistant" : "/login?next=/assistant"}>/assistant</Link></Button> },
    { icon: KeyRound, title: "Espaço do cliente e subempreiteiro", desc: "Foi convidado para uma obra? Inicie sessão com o identificador recebido.", action: <Button size="sm" variant="outline" asChild data-testid="help-open-portal"><Link to="/espace">/espace</Link></Button> },
    { icon: Mail, title: "E-mail", desc: "Para qualquer questão comercial, de faturação ou de dados pessoais.", action: <Button size="sm" variant="outline" asChild data-testid="help-mailto"><a href="mailto:info@construpilot.pt">info@construpilot.pt</a></Button> },
  ];
  return (
    <div className="grid gap-10 max-w-5xl" data-testid="help-page">
      <SEO title="Ajuda e assistência ConstruPilot" description="Centro de ajuda ConstruPilot: perguntas frequentes, assistente online, espaço do cliente e formulário de contacto com resposta em 1 dia útil." path="/aide" />
      <header className="grid gap-3">
        <p className="text-xs uppercase tracking-[0.2em] text-primary font-semibold flex items-center gap-2"><LifeBuoy className="h-4 w-4" /> Assistência</p>
        <h1 className="font-display text-4xl sm:text-5xl font-bold tracking-tight">Como podemos ajudar?</h1>
        <p className="text-base text-muted-foreground max-w-2xl">Um assistente online para as perguntas imediatas, uma FAQ para o essencial e uma equipa que responde por e-mail em 1 dia útil.</p>
      </header>

      <section className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid="help-links">
        {links.map((l) => <div key={l.title} className="surface p-5 grid gap-3 content-start"><span className="h-10 w-10 rounded-sm bg-primary/10 text-primary grid place-items-center"><l.icon className="h-5 w-5" /></span><p className="font-display font-bold">{l.title}</p><p className="text-sm text-muted-foreground flex-1">{l.desc}</p>{l.action}</div>)}
      </section>

      <div className="grid lg:grid-cols-[1.2fr_1fr] gap-8 items-start">
        <section className="surface px-6 py-2" data-testid="help-faq">
          <h2 className="font-display text-lg font-bold pt-4 pb-1">Perguntas frequentes</h2>
          {FAQ.map((it, i) => <FaqItem key={it.q} item={it} i={i} open={open === i} onToggle={() => setOpen(open === i ? null : i)} />)}
        </section>
        <section className="grid gap-3" data-testid="help-contact">
          <h2 className="font-display text-lg font-bold">Escrever à assistência</h2>
          <ContactForm />
        </section>
      </div>
    </div>
  );
}
