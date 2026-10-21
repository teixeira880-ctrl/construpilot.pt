import { useState } from "react";
import { FileText, Download, Loader2, Presentation } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { toast } from "sonner";

const LANGS = [
  { code: "fr", label: "Português" },
  { code: "en", label: "English" },
  { code: "pt", label: "Português" },
];

// Plaquette et deck commerciaux à l'en-tête de l'entreprise, avec page de garde personnalisée.
export const BrochureCard = () => {
  const [busy, setBusy] = useState("");
  const [prospect, setProspect] = useState("");

  const get = async (ext, lang) => {
    setBusy(`${ext}-${lang}`);
    try {
      const name = prospect.trim();
      const qs = `lang=${lang}${name ? `&prospect=${encodeURIComponent(name)}` : ""}`;
      const { data } = await api.get(`/brochures/plaquette.${ext}?${qs}`, { responseType: "blob" });
      const url = URL.createObjectURL(data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ConstruPilot-brochura${name ? `-${name.replace(/\W+/g, "-")}` : ""}-${lang}.${ext}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Brochura indisponível");
    } finally { setBusy(""); }
  };

  return (
    <div className="surface p-5 space-y-3" data-testid="brochure-card">
      <p className="overline flex items-center gap-2 text-primary">
        <FileText className="h-4 w-4" /> Brochura comercial
      </p>
      <p className="text-sm text-muted-foreground">
        Apresentação com o seu cabeçalho (logótipo, nome, contactos): para enviar aos seus clientes ou imprimir para as suas reuniões. Indique o nome do cliente para uma página de rosto personalizada e datada.
      </p>
      <Input value={prospect} onChange={(e) => setProspect(e.target.value)} maxLength={80}
        placeholder="Nome do cliente (opcional) — ex.: Câmara Municipal de Sintra"
        className="rounded-sm h-10" data-testid="brochure-prospect-input" />
      <div className="space-y-2">
        {[["pdf", FileText, "PDF"], ["pptx", Presentation, "PowerPoint"]].map(([ext, Icon, title]) => (
          <div key={ext} className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground w-24 flex items-center gap-1.5">
              <Icon className="h-3.5 w-3.5" /> {title}
            </span>
            {LANGS.map((l) => (
              <Button key={l.code} variant="outline" size="sm" className="rounded-sm gap-2"
                onClick={() => get(ext, l.code)} disabled={!!busy}
                data-testid={`brochure-${ext}-${l.code}`}>
                {busy === `${ext}-${l.code}`
                  ? <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  : <Download className="h-3.5 w-3.5" />} {l.label}
              </Button>
            ))}
          </div>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">
        Complete o seu logótipo e os seus contactos em «A minha página e os meus documentos» para que apareçam.
      </p>
    </div>
  );
};
