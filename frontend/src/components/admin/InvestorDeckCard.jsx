import { useState } from "react";
import { Presentation, Download, Loader2, FileText } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";

const LANGS = [
  { code: "fr", label: "Português" },
  { code: "en", label: "English" },
  { code: "pt", label: "Português" },
];

// Présentations client et investisseur : KPI réels lus en base au moment du téléchargement.
export default function InvestorDeckCard() {
  const [busy, setBusy] = useState("");
  const [prospect, setProspect] = useState("");

  const get = async (kind, ext, lang) => {
    const key = `${kind}-${ext}-${lang}`;
    setBusy(key);
    try {
      const path = kind === "investor" ? "investisseurs" : "plaquette";
      const name = kind === "client" ? prospect.trim() : "";
      const qs = `lang=${lang}${name ? `&prospect=${encodeURIComponent(name)}` : ""}`;
      const { data } = await api.get(`/brochures/${path}.${ext}?${qs}`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ConstruPilot-${path}-${lang}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Impossível gerar");
    } finally {
      setBusy("");
    }
  };

  const Row = ({ kind, ext, icon: Icon, title }) => (
    <div className="flex flex-wrap items-center gap-2">
      <span className="text-xs text-muted-foreground w-28 flex items-center gap-1.5">
        <Icon className="h-3.5 w-3.5" /> {title}
      </span>
      {LANGS.map((l) => (
        <Button key={l.code} variant="outline" size="sm" className="rounded-sm gap-2"
          onClick={() => get(kind, ext, l.code)} disabled={!!busy}
          data-testid={`deck-${kind}-${ext}-${l.code}`}>
          {busy === `${kind}-${ext}-${l.code}`
            ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
            : <Download className="h-3.5 w-3.5" />} {l.label}
        </Button>
      ))}
    </div>
  );

  return (
    <div className="surface p-5 space-y-4" data-testid="investor-deck-card">
      <p className="overline flex items-center gap-2 text-primary">
        <Presentation className="h-4 w-4" /> Apresentações para investidores e clientes
      </p>
      <p className="text-sm text-muted-foreground">
        Deck para investidores com os <b>números reais</b> lidos na base no momento da transferência (contas existentes fora de testes, ativas 30 dias, subscrições pagas, inscrições medidas, taxa de ativação), a análise do mercado português, as aplicações Android e iOS e o plano de exploração de <b>500 000 € em 24 meses</b>. Um valor não mensurável é apresentado como «não mensurável». O PowerPoint integra as capturas de ecrã reais do produto.
      </p>
      <div className="space-y-2.5">
        <p className="text-xs font-medium text-foreground">Investidor (confidencial)</p>
        <Row kind="investor" ext="pdf" icon={FileText} title="PDF" />
        <Row kind="investor" ext="pptx" icon={Presentation} title="PowerPoint" />
        <p className="text-xs font-medium text-foreground pt-2">Cliente (comercial)</p>
        <Input value={prospect} onChange={(e) => setProspect(e.target.value)} maxLength={80}
          placeholder="Nome do potencial cliente (opcional) — página de rosto personalizada e datada"
          className="rounded-sm h-9 text-sm" data-testid="deck-client-prospect-input" />
        <Row kind="client" ext="pdf" icon={FileText} title="PDF" />
        <Row kind="client" ext="pptx" icon={Presentation} title="PowerPoint" />
      </div>
      <p className="text-[11px] text-muted-foreground">
        Documentos não publicados no site: o deck para investidores só pode ser gerado por um administrador.
      </p>
    </div>
  );
}
