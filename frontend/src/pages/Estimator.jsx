import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { toast } from "sonner";
import { ChevronLeft, ChevronRight, Calculator, Save, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { api } from "@/lib/api";
import { EstimationView } from "@/components/EstimationView";
import { LeadDialog } from "@/components/LeadDialog";
import { EmailPdfDialog } from "@/components/EmailPdfDialog";
import { WhatsAppShare } from "@/components/WhatsAppShare";
import { SoftPaywall } from "@/components/SoftPaywall";
import { SavingsCard } from "@/components/SavingsCard";
import { SectionTitle } from "@/components/Bits";
import { SEO } from "@/components/SEO";
import { useAuth } from "@/context/AuthContext";
import { useBilling } from "@/context/BillingContext";

const CONDITION_LABEL = {
  neuf: "Neuf", bon: "Bon état", moyen: "État moyen", vetuste: "Vétuste",
  a_renover_totalement: "À rénover totalement",
};

export default function Estimator() {
  const [params] = useSearchParams();
  const { has, tier } = useBilling();
  const [catalog, setCatalog] = useState(null);
  const [step, setStep] = useState(0);
  const [est, setEst] = useState(null);
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const { user } = useAuth();
  const navigate = useNavigate();

  const [form, setForm] = useState({
    project_type: params.get("type") || "renovation_complete",
    country: "FR", region: "Île-de-France", city: "",
    surface: Number(params.get("surface")) || 100,
    building_type: "maison", construction_year: 1990, condition: "bon",
    finish_level: "standard", description: "", lots: [],
  });
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    api.get("/estimation/catalog").then(({ data }) => setCatalog(data));
  }, []);

  const regions = (catalog?.regions || []).filter((r) => r.country === form.country);

  const compute = async () => {
    setBusy(true);
    try {
      const { data } = await api.post("/estimation/compute", {
        ...form,
        surface: Number(form.surface),
        construction_year: Number(form.construction_year) || null,
        lots: form.lots.length ? form.lots : null,
      });
      setEst(data);
      setName(`${catalog.project_types.find((p) => p.key === form.project_type)?.name} ${form.city || ""}`.trim());
      setStep(3);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e) {
      toast.error("Calcul impossible");
    } finally {
      setBusy(false);
    }
  };

  const save = async () => {
    if (!user) { navigate("/login"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/projects", {
        ...form, name: name || "Mon projet", surface: Number(form.surface),
        construction_year: Number(form.construction_year) || null,
        lots: form.lots.length ? form.lots : null, estimation: est,
      });
      toast.success("Projet enregistré");
      navigate(`/projet/${data.project_id}`);
    } catch {
      toast.error("Sauvegarde impossible");
    } finally {
      setBusy(false);
    }
  };

  const downloadPdf = async () => {
    setBusy(true);
    try {
      const res = await api.post("/estimation/pdf",
        { project: { name: name || "Mon projet", city: form.city, description: form.description },
          estimation: est },
        { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `Estimation-ConstruPilot-${name || "projet"}.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("PDF téléchargé");
    } catch {
      toast.error("PDF indisponible");
    } finally {
      setBusy(false);
    }
  };

  if (!catalog) return <div className="h-40 grid place-items-center"><div className="h-8 w-8 border-2 border-primary border-t-transparent rounded-full animate-spin" /></div>;

  const steps = ["Projet", "Bâtiment", "Finitions"];

  return (
    <div className="grid gap-10">
      <SEO title="Estimateur travaux gratuit" description="Estimation gratuite de vos travaux de rénovation en 30 secondes. Prix par lot, TVA 10 %, durée estimée. Basé sur les prix France 2026." keywords="estimateur travaux gratuit, estimation rénovation en ligne, coût travaux, calcul devis, prix chantier" canonical="/estimation" />
      <SectionTitle as="h1" over="Estimateur de travaux" title="Chiffrez votre chantier en 3 étapes">
        Moteur d'estimation déterministe : prix de référence par lot, coefficients régionaux,
        état du bâtiment et niveau de finition.
      </SectionTitle>

      {step < 3 && (
        <div className="max-w-3xl">
          <div className="flex items-center gap-4 mb-8">
            <Progress value={((step + 1) / 3) * 100} className="h-1 rounded-none" data-testid="wizard-progress" />
            <span className="num text-xs text-muted-foreground whitespace-nowrap">{step + 1} / 3 · {steps[step]}</span>
          </div>

          <div className="surface p-8 grid gap-6" data-testid={`wizard-step-${step}`}>
            {step === 0 && (
              <>
                <div className="grid gap-2">
                  <Label>Type de travaux</Label>
                  <Select value={form.project_type} onValueChange={(v) => set("project_type", v)}>
                    <SelectTrigger className="rounded-sm h-11" data-testid="select-project-type"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      {catalog.project_types.map((p) => <SelectItem key={p.key} value={p.key}>{p.name}</SelectItem>)}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid sm:grid-cols-2 gap-6">
                  <div className="grid gap-2">
                    <Label>Pays</Label>
                    <Select value={form.country} onValueChange={(v) => { set("country", v); set("region", v === "FR" ? "Île-de-France" : "Lisboa"); }}>
                      <SelectTrigger className="rounded-sm h-11" data-testid="select-country"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="FR">France</SelectItem>
                        <SelectItem value="PT">Portugal</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <Label>Région</Label>
                    <Select value={form.region} onValueChange={(v) => set("region", v)}>
                      <SelectTrigger className="rounded-sm h-11" data-testid="select-region"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {regions.map((r) => <SelectItem key={r.region} value={r.region}>{r.region} (×{r.coef})</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <Label>Ville / code postal</Label>
                    <Input value={form.city} onChange={(e) => set("city", e.target.value)} data-testid="input-city" className="rounded-sm h-11" placeholder="Ex : Nanterre 92000" />
                  </div>
                  <div className="grid gap-2">
                    <Label>Surface concernée (m²)</Label>
                    <Input type="number" min={1} value={form.surface} onChange={(e) => set("surface", e.target.value)} data-testid="input-surface" className="rounded-sm h-11 num" />
                  </div>
                </div>
              </>
            )}

            {step === 1 && (
              <>
                <div className="grid sm:grid-cols-3 gap-6">
                  <div className="grid gap-2">
                    <Label>Type de bâtiment</Label>
                    <Select value={form.building_type} onValueChange={(v) => set("building_type", v)}>
                      <SelectTrigger className="rounded-sm h-11" data-testid="select-building-type"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {catalog.building_types.map((b) => <SelectItem key={b} value={b}>{b[0].toUpperCase() + b.slice(1)}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="grid gap-2">
                    <Label>Année de construction</Label>
                    <Input type="number" value={form.construction_year} onChange={(e) => set("construction_year", e.target.value)} data-testid="input-year" className="rounded-sm h-11 num" />
                  </div>
                  <div className="grid gap-2">
                    <Label>État actuel</Label>
                    <Select value={form.condition} onValueChange={(v) => set("condition", v)}>
                      <SelectTrigger className="rounded-sm h-11" data-testid="select-condition"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        {catalog.conditions.map((c) => <SelectItem key={c} value={c}>{CONDITION_LABEL[c] || c}</SelectItem>)}
                      </SelectContent>
                    </Select>
                  </div>
                </div>
                <div className="grid gap-2">
                  <Label>Description (optionnel)</Label>
                  <Textarea rows={3} value={form.description} onChange={(e) => set("description", e.target.value)} data-testid="input-description" className="rounded-sm" />
                </div>
              </>
            )}

            {step === 2 && (
              <>
                <div className="grid gap-3">
                  <Label>Niveau de finition</Label>
                  <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-3">
                    {catalog.finish_levels.map((f) => (
                      <button
                        key={f.key} onClick={() => set("finish_level", f.key)}
                        data-testid={`finish-${f.key}`}
                        className={`p-4 text-left rounded-sm border transition-colors ${
                          form.finish_level === f.key ? "border-primary bg-primary/10" : "border-border hover:border-primary/50"
                        }`}
                      >
                        <p className="font-display font-semibold">{f.name}</p>
                        <p className="num mt-1 text-xs text-muted-foreground">coefficient ×{f.coef}</p>
                      </button>
                    ))}
                  </div>
                </div>
                <div className="grid gap-3">
                  <Label>Lots à inclure (vide = lots standards du type de projet)</Label>
                  <div className="flex flex-wrap gap-2" data-testid="lots-picker">
                    {catalog.lots.map((l) => {
                      const on = form.lots.includes(l.key);
                      return (
                        <button
                          key={l.key} data-testid={`lot-toggle-${l.key}`}
                          onClick={() => set("lots", on ? form.lots.filter((k) => k !== l.key) : [...form.lots, l.key])}
                          className={`px-3 py-2 text-xs rounded-sm border transition-colors ${
                            on ? "border-primary bg-primary/15 text-primary" : "border-border text-muted-foreground hover:border-primary/50"
                          }`}
                        >
                          {l.name}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </>
            )}

            <div className="flex gap-3 pt-4 border-t border-border">
              {step > 0 && (
                <Button variant="outline" onClick={() => setStep(step - 1)} data-testid="wizard-prev-btn" className="rounded-sm gap-2">
                  <ChevronLeft className="h-4 w-4" /> Retour
                </Button>
              )}
              {step < 2 ? (
                <Button onClick={() => setStep(step + 1)} data-testid="wizard-next-btn" className="ml-auto rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  Continuer <ChevronRight className="h-4 w-4" />
                </Button>
              ) : (
                <Button onClick={compute} disabled={busy} data-testid="wizard-compute-btn" className="ml-auto rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                  <Calculator className="h-4 w-4" /> {busy ? "Calcul…" : "Créer mon estimation"}
                </Button>
              )}
            </div>
          </div>
        </div>
      )}

      {step === 3 && est && (
        <>
          <div className="flex flex-wrap gap-3">
            <Button variant="outline" onClick={() => setStep(0)} data-testid="edit-estimation-btn" className="rounded-sm gap-2">
              <ChevronLeft className="h-4 w-4" /> Modifier les paramètres
            </Button>
            <Input value={name} onChange={(e) => setName(e.target.value)} data-testid="estimation-project-name" className="rounded-sm max-w-xs" placeholder="Nom du projet" />
            <Button onClick={save} disabled={busy} data-testid="save-estimation-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
              <Save className="h-4 w-4" /> Enregistrer le projet
            </Button>
            <Button variant="outline" onClick={downloadPdf} disabled={busy} data-testid="download-pdf-btn" className="rounded-sm gap-2">
              <Download className="h-4 w-4" /> Télécharger le devis PDF
            </Button>
            <EmailPdfDialog project={{ name: name || "Mon projet", city: form.city, description: form.description }} estimation={est} />
            <WhatsAppShare project={{ name: name || "Mon projet", city: form.city, surface: Number(form.surface) }} estimation={est} />
            <LeadDialog budget={est.total_avg} description={form.description} />
          </div>
          <EstimationView est={est} />
          <SavingsCard estimation={est} />
          {tier === "free" && <SoftPaywall context="savings" />}
        </>
      )}
    </div>
  );
}
