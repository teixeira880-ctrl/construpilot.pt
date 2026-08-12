import { useEffect, useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import { Sparkles, HelpCircle, AlertTriangle, Save, Wrench, ShoppingCart, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { api, eur } from "@/lib/api";
import { EstimationView } from "@/components/EstimationView";
import { LeadDialog } from "@/components/LeadDialog";
import { useAuth } from "@/context/AuthContext";
import { SectionTitle } from "@/components/Bits";

export default function SmartProject() {
  const [description, setDescription] = useState(sessionStorage.getItem("cmrenov_description") || "");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [name, setName] = useState("");
  const [saving, setSaving] = useState(false);
  const { user } = useAuth();
  const navigate = useNavigate();

  const run = useCallback(async (text) => {
    if (!text || text.trim().length < 10) {
      toast.error("Décrivez votre projet en quelques mots (10 caractères minimum)");
      return;
    }
    setLoading(true);
    setResult(null);
    try {
      const { data } = await api.post("/estimation/analyse", { description: text });
      setResult(data);
      setName(data.analysis?.summary?.slice(0, 48) || "Mon projet");
    } catch (e) {
      toast.error("L'analyse IA a échoué. Réessayez.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const stored = sessionStorage.getItem("cmrenov_description");
    if (stored) {
      sessionStorage.removeItem("cmrenov_description");
      run(stored);
    }
  }, [run]);

  const save = async () => {
    if (!user) {
      sessionStorage.setItem("cmrenov_description", description);
      navigate("/login");
      return;
    }
    setSaving(true);
    try {
      const a = result.analysis;
      const { data } = await api.post("/projects", {
        name: name || "Mon projet", description,
        project_type: a.project_type, surface: a.surface, finish_level: a.finish_level,
        building_type: a.building_type, condition: a.condition, lots: a.lots,
        estimation: result.estimation,
      });
      toast.success("Projet sauvegardé");
      navigate(`/projet/${data.project_id}`);
    } catch (e) {
      toast.error("Sauvegarde impossible");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="grid gap-12">
      <div>
        <SectionTitle over="CMRENOV Smart Project" title="Décrivez votre projet, l'IA fait le reste">
          Liste des travaux, ordre d'exécution, budget, quantités, durée, ce que vous pouvez faire
          vous-même, risques et économies possibles.
        </SectionTitle>
        <div className="surface p-2 relative">
          <Textarea
            data-testid="smart-project-input" rows={4} value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Ex : Je veux rénover complètement cette maison de 120 m²…"
            className="resize-none border-0 bg-transparent focus-visible:ring-0 text-base"
          />
          <div className="p-2 pt-0 flex gap-3">
            <Button
              onClick={() => run(description)} disabled={loading} data-testid="smart-project-submit-btn"
              className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white"
            >
              {loading ? <RefreshCw className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              {loading ? "Analyse en cours…" : "Analyser mon projet"}
            </Button>
          </div>
        </div>
      </div>

      {loading && (
        <div className="surface p-12 text-center" data-testid="smart-project-loading">
          <div className="h-8 w-8 mx-auto border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="mt-6 text-sm text-muted-foreground">
            CMRENOV AI analyse votre projet, décompose les lots et lance le moteur de calcul…
          </p>
        </div>
      )}

      {result && (
        <>
          <div className="grid lg:grid-cols-3 gap-4" data-testid="analysis-block">
            <div className="surface p-6 lg:col-span-2">
              <p className="overline">Ce que CMRENOV AI a compris</p>
              <p className="mt-3 text-sm">{result.analysis.summary}</p>
              {result.analysis.diy_advice && (
                <p className="mt-4 text-sm text-muted-foreground flex gap-2">
                  <Wrench className="h-4 w-4 text-primary shrink-0 mt-0.5" />
                  {result.analysis.diy_advice}
                </p>
              )}
            </div>
            <div className="surface p-6">
              <p className="overline flex items-center gap-2"><HelpCircle className="h-4 w-4" /> Questions à préciser</p>
              <ul className="mt-3 grid gap-2 text-sm text-muted-foreground" data-testid="dynamic-questions">
                {(result.analysis.questions || []).map((q, i) => <li key={i}>• {q}</li>)}
              </ul>
            </div>
            {result.analysis.risks?.length > 0 && (
              <div className="surface p-6 lg:col-span-3 border-amber-500/40">
                <p className="overline flex items-center gap-2 text-amber-500">
                  <AlertTriangle className="h-4 w-4" /> Points de vigilance
                </p>
                <ul className="mt-3 grid sm:grid-cols-2 gap-2 text-sm text-muted-foreground">
                  {result.analysis.risks.map((r, i) => <li key={i}>• {r}</li>)}
                </ul>
              </div>
            )}
          </div>

          <EstimationView est={result.estimation} />

          <div className="surface p-6 flex flex-col lg:flex-row gap-4 lg:items-center">
            <div className="flex-1">
              <p className="overline">Sauvegarder ce chantier</p>
              <Input
                value={name} onChange={(e) => setName(e.target.value)} data-testid="project-name-input"
                placeholder="Nom du projet" className="mt-3 rounded-sm"
              />
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={save} disabled={saving} data-testid="save-project-btn" className="rounded-sm gap-2 hover:bg-orange-600 hover:text-white">
                <Save className="h-4 w-4" /> {user ? "Enregistrer mon projet" : "Se connecter et enregistrer"}
              </Button>
              <Button variant="outline" className="rounded-sm gap-2" data-testid="goto-prices-btn" onClick={() => navigate("/prix")}>
                <ShoppingCart className="h-4 w-4" /> Comparer les prix matériaux
              </Button>
              <LeadDialog budget={result.estimation.total_avg} description={description} />
            </div>
          </div>
          <p className="text-xs text-muted-foreground -mt-8">
            Estimation moyenne : <span className="num">{eur(result.estimation.total_avg)}</span> — indicative,
            calculée par le moteur déterministe CMRENOV (prix de référence régionaux).
          </p>
        </>
      )}
    </div>
  );
}
