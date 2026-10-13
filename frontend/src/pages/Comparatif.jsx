import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SEO } from "@/components/SEO";
import { ArrowRight, Download, Check, X, Minus } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;
const COLS = ["ConstruPilot", "Obat", "Trustup Pro", "Vertuoza", "Primavera", "Batappli", "Alobees", "BatiChiffrage", "Renalto"];
const COMPETITORS = [
  { slug: "obat", name: "Obat" }, { slug: "trustup", name: "Trustup Pro" }, { slug: "vertuoza", name: "Vertuoza" },
  { slug: "ebp", name: "PHC / Primavera" }, { slug: "batappli", name: "Batappli" }, { slug: "alobees", name: "Alobees" },
  { slug: "batichiffrage", name: "BatiChiffrage" }, { slug: "renalto", name: "Renalto" },
];
const ROWS = [
  ["Orçamentos e faturas", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Partiel", "Oui", "Oui"]],
  ["Faturação eletrónica (SAF-T / QR code ATCUD)", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "—", "Oui", "Oui"]],
  ["Biblioteca de artigos e preços", ["Oui", "Oui", "Oui", "Oui", "Option", "Oui", "Non", "Oui", "Oui"]],
  ["Orçamentação 100% determinística (0 IA na matemática)", ["Oui", "—", "—", "—", "—", "—", "—", "—", "Non"]],
  ["Medição em plantas (PDF/imagem) + calibração", ["Oui", "Brevemente", "Non", "Non", "Non", "Non", "Non", "Non", "Partiel"]],
  ["Leitura das cotas nativas DWG / DXF", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Deteção de paredes e vãos (IA / OpenCV)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Partiel"]],
  ["Projetos multinível consolidados (R/C, 1.º andar…)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Cálculo de escadas (betão + armaduras + 3D)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Leitura de mapas de quantidades / cadernos de encargos → orçamento detalhado", ["Oui", "—", "—", "—", "Option", "Oui", "—", "Oui", "Oui"]],
  ["Comparação de versões de plantas", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Assistente IA + agentes especializados orquestrados", ["Oui", "Partiel", "Non", "Partiel", "Non", "Non", "Non", "Partiel", "Oui"]],
  ["Acompanhamento de obra / controlo de custos", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Partiel"]],
  ["Assinatura eletrónica", ["Oui", "Oui", "—", "—", "Oui", "Oui", "—", "Oui", "—"]],
  ["Processo PDF com a sua marca (página de rosto, logótipo, marca de água)", ["Oui", "Partiel", "Partiel", "Partiel", "Partiel", "Partiel", "—", "Partiel", "Partiel"]],
  ["PDF multilingue (FR / EN / PT)", ["Oui", "—", "—", "—", "—", "—", "—", "—", "—"]],
];
const DIFFS = [
  ["Orçamentação 100% determinística", "Zero alucinações nos cálculos: a IA orienta, os motores calculam. Cada montante é rastreável, onde os geradores «IA» produzem um rascunho a rever."],
  ["Da planta ao orçamento, a sério", "Medição em PDF/imagens com calibração, cotas nativas DWG/DXF, deteção de paredes e vãos, projetos multinível: a maioria fica pelo orçamento introduzido à mão."],
  ["Expertise technique rare", "Cálculo de escadas em betão + armaduras com pré-visualização 3D e PDF, inexistente nos softwares de orçamentação generalistas."],
  ["Agentes IA orquestrados", "Processo, orçamento, deteção, comparação, mapa de quantidades→orçamento: o agente encadeia os seus motores, propõe, valida e aprende com as suas correções."],
  ["Entregáveis de topo", "Processo PDF com a sua marca (página de rosto, logótipo, marca de água, total c/ IVA), multilingue PT/EN/FR, assinatura online."],
  ["Comparação e controlo", "Comparação de versões de plantas e controlo das cotas: assegura a medição antes de orçamentar."],
];

const Cell = ({ v }) => {
  if (v === "Oui") return <Check className="h-4 w-4 text-[#15803D] inline" />;
  if (v === "Non") return <X className="h-4 w-4 text-[#B91C1C] inline" />;
  if (v === "—") return <Minus className="h-4 w-4 text-slate-400 inline" />;
  return <span className="text-[11px] font-medium text-[#B45309]">{v}</span>;
};

export default function Comparatif() {
  const navigate = useNavigate();
  const [vs, setVs] = useState("");
  const pdfUrl = `${API}/api/public/marketing/comparatif.pdf${vs ? `?vs=${vs}` : ""}`;

  return (
    <div className="mx-auto max-w-6xl px-4 sm:px-6 py-10" data-testid="comparatif-page">
      <SEO
        title="ConstruPilot, a alternativa aos softwares de orçamentação de obras — Comparativo"
        description="Comparativo de softwares para a construção: medição em planta, orçamentação determinística, escadas 3D, agentes IA."
        keywords="alternativa software orçamentos obras, comparativo software construção, software medições planta, orçamentação determinística, software construção profissional"
        canonical="/comparatif"
        jsonLd={{ "@context": "https://schema.org", "@type": "WebPage", "name": "Comparatif logiciels BTP — ConstruPilot" }}
      />

      <div className="text-center">
        <p className="text-sm font-semibold text-primary mb-3">COMPARATIVO DE MERCADO</p>
        <h1 className="font-display text-4xl sm:text-5xl font-extrabold tracking-tight">A alternativa para a construção que vai <span className="text-primary">da planta ao orçamento</span></h1>
        <p className="mt-4 text-base text-muted-foreground max-w-2xl mx-auto">O ConstruPilot face aos softwares de orçamentação do mercado. O único a combinar medição em planta, orçamentação determinística, escadas 3D e agentes IA.</p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button onClick={() => navigate("/inscription")} size="lg" className="rounded-full gap-2 font-bold px-7 h-12" data-testid="comparatif-hero-cta">Iniciar o teste gratuito <ArrowRight className="h-5 w-5" /></Button>
          <a href={pdfUrl} target="_blank" rel="noopener noreferrer" data-testid="comparatif-download-hero">
            <Button size="lg" variant="outline" className="rounded-full gap-2 h-12"><Download className="h-4 w-4" /> Transferir o comparativo (PDF)</Button>
          </a>
        </div>
      </div>

      <div className="mt-8 rounded-xl border border-border bg-card p-5 flex flex-col sm:flex-row items-center gap-3 max-w-3xl mx-auto" data-testid="comparatif-targeted">
        <p className="text-sm font-medium flex-1">Já utiliza um software? Obtenha o comparativo direcionado.</p>
        <Select value={vs} onValueChange={setVs}>
          <SelectTrigger className="w-full sm:w-52 rounded-full" data-testid="comparatif-select"><SelectValue placeholder="Escolher um concorrente" /></SelectTrigger>
          <SelectContent>
            {COMPETITORS.map((c) => <SelectItem key={c.slug} value={c.slug} data-testid={`comparatif-opt-${c.slug}`}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <a href={pdfUrl} target="_blank" rel="noopener noreferrer" data-testid="comparatif-download-targeted">
          <Button className="rounded-full gap-2 font-semibold"><Download className="h-4 w-4" /> {vs ? "PDF direcionado" : "PDF complet"}</Button>
        </a>
      </div>

      <div className="mt-8 overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full text-sm border-collapse min-w-[900px]" data-testid="comparatif-table">
          <thead>
            <tr>
              <th className="text-left p-3 bg-[#0A0D14] text-white font-semibold text-xs">Funcionalidade</th>
              {COLS.map((c, i) => (
                <th key={c} className={`p-3 text-center text-xs font-semibold ${i === 0 ? "bg-primary text-white" : "bg-[#0A0D14] text-white"}`}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ROWS.map(([feat, vals], r) => (
              <tr key={feat} className={r % 2 ? "bg-muted/40" : ""}>
                <td className="p-3 text-xs font-semibold border-t border-border">{feat}</td>
                {vals.map((v, i) => (
                  <td key={i} className={`p-3 text-center border-t border-border ${i === 0 ? "bg-[#F1FBF4] border-x border-primary/40" : ""}`}><Cell v={v} /></td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted-foreground mt-3">Legenda: ✓ disponível · texto = parcial / opção / brevemente · ✗ não proposto · — não documentado publicamente. Dados públicos à data de edição, não contratuais.</p>

      <h2 className="font-display text-2xl font-bold mt-14 mb-6">O que distingue o ConstruPilot</h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-5">
        {DIFFS.map(([t, d]) => (
          <div key={t} className="rounded-xl border border-border bg-card p-5">
            <p className="font-semibold text-primary flex items-center gap-2"><Check className="h-4 w-4" /> {t}</p>
            <p className="text-sm text-muted-foreground mt-2">{d}</p>
          </div>
        ))}
      </div>

      <div className="mt-14 rounded-2xl bg-[#0A0D14] text-white p-10 text-center">
        <h2 className="font-display text-3xl font-bold">Essayez ConstruPilot gratuitement 7 jours</h2>
        <p className="mt-3 text-slate-300">Da planta ao orçamento, sem reintrodução nem cálculo manual. Teste em condições reais.</p>
        <Button onClick={() => navigate("/inscription")} size="lg" className="mt-6 rounded-full gap-2 font-bold px-8 h-12" data-testid="comparatif-bottom-cta">Começar agora <ArrowRight className="h-5 w-5" /></Button>
      </div>
    </div>
  );
}
