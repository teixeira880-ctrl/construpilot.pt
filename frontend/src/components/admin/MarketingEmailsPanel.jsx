import { useState } from "react";
import { api, API } from "@/lib/api";
import { Loader2, Eye, Send, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { toast } from "sonner";

const EMAILS = [
  {
    key: "welcome",
    title: "Boas-vindas (novos inscritos)",
    desc: "Enviado automaticamente D+1 após a inscrição. Apresentação do produto + experiência gratuita.",
    previewUrl: () => `${API}/admin/welcome-email/preview`,
    sendPath: "/admin/welcome-email/test",
    sendBody: (to) => ({ to }),
  },
  {
    key: "prospect-particulier",
    title: "Potencial cliente — Particular",
    desc: "Para os leads que pediram uma estimativa. Ângulo: estimativa, preços justos, encontrar um profissional.",
    previewUrl: () => `${API}/admin/prospect-email/preview?audience=particulier`,
    sendPath: "/admin/prospect-email/test",
    sendBody: (to) => ({ to, audience: "particulier" }),
  },
  {
    key: "prospect-pro",
    title: "Potencial cliente — Profissional",
    desc: "Para profissionais / gabinetes de projeto não clientes. Ângulo: medições, orçamentos determinísticos, StructuroPilot, faturação eletrónica.",
    previewUrl: () => `${API}/admin/prospect-email/preview?audience=pro`,
    sendPath: "/admin/prospect-email/test",
    sendBody: (to) => ({ to, audience: "pro" }),
  },
];

const parseEmails = (raw) =>
  (raw || "")
    .split(/[,;\s]+/)
    .map((e) => e.trim().toLowerCase())
    .filter((e) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(e));

function EmailCard({ cfg }) {
  const [to, setTo] = useState("");
  const [busy, setBusy] = useState(false);
  const valid = parseEmails(to);
  const count = new Set(valid).size;

  const send = async () => {
    if (count === 0) {
      toast.error("Introduza pelo menos um endereço de e-mail válido");
      return;
    }
    if (!window.confirm(`Enviar « ${cfg.title} » para ${count} destinatário(s) agora?`)) return;
    setBusy(true);
    try {
      const { data } = await api.post(cfg.sendPath, cfg.sendBody(to));
      toast.success(`${data.sent} enviado(s)${data.failed ? ` · ${data.failed} falha(s)` : ""} de ${data.recipients}`);
      setTo("");
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Envio impossível");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="surface rounded-md p-4 space-y-3" data-testid={`admin-marketing-email-${cfg.key}`}>
      <div>
        <p className="font-semibold">{cfg.title}</p>
        <p className="text-xs text-muted-foreground mt-0.5">{cfg.desc}</p>
      </div>
      <Textarea
        placeholder="Vários endereços — separados por vírgula, ponto e vírgula ou mudança de linha&#10;ex.: joao@exemplo.pt, maria@exemplo.pt"
        value={to}
        onChange={(e) => setTo(e.target.value)}
        rows={2}
        className="rounded-sm text-sm resize-y"
        data-testid={`admin-marketing-recipients-${cfg.key}`}
      />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-muted-foreground" data-testid={`admin-marketing-count-${cfg.key}`}>
          {count > 0 ? `${count} destinatário(s) válido(s)` : "Nenhum endereço válido"}
        </span>
        <div className="flex items-center gap-2">
          <Button
            variant="outline" size="sm" className="rounded-sm gap-2"
            onClick={() => window.open(cfg.previewUrl(), "_blank", "noopener")}
            data-testid={`admin-marketing-preview-${cfg.key}`}
          >
            <Eye className="h-4 w-4" /> Pré-visualização
          </Button>
          <Button
            variant="default" size="sm" className="rounded-sm gap-2"
            onClick={send} disabled={busy || count === 0}
            data-testid={`admin-marketing-send-${cfg.key}`}
          >
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Enviar
          </Button>
        </div>
      </div>
    </div>
  );
}

export default function MarketingEmailsPanel() {
  return (
    <div className="surface rounded-md p-5 space-y-3" data-testid="admin-marketing-emails-panel">
      <div className="flex items-start gap-2">
        <Mail className="h-5 w-5 text-primary mt-0.5" />
        <div>
          <h3 className="font-display font-bold text-lg">E-mails publicitários</h3>
          <p className="text-sm text-muted-foreground">
            Modelos prontos a enviar: boas-vindas (auto D+1) e potenciais clientes. Pré-visualize num novo separador, introduza um ou vários endereços e envie diretamente.
          </p>
        </div>
      </div>
      <div className="grid gap-3">
        {EMAILS.map((cfg) => <EmailCard key={cfg.key} cfg={cfg} />)}
      </div>
    </div>
  );
}
