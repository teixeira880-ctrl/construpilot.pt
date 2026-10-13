import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { SEO } from "@/components/SEO";
import { ArrowRight, Download, Check, X, Minus } from "lucide-react";

const API = process.env.REACT_APP_BACKEND_URL;
const COLS = ["ConstruPilot", "Obat", "Trustup Pro", "Vertuoza", "EBP Bât.", "Batappli", "Alobees", "BatiChiffrage", "Renalto"];
const COMPETITORS = [
  { slug: "obat", name: "Obat" }, { slug: "trustup", name: "Trustup Pro" }, { slug: "vertuoza", name: "Vertuoza" },
  { slug: "ebp", name: "EBP Bâtiment" }, { slug: "batappli", name: "Batappli" }, { slug: "alobees", name: "Alobees" },
  { slug: "batichiffrage", name: "BatiChiffrage" }, { slug: "renalto", name: "Renalto" },
];
const ROWS = [
  ["Devis & factures", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Partiel", "Oui", "Oui"]],
  ["Facturation électronique (Factur-X / Chorus Pro)", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "—", "Oui", "Oui"]],
  ["Bibliothèque d'ouvrages & prix", ["Oui", "Oui", "Oui", "Oui", "Option", "Oui", "Non", "Oui", "Oui"]],
  ["Chiffrage 100% déterministe (0 IA sur les maths)", ["Oui", "—", "—", "—", "—", "—", "—", "—", "Non"]],
  ["Métré sur plans (PDF/image) + étalonnage", ["Oui", "À venir", "Non", "Non", "Non", "Non", "Non", "Non", "Partiel"]],
  ["Lecture des cotes natives DWG / DXF", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Détection murs & ouvertures (IA / OpenCV)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Partiel"]],
  ["Projets multi-niveaux consolidés (RDC/R+1…)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Calcul d'escaliers (béton + ferraillage + 3D)", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Lecture DPGF / CCTP → devis chiffré", ["Oui", "—", "—", "—", "Option", "Oui", "—", "Oui", "Oui"]],
  ["Comparaison de versions de plans", ["Oui", "Non", "Non", "Non", "Non", "Non", "Non", "Non", "Non"]],
  ["Assistant IA + agents métier orchestrés", ["Oui", "Partiel", "Non", "Partiel", "Non", "Non", "Non", "Partiel", "Oui"]],
  ["Suivi de chantier / contrôle des coûts", ["Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Oui", "Partiel"]],
  ["Signature électronique", ["Oui", "Oui", "—", "—", "Oui", "Oui", "—", "Oui", "—"]],
  ["Dossier PDF brandé (page de garde, logo, filigrane)", ["Oui", "Partiel", "Partiel", "Partiel", "Partiel", "Partiel", "—", "Partiel", "Partiel"]],
  ["PDF multilingue (FR / EN / PT)", ["Oui", "—", "—", "—", "—", "—", "—", "—", "—"]],
];
const DIFFS = [
  ["Chiffrage 100% déterministe", "Zéro hallucination sur les calculs : l'IA oriente, les moteurs calculent. Chaque montant est traçable, là où les générateurs « IA » produisent un brouillon à relire."],
  ["Du plan au devis, vraiment", "Métré sur PDF/images avec étalonnage, cotes natives DWG/DXF, détection murs & ouvertures, projets multi-niveaux : la plupart s'arrêtent au devis saisi à la main."],
  ["Expertise technique rare", "Calcul d'escaliers béton + ferraillage avec aperçu 3D et PDF, introuvable chez les logiciels de devis généralistes."],
  ["Agents IA orchestrés", "Dossier, devis, détection, comparaison, DPGF→devis : l'agent enchaîne vos moteurs, propose, vous validez, il apprend vos corrections."],
  ["Livrables haut de gamme", "Dossier PDF brandé (page de garde, logo, filigrane, total TTC), multilingue FR/EN/PT, signature en ligne."],
  ["Comparaison & contrôle", "Comparaison de versions de plans et contrôle des cotes : vous sécurisez le métré avant de chiffrer."],
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
        title="ConstruPilot, l'alternative à Obat, Batappli & Vertuoza — Comparatif BTP"
        description="Comparatif des logiciels BTP : ConstruPilot vs Obat, Trustup Pro, Vertuoza, EBP, Batappli, Alobees, BatiChiffrage, Renalto. Métré sur plan, chiffrage déterministe, escaliers 3D, agents IA."
        keywords="alternative Obat, alternative Batappli, alternative Vertuoza, comparatif logiciel devis BTP, logiciel métré plan, chiffrage déterministe, logiciel bâtiment artisan"
        canonical="/comparatif"
        jsonLd={{ "@context": "https://schema.org", "@type": "WebPage", "name": "Comparatif logiciels BTP — ConstruPilot" }}
      />

      <div className="text-center">
        <p className="text-sm font-semibold text-primary mb-3">COMPARATIF MARCHÉ</p>
        <h1 className="font-display text-4xl sm:text-5xl font-extrabold tracking-tight">L'alternative BTP qui va <span className="text-primary">du plan au devis</span></h1>
        <p className="mt-4 text-base text-muted-foreground max-w-2xl mx-auto">ConstruPilot face à Obat, Trustup Pro, Vertuoza, EBP, Batappli, Alobees, BatiChiffrage et Renalto. Le seul à combiner métré sur plan, chiffrage déterministe, escaliers 3D et agents IA.</p>
        <div className="mt-7 flex flex-wrap items-center justify-center gap-3">
          <Button onClick={() => navigate("/inscription")} size="lg" className="rounded-full gap-2 font-bold px-7 h-12" data-testid="comparatif-hero-cta">Démarrer l'essai gratuit <ArrowRight className="h-5 w-5" /></Button>
          <a href={pdfUrl} target="_blank" rel="noopener noreferrer" data-testid="comparatif-download-hero">
            <Button size="lg" variant="outline" className="rounded-full gap-2 h-12"><Download className="h-4 w-4" /> Télécharger le comparatif (PDF)</Button>
          </a>
        </div>
      </div>

      <div className="mt-8 rounded-xl border border-border bg-card p-5 flex flex-col sm:flex-row items-center gap-3 max-w-3xl mx-auto" data-testid="comparatif-targeted">
        <p className="text-sm font-medium flex-1">Vous utilisez déjà un logiciel ? Obtenez le comparatif ciblé.</p>
        <Select value={vs} onValueChange={setVs}>
          <SelectTrigger className="w-full sm:w-52 rounded-full" data-testid="comparatif-select"><SelectValue placeholder="Choisir un concurrent" /></SelectTrigger>
          <SelectContent>
            {COMPETITORS.map((c) => <SelectItem key={c.slug} value={c.slug} data-testid={`comparatif-opt-${c.slug}`}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <a href={pdfUrl} target="_blank" rel="noopener noreferrer" data-testid="comparatif-download-targeted">
          <Button className="rounded-full gap-2 font-semibold"><Download className="h-4 w-4" /> {vs ? "PDF ciblé" : "PDF complet"}</Button>
        </a>
      </div>

      <div className="mt-8 overflow-x-auto rounded-xl border border-border bg-card">
        <table className="w-full text-sm border-collapse min-w-[900px]" data-testid="comparatif-table">
          <thead>
            <tr>
              <th className="text-left p-3 bg-[#0A0D14] text-white font-semibold text-xs">Fonctionnalité</th>
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
      <p className="text-xs text-muted-foreground mt-3">Légende : ✓ disponible · texte = partiel / option / à venir · ✗ non proposé · — non documenté publiquement. Données publiques à la date d'édition, non contractuelles.</p>

      <h2 className="font-display text-2xl font-bold mt-14 mb-6">Ce qui distingue ConstruPilot</h2>
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
        <p className="mt-3 text-slate-300">Du plan au devis, sans ressaisie ni calcul manuel. Testez en conditions réelles.</p>
        <Button onClick={() => navigate("/inscription")} size="lg" className="mt-6 rounded-full gap-2 font-bold px-8 h-12" data-testid="comparatif-bottom-cta">Démarrer maintenant <ArrowRight className="h-5 w-5" /></Button>
      </div>
    </div>
  );
}
